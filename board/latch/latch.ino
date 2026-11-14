/*
  Feeder latch for the Feeder Census demo (Arduino UNO Q, microcontroller side).

  Two DFRobot SER0006 servos (9 g, 180 degree position servos, 4.8-6 V) close a latch over the
  feeder when the Linux side sees a squirrel or a rat. The Linux program (feeder_census, --latch
  router) calls set_latch(true/false) through arduino-router; while an animal is there it repeats
  set_latch(true) at every detection. If no close command arrives for REOPEN_AFTER_MS the sketch
  opens the latch by itself, so the feeder never stays shut when the Linux side stops.

  Wiring:
  - Servo 1 signal wire (orange or yellow) to D9, servo 2 signal wire to D10.
  - Recommended: servo power (red and brown/black wires) from a separate 5 V supply that can give
    at least 1 A, with that supply's ground joined to a GND pin on the board (or the signal has no
    reference).
  - Fallback this team uses (no separate supply): servo power from the board's 5V and GND pins.
    Keep the flap light: a jammed or overloaded servo pulls enough current to reset the board.
    The sketch never starts both servos at the same moment (STAGGER_MS below), so their start-up
    current bursts do not add up.
  - Never put 5 V on D3 or A0-A5.

  Bring-up from the board's Linux shell: python -m feeder_census.latch close | open | cycle

  Angles: start with 10 (open) and 100 (closed); servo 2 is mounted mirrored, so its angles are
  180 minus servo 1's. Adjust the four constants below to the real latch.
*/

#include <Servo.h>
#include "Arduino_RouterBridge.h"

const int SERVO_1_PIN = 9;   // D9
const int SERVO_2_PIN = 10;  // D10

const int SERVO_1_OPEN = 10;
const int SERVO_1_CLOSED = 100;
const int SERVO_2_OPEN = 170;    // mirrored: 180 - 10
const int SERVO_2_CLOSED = 80;   // mirrored: 180 - 100

const unsigned long REOPEN_AFTER_MS = 30000;  // fail-safe: open when no close command came for 30 s
const unsigned long STAGGER_MS = 300;         // servo 2 moves this long after servo 1, never together

Servo servo1;
Servo servo2;

volatile bool latchClosed = false;
volatile unsigned long lastCloseMs = 0;
// Servo 2 follows servo 1 after STAGGER_MS. Done from loop(), not with delay(), so the bridge
// answers at once (the Linux side gives up after 0.5 s) and the fail-safe timer keeps running.
bool servo2Pending = false;
bool servo2Target = false;
unsigned long servo1MovedMs = 0;

// Moves servo 1 now and schedules servo 2. Does nothing when the latch is already in that state,
// so the close command repeated at every detection never starts a servo.
void moveLatch(bool closed) {
  if (closed == latchClosed) {
    return;
  }
  servo1.write(closed ? SERVO_1_CLOSED : SERVO_1_OPEN);
  servo1MovedMs = millis();
  servo2Target = closed;
  servo2Pending = true;
  latchClosed = closed;
}

void moveServo2WhenDue() {
  if (servo2Pending && millis() - servo1MovedMs >= STAGGER_MS) {
    servo2.write(servo2Target ? SERVO_2_CLOSED : SERVO_2_OPEN);
    servo2Pending = false;
  }
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
  // a restart always leaves the feeder open; servo 2 is attached only after servo 1 has started
  servo1.attach(SERVO_1_PIN);
  servo1.write(SERVO_1_OPEN);
  delay(STAGGER_MS);
  servo2.attach(SERVO_2_PIN);
  servo2.write(SERVO_2_OPEN);

  Bridge.begin();
  Bridge.provide_safe("set_latch", set_latch);
  Bridge.provide_safe("get_latch", get_latch);
}

void loop() {
  if (latchClosed && millis() - lastCloseMs >= REOPEN_AFTER_MS) {
    moveLatch(false);
  }
  moveServo2WhenDue();
  delay(10);
}
