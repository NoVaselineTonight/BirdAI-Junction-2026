/*
  Feeder latch for the Feeder Census demo (Arduino UNO Q, microcontroller side).

  Two DFRobot SER0006 servos (9 g, 180 degree position servos, 4.8-6 V) close a latch over the
  feeder when the Linux side sees a squirrel or a rat. The Linux program (feeder_census, --latch
  router) calls set_latch(true/false) through arduino-router; while an animal is there it repeats
  set_latch(true) at every detection. If no close command arrives for REOPEN_AFTER_MS the sketch
  opens the latch by itself, so the feeder never stays shut when the Linux side stops.

  Wiring:
  - Servo 1 signal wire (orange or yellow) to D9, servo 2 signal wire to D10.
  - Servo power (red and brown/black wires) from a separate 5 V supply that can give at least 1 A,
    not from the board's 5 V pin: two servos starting together pull more current than the board
    can give, and the board resets.
  - Join the supply's ground to a GND pin on the board, or the signal has no reference.
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

Servo servo1;
Servo servo2;

volatile bool latchClosed = false;
volatile unsigned long lastCloseMs = 0;

void moveLatch(bool closed) {
  servo1.write(closed ? SERVO_1_CLOSED : SERVO_1_OPEN);
  servo2.write(closed ? SERVO_2_CLOSED : SERVO_2_OPEN);
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
  servo1.attach(SERVO_1_PIN);
  servo2.attach(SERVO_2_PIN);
  moveLatch(false);  // a restart always leaves the feeder open

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
