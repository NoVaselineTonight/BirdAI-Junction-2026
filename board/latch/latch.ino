/*
  Feeder latch for the Feeder Census demo (Arduino UNO Q, microcontroller side).

  One DFRobot SER0006 servo (9 g, 180 degree position servo, 4.8-6 V) closes a latch over the
  feeder when the Linux side sees a squirrel or a rat. The Linux program (feeder_census, --latch
  router) calls set_latch(true/false) through arduino-router; while an animal is there it repeats
  set_latch(true) at every detection. If no close command arrives for REOPEN_AFTER_MS the sketch
  opens the latch by itself, so the feeder never stays shut when the Linux side stops.

  Wiring:
  - Servo signal wire (orange or yellow) to D9.
  - Servo power from the board's 5V and GND pins: the red wire to 5V, the brown wire to GND. One
    servo, so no joining of wires and no breadboard is needed. Keep the flap light: a jammed or
    overloaded servo pulls enough current to reset the board.
  - A separate 5 V supply that can give at least 1 A (its ground joined to a GND pin on the board,
    or the signal has no reference) is still the better option if you have one.
  - Never put 5 V on D3 or A0-A5.

  Mechanics:
  - The servo is a 180 degree position servo. It turns at most half a turn and does not spin round.
  - Both pull wires go on the same axis (spool or horn), wound the same way, so they rise together.
  - A spool or horn of radius r pulls about 3.1 x r of wire in half a turn, and about 1.6 x r over
    the default 10 to 100 degrees (r = 1 cm: about 1.6 cm of wire, up to about 3 cm at 0 to 180).
  - Rated torque is about 1.6 kg.cm at 4.8 V, so r = 1 cm gives about 1.6 kg at stall. Plan for well
    under half of that for both wires together (about 0.5 kg at r = 1 cm, 0.25 kg at r = 2 cm).
    A servo held stalled gets hot and can reset the board.

  Bring-up from the board's Linux shell: python -m feeder_census.latch close | open | cycle | angle N

  Angles: start with 10 (open) and 100 (closed). Three more calls let the Linux side find the right angles
  without editing this file (the page python -m feeder_census.calibrate uses them):
  - set_angle(degrees): clamps to 0..180, turns the servo there at once and returns the angle used. The servo
    is then in a "hand-set" position: the 30 s fail-safe does not reopen it (calibration needs it to stay),
    but a hand-set angle goes back to the open angle by itself HAND_SET_TIMEOUT_MS (10 minutes) after the
    last set_angle call, and the latch is then open. So the feeder never stays shut for good, even when a
    person sets a closed angle and walks away. The next set_latch also moves a hand-set servo, even when the
    latch is already in that state.
  - get_angle(): the last angle written to the servo.
  - set_limits(open_degrees, closed_degrees): clamps both to 0..180 and stores them as the open and closed
    angles. Unless the servo is in a hand-set position it moves to the new angle of its current state.
  The limits set this way live in memory only: they are lost at a restart of the microcontroller, which
  goes back to 10 and 100. The Linux side sends them again at its start (data/latch_angles.json). To make
  other angles the sketch's own, change the two start values below.
*/

#include <Servo.h>
#include "Arduino_RouterBridge.h"

const int SERVO_PIN = 9;  // D9

int servoOpen = 10;
int servoClosed = 100;

const unsigned long REOPEN_AFTER_MS = 30000;  // fail-safe: open when no close command came for 30 s
const unsigned long HAND_SET_TIMEOUT_MS = 600000;  // a hand-set angle goes back to open 10 minutes after the last set_angle

Servo servo;

volatile bool latchClosed = false;
volatile bool handSet = false;  // the servo was turned by set_angle and has not been moved by set_latch since
volatile unsigned long lastCloseMs = 0;
volatile unsigned long handSetMs = 0;  // when set_angle was last called
int lastAngle = 10;

int clampAngle(int degrees) {
  return degrees < 0 ? 0 : (degrees > 180 ? 180 : degrees);
}

void writeAngle(int degrees) {
  servo.write(degrees);
  lastAngle = degrees;
}

// Moves the servo. Does nothing when the latch is already in that state, so the close command
// repeated at every detection never starts the servo. After a hand-set angle it always moves.
void moveLatch(bool closed) {
  if (closed == latchClosed && !handSet) {
    return;
  }
  writeAngle(closed ? servoClosed : servoOpen);
  latchClosed = closed;
  handSet = false;
}

// Called from Linux through arduino-router. provide_safe runs it from loop(), not the bridge thread.
void set_latch(bool closed) {
  moveLatch(closed);
  if (closed) {
    lastCloseMs = millis();
  }
}

bool get_latch() {
  return latchClosed;
}

// Calibration: turn the servo to any angle at once. The fail-safe does not reopen a hand-set angle.
int set_angle(int degrees) {
  int used = clampAngle(degrees);
  writeAngle(used);
  handSet = true;
  handSetMs = millis();
  return used;
}

int get_angle() {
  return lastAngle;
}

// Calibration: new open and closed angles, in memory only.
bool set_limits(int open_degrees, int closed_degrees) {
  servoOpen = clampAngle(open_degrees);
  servoClosed = clampAngle(closed_degrees);
  if (!handSet) {
    writeAngle(latchClosed ? servoClosed : servoOpen);
  }
  return true;
}

void setup() {
  // a restart always leaves the feeder open
  servo.attach(SERVO_PIN);
  writeAngle(servoOpen);

  Bridge.begin();
  Bridge.provide_safe("set_latch", set_latch);
  Bridge.provide_safe("get_latch", get_latch);
  Bridge.provide_safe("set_angle", set_angle);
  Bridge.provide_safe("get_angle", get_angle);
  Bridge.provide_safe("set_limits", set_limits);
}

void loop() {
  if (handSet) {
    if (millis() - handSetMs >= HAND_SET_TIMEOUT_MS) {
      moveLatch(false);  // moves although the latch is "open": it clears the hand-set mark and writes the open angle
    }
  } else if (latchClosed && millis() - lastCloseMs >= REOPEN_AFTER_MS) {
    moveLatch(false);
  }
  delay(10);
}
