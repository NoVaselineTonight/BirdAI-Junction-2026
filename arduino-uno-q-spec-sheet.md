---
title: "Arduino UNO Q: spec sheet"
subtitle: "The board we have (ABX00162, 2 GB / 16 GB), and what it means for the feeder camera"
date: "14 November 2026"
---

# In one sentence

A UNO-sized board with two computers on it: a quad-core Linux computer (Qualcomm QRB2210, Debian 13) and a real-time microcontroller (STM32U585, Zephyr). The two talk to each other over an RPC bridge.

# Our unit

These values were read from the board itself over adb on 14 November 2026.

| Item | Value |
|---|---|
| Model | Arduino UNO Q, **ABX00162** (2 GB RAM / 16 GB eMMC) |
| Device-tree name | `Arduino SA,Imola` |
| OS | Debian GNU/Linux 13 (trixie), kernel 6.16, aarch64 |
| CPU | 4 cores, maximum 2.016 GHz |
| RAM visible to Linux | 1.7 GiB total, about 1.3 GiB available when idle, no swap |
| Storage | 14.6 GB eMMC, root partition 9.3 GB with **3.0 GB free** |
| Wi-Fi | `wlan0` up |
| Software on board | Python 3.13.5, Docker 26.1.5, Arduino App Lab |
| MCU board ID | `arduino:zephyr:unoq` on `/dev/ttyACM0` |
| Camera | **None attached.** `/dev/video0` is the hardware video decoder (`qcom-venus-decoder`), not a camera |
| Sensors | Modulino Thermo (SHT31 revision, I2C address 0x45) on Qwiic |

# Hardware

From the official datasheet (ABX00162-ABX00173) unless marked otherwise.

## Linux side (MPU)

| Item | Spec |
|---|---|
| Chip | Qualcomm Dragonwing QRB2210 |
| CPU | 4 × Arm Cortex-A53, 2.0 GHz, 64-bit |
| GPU | Adreno 702 at 845 MHz. OpenGL ES 3.1, Vulkan 1.0 (the hardware supports 1.1), OpenCL 2.0. It shares RAM with the CPU |
| ISP | Two ISPs: 13 MP + 13 MP, or one 25 MP sensor at 30 fps |
| Video codec | H.264 and H.265 encode and decode, VP9 decode only, up to 1080p |
| NPU | **None.** The datasheet lists none. One Arduino marketing line mentions an NPU, but the same page's spec card says "GPU + DSP + ISP" |
| RAM | 2 GB LPDDR4X (4 GB on ABX00173) |
| Storage | 16 GB eMMC (32 GB on ABX00173) |

## Microcontroller side (MCU)

| Item | Spec |
|---|---|
| Chip | STM32U585, Arm Cortex-M33 at 160 MHz with FPU |
| Memory | 2 MB flash, 786 kB SRAM |
| Firmware | Arduino core on Zephyr OS |
| Talking to Linux | `Arduino_RouterBridge` (MessagePack-RPC through the `arduino-router` service) |

## Wireless

- Wi-Fi 5 (802.11a/b/g/n/ac), on both 2.4 and 5 GHz.
- Bluetooth 5.1.
- Module: WCBN3536A (Qualcomm WCN3980), on-board PCB antenna.

## Power

| Input | Spec |
|---|---|
| USB-C | 5 V (4.5–5.5 V), up to 3 A. Power Delivery asks for 5 V / 3 A and nothing higher |
| VIN | 7–24 V DC on the analog header and JMEDIA. Reverse-polarity protected |
| 5V_SYS pin | 5 V output, up to 3 A |
| Operating temperature | **−10 to +60 °C** ambient |

## Pins and buses

All UNO header pins are **3.3 V logic**. Most digital pins tolerate 5 V as inputs. Two exceptions:

- **D3** tolerates 3.6 V at most.
- **A0–A5**, and any pin used as analog, tolerate no more than 3.3 V + 0.3 V.

| Item | Spec |
|---|---|
| Digital pins | 47 driven by the MCU: 22 on the UNO headers and 25 on JMISC |
| Analog inputs | A0–A5. The ADC is 14-bit, and 12, 10 or 8 bits can be selected |
| DAC | 2 outputs, on A0 and A1, 8–12 bit |
| PWM | D3, D5, D6, D9, D10, D11. 8-bit by default, fixed at 500 Hz |
| UART | D0/D1 (`Serial1`) |
| I2C | D20/D21 (`Wire`), A4/A5, and Qwiic (`Wire1`) |
| SPI | D10–D13 and the JSPI header |
| CAN | FDCAN on D4/D5. Needs an external transceiver |
| Qwiic | 4-pin, 3.3 V, for Modulino modules. **It is on the MCU, so Linux cannot see it** |

## On-board LEDs

- An 8 × 13 blue LED matrix, driven by the MCU, with 8 brightness levels. It shows a boot logo for 20–30 s while Linux starts.
- Four RGB LEDs: LEDs 1 and 2 belong to Linux (`/sys/class/leds`), LEDs 3 and 4 to the MCU.

## Connectors underneath

| Connector | What it carries |
|---|---|
| JMEDIA (60-pin, 1.8 V) | MIPI-DSI (4 lanes), **two MIPI-CSI-2 camera ports**, camera I2C and clocks, VIN |
| JMISC (60-pin, 1.8 V and 3.3 V) | Analog audio (mic, headphone, line out), the MCU's parallel camera bus, extra MCU pins, power rails |
| JCTL (10-pin, 1.8 V) | Boot, console UART, reset |

The board has no plug-in camera socket. The CSI signals exist only on this connector.

## USB-C

- USB 3.1 Gen 1 (5 Gb/s).
- DisplayPort video output. 1280 × 720 works best, and USB slows down while video is on.
- Through a dongle with its own PD power supply you can attach HDMI, Ethernet, a USB camera, audio and storage.

## Size and price

- 68.58 × 53.34 mm, the standard UNO footprint and hole pattern. No official weight figure.
- EUR 59.90 / USD 59 for our 2 GB board. The 4 GB board is USD 79. Arduino raised both prices in July 2026 because memory got more expensive (they were USD 44 and 59).

# What this means for the feeder camera

- **No NPU, so the detector runs on the CPU.** Four A53 cores at 2 GHz handle a small int8 detector, such as a YOLO nano-class model in TFLite or ONNX, at a frame every few seconds. That rate is enough for counting. Running on the GPU through OpenCL may help, but nobody has tested it on this board. Don't plan for real-time video.
- **About 1.3 GB of RAM is free.** That is enough for one small model and the counting logic. It is not enough for a large model plus a browser on the board. Arduino recommends the 4 GB version for standalone desktop use.
- **3 GB of free disk.** Store the best frame per record, not continuous video. A few hundred JPEGs at 100–200 kB each is fine. Hours of footage are not.
- **The camera has two routes:**
  - **USB webcam (easiest).** It needs a USB-C dongle with its own PD power supply. **That dongle cuts the PC's USB data link**, so in that setup reach the board over Wi-Fi with `adb connect` or SSH.
  - **MIPI-CSI camera.** It needs the UNO Media Carrier (ASX00083). Only the Raspberry Pi IMX219 camera is supported so far.
- **The temperature rating is a real problem.** The board is rated down to −10 °C, and a Finnish feeder in January sees colder than that. For the demo this doesn't matter. A real deployment needs an insulated or indoor enclosure, for example a board behind a window looking out.
- **The MCU side is useful for a wake-up sensor.** A distance or motion Modulino on Qwiic can tell Linux over Bridge that a bird has landed, so the detector runs only then.

# How we use it from the laptop

| Task | Command or note |
|---|---|
| Connect | Plug in USB-C directly with a data cable. **Do not use the dongle** for PC data |
| Upload an MCU sketch | `arduino-cli upload -b arduino:zephyr:unoq -p /dev/ttyACM0 <sketch>` |
| Read sketch output | `Serial` does not reach the PC. Use `Bridge.begin(); Monitor.begin(); Monitor.println(...)`, then `adb forward tcp:7500 tcp:7500` and read TCP 127.0.0.1:7500 |
| Linux shell | `adb shell` (logs in as root) |
| App Lab | `~/Applications/ArduinoAppLab_0.12.0_Linux_x86-64/` |

# Sources

- Arduino UNO Q datasheet ABX00162-ABX00173: docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf
- UNO Q user manual: docs.arduino.cc/tutorials/uno-q/user-manual/
- UNO Media Carrier user manual: docs.arduino.cc/tutorials/uno-media-carrier/user-manual
- Arduino blog on pricing, 26 June 2026: blog.arduino.cc
- "Our unit" table: read from the board over adb, 14 November 2026.
- Not found in an official source: weight, and the EUR price of the 4 GB board.
