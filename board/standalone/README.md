# Running the board on its own

At the stand the Arduino UNO Q runs without a laptop: power, a USB-C hub with a USB webcam and an HDMI screen.
It starts the demo when it boots, finds the webcam, and shows the page full screen on the screen.
These are the files that do it. The steps below were done by hand, once, on one board (15 November 2026).
There is no install script and nothing here has been tested on a second board.

**Security.** Root SSH access, the automatic desktop login and the cleared "password must be changed" flag
all lower the board's security. Use this only on a demo board on a network you trust.

## The files

| File | What it is | Goes to (on the board) |
|---|---|---|
| `start.sh` | What the service runs: reads `config`, resets the microcontroller when the hatch is on, finds the webcam, checks it gives a picture, then starts the demo with the camera or with the recorded reel | `/home/arduino/feeder-standalone/start.sh` |
| `config` | The settings: `ROTATE`, `LATCH`, `PHOTO`, `PORT`, `PEST_THRESHOLD`, `CLOSE_FRAMES`, `OPEN_FRAMES`, `SOURCE` | `/home/arduino/feeder-standalone/config` |
| `kiosk.sh` | Full-screen Chromium on the HDMI screen, opened at `http://localhost:8088/?kiosk` once the demo answers | `/home/arduino/feeder-standalone/kiosk.sh` |
| `undo.sh` | Takes the stand-alone setup away again | `/home/arduino/feeder-standalone/undo.sh` |
| `feeder-census.service` | The systemd unit that runs `start.sh` as root and restarts it when it stops | `/etc/systemd/system/feeder-census.service` |
| `feeder-census-kiosk.desktop` | Desktop autostart entry that runs `kiosk.sh` | `/home/arduino/.config/autostart/feeder-census-kiosk.desktop` |
| `50-birdai-lightdm.conf` | Automatic desktop login of the user `arduino` | `/etc/lightdm/lightdm.conf.d/50-birdai.conf` |

The demo itself (the code, `models/`, `videos/`) must already be on the board in `/home/arduino/feeder-census`,
put there by `board/deploy.sh`.

## Install, as it was done by hand

Run the commands on the board as root (`adb shell`), with the files copied over first (`adb push`).

1. Allow SSH for root with a key only. Create `/etc/ssh/sshd_config.d/50-birdai.conf` with the two lines
   `PasswordAuthentication no` and `PermitRootLogin prohibit-password`. Run `ssh-keygen -A`, put the laptop's
   public key in `/root/.ssh/authorized_keys`, and start the SSH service (`systemctl enable --now ssh`).
   The laptop tools in `tools/feed_switch/` use this.
2. Make a 1 GB swap file: `fallocate -l 1G /swapfile`, `chmod 600 /swapfile`, `mkswap /swapfile`,
   `swapon /swapfile`, and add the line `/swapfile none swap sw 0 0` to `/etc/fstab`.
3. Run `chage -d <today, as YYYY-MM-DD> arduino`. The board ships with "password must be changed" set for that
   user, and that blocks the automatic login. This, the auto-login and the root SSH access lower the board's
   security (see above).
4. Copy the files: `start.sh`, `config`, `kiosk.sh` and `undo.sh` to `/home/arduino/feeder-standalone/` (keep
   the scripts executable); `feeder-census.service` to `/etc/systemd/system/`; `50-birdai-lightdm.conf` to
   `/etc/lightdm/lightdm.conf.d/50-birdai.conf`; `feeder-census-kiosk.desktop` to
   `/home/arduino/.config/autostart/` (the folder may have to be made, owned by `arduino`).
5. Run `systemctl daemon-reload` and `systemctl enable --now feeder-census`. Restart the board to see the
   screen log in by itself and open the page.

## Change a setting, undo

- Edit `/home/arduino/feeder-standalone/config`, then run `systemctl restart feeder-census`. The feed switch
  (`tools/feed_switch/switch.py`) does exactly this to the `SOURCE` line.
- Run `/home/arduino/feeder-standalone/undo.sh` as root to remove the service, the autostart entry, the
  auto-login, the SSH setting, the swap file, and to set "password must be changed" again. It leaves
  `/home/arduino/feeder-standalone` and `/root/.ssh/authorized_keys` in place.

## Known limits

- The webcam (USB id 1c45:6200) gave a garbled USB description behind the hub's inner hub port. It works on a
  first-level port. `start.sh` also tries a slower USB handshake and attaching the hub again.
- `start.sh` falls back to the recorded reel when the camera gives no picture within 15 s.
- After a restart of Linux the servo sketch must be reset, or `arduino-router` does not know its calls. The
  script does this through `/opt/openocd` when `LATCH=router`.
- Done by hand once, on one board. There is no tested install script; check each step.
