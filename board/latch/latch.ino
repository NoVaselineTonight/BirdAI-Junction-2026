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

  Bring-up from the board's Linux shell: python -m feeder_census.latch close | open | cycle

  Angles: start with 10 (open) and 100 (closed). Adjust the two constants below to the real latch.
*/

#include <Servo.h>
#include "Arduino_RouterBridge.h"

const int SERVO_PIN = 9;  // D9

const int SERVO_OPEN = 10;
const int SERVO_CLOSED = 100;

const unsigned long REOPEN_AFTER_MS = 30000;  // fail-safe: open when no close command came for 30 s

Servo servo;

volatile bool latchClosed = false;
volatile unsigned long lastCloseMs = 0;

// Moves the servo. Does nothing when the latch is already in that state, so the close command
// repeated at every detection never starts the servo.
void moveLatch(bool closed) {
  if (closed == latchClosed) {
    return;
  }
  servo.write(closed ? SERVO_CLOSED : SERVO_OPEN);
  latchClosed = closed;
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

void setup() {
  // a restart always leaves the feeder open
  servo.attach(SERVO_PIN);
  servo.write(SERVO_OPEN);

  Bridge.begin();
  Bridge.provide_safe("set_latch", set_latch);
  Bridge.provide_safe("get_latch", get_latch);
}

void loop() {
  if (latchClosed && millis() - lastCloseMs >= REOPEN_AFTER_MS) {
    moveLatch(false);
  }
  delay(10);
}
