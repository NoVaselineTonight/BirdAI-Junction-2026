# Latch wiring

How the two latch servos (DFRobot SER0006) connect to the Arduino UNO Q, with the parts the team has: no separate 5 V supply, so the servos take their power from the board.

The same plan as a page that reads well on a phone: <https://claude.ai/artifact/R2eV8ii6dEn2Q5ypfEf7N7>. The source of that page is [`latch-wiring.html`](latch-wiring.html).

**Unplug the USB-C cable from the board before you wire anything.**

## Connections

Hold the board with the USB-C port on your left. The signal pins are on the top edge, the power pins on the bottom edge.

| # | From | To |
|---|---|---|
| 1 | Servo A signal (orange) | UNO Q **D9**, top edge |
| 2 | Servo B signal (orange) | UNO Q **D10**, top edge |
| 3 | Servo A power (red) | UNO Q **5V**, bottom edge, fifth pin from the USB-C end |
| 4 | Servo B power (red) | the same **5V** pin (join the two reds first, see below) |
| 5 | Servo B ground (brown) | UNO Q **GND**, the pin right after 5V |
| 6 | Servo A ground (brown) | UNO Q **GND**, the next pin after that |

- **Finding D9 and D10:** the long header on the top edge has a small gap. From the gap, walking left toward USB-C: D8, then D9, then D10.
- **Finding 5V and GND:** the shorter header on the bottom edge starts at the USB-C end with BOOT, IOREF, RESET, 3V3, then 5V, GND, GND, VIN.
- **Joining the two reds:** one header hole holds one jumper. Put both red wires and one jumper to 5V in the same breadboard row. With no breadboard, twist the three bare ends together and wrap them in tape.
- **Wire colours:** red = power, brown = ground, orange = signal. If the wires are gray, red and yellow: gray = ground, red = power, yellow = signal. On a standard servo plug the middle wire is power.
- **Jumpers:** the servo plugs and the board's headers are both sockets, so use jumper wires with pins on both ends.

## Do not

- **Never put 5 V on D3 or A0–A5.** Those pins take about 3.3 V only; 5 V there can destroy the microcontroller.
- **Never put a red (power) wire on a signal pin** such as D9 or D10.
- **Never swap a servo's red and brown wires**, and never wire with anything plugged in.

## The risk of powering the servos from the board

A servo pulls a burst of current when it starts to move. Here that burst comes from the board's own 5 V, and a big enough one can reset the UNO Q, which is also running the demo. What keeps it small: a light flap (cardboard), nothing that can jam, and the sketch moving the two servos one after the other, 300 ms apart. A separate 5 V supply for the servos removes the risk; that wiring is on the page under "Better, if you find a 5 V supply".

## Plugging in USB

- **Now:** one USB-C cable from the laptop to the UNO Q. It powers the board and is how the demo is started and shown. No hub, no camera.
- **Only if we later use the live camera, or the servos reset the board:** the hub's cable into the UNO Q, the camera into a USB-A port on the hub, and the Arduino's power supply into the hub's power-in port (often marked "PD"). This works only if the hub has a power-in port, and the demo then has to be reached over Wi-Fi, which is not set up yet.
- The program plays recorded feeder video today. It does not read the live camera, so the camera is not needed for the latch.
- **The "Atech" board stays unconnected** until it is identified. Nothing by the name "Atech Frame 2.2" could be found; the marking on its largest chip and the text beside its connectors would identify it.

## First power-on

Until the sketch (`board/latch/latch.ino`) is uploaded the servos do nothing, which is normal. When it starts, servo A moves to the open position and servo B follows about 300 ms later. The sketch reopens the latch by itself 30 seconds after the last close command.

## Not confirmed

- Servo wire colours come from a third-party page for the same servo family; DFRobot's own page could not be opened.
- Whether the SER0006 accepts a 3.3 V control signal (hobby servos normally do).
- How much current the UNO Q's 5V pin can give, and how much the laptop's USB-C port gives. No stall-current figure for the servo was found.
- Whether this hub has a power-in port, and whether this camera works on the board.
- The link from the program to the microcontroller has not been run on this board yet.

## The whole page as a picture

![Latch wiring page](latch-wiring.png)
