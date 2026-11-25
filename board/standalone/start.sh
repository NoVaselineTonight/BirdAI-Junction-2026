#!/bin/bash
# Feeder Census, standalone on the Arduino UNO Q: starts the demo with the USB webcam when one is plugged in,
# otherwise with the recorded reel. Settings are in /home/arduino/feeder-standalone/config.
cd /home/arduino/feeder-census || exit 1
SOURCE=camera; ROTATE=180; LATCH=router; PHOTO=5; PORT=8088; PEST_THRESHOLD=0.8; CLOSE_FRAMES=3; OPEN_FRAMES=5
[ -f /home/arduino/feeder-standalone/config ] && . /home/arduino/feeder-standalone/config
if [ "$LATCH" = router ]; then
  # After a restart of Linux the servo sketch is no longer known to arduino-router. A reset of the
  # microcontroller makes the sketch register its calls again (it also puts the hatch at its open angle).
  for i in $(seq 1 30); do [ -S /var/run/arduino-router.sock ] && break; sleep 1; done
  (cd /opt/openocd && bin/openocd -d0 -s share/openocd/scripts -s /opt/openocd -f openocd_gpiod.cfg -c "init; reset run; shutdown") >/dev/null 2>&1
  sleep 4
fi
# Find the USB webcam: the first capture device that is not the board's own video decoder.
find_cam() {
  for d in /sys/class/video4linux/video*; do
    [ -e "$d/name" ] || continue
    case "$(cat $d/name)" in *venus*|*decoder*|*encoder*) continue;; esac
    [ "$(cat $d/index 2>/dev/null)" = 0 ] && { echo "/dev/$(basename $d)"; return; }
  done
}
# Our webcam (1c45:6200) gives a garbled USB description through the hub at power-on. A slower handshake
# (usbcore quirks g = delay at init, n = pause after control messages) and attaching its hub again fixes it.
echo "1c45:6200:gn" > /sys/module/usbcore/parameters/quirks 2>/dev/null
CAM=""
for try in 1 2 3; do
  for i in $(seq 1 8); do CAM=$(find_cam); [ -n "$CAM" ] && break; sleep 2; done
  [ -n "$CAM" ] && break
  for v in /sys/bus/usb/devices/*/idVendor; do
    dev=$(dirname $v)
    [ "$(cat $v)" = 1c45 ] && [ "$(cat $dev/idProduct)" = 6200 ] || continue
    hub=$(basename $(dirname $(readlink -f $dev)))
    echo "feeder-standalone: webcam not usable, attaching its hub $hub again (try $try)"
    echo $hub > /sys/bus/usb/drivers/usb/unbind 2>/dev/null; sleep 3; echo $hub > /sys/bus/usb/drivers/usb/bind 2>/dev/null
  done
done
# SOURCE=reel in the config means: play the recorded feeder footage even when a webcam is plugged in.
[ "$SOURCE" = reel ] && CAM=""
# Only use the camera if it really gives a picture within 15 s; otherwise play the reel.
if [ -n "$CAM" ] && ! timeout 15 .venv/bin/python -c "import cv2,sys
cap=cv2.VideoCapture(sys.argv[1], cv2.CAP_V4L2); ok,_=cap.read(); cap.release(); sys.exit(0 if ok else 1)" "$CAM" >/dev/null 2>&1; then
  echo "feeder-standalone: camera $CAM gives no picture"
  CAM=""
fi
if [ -n "$CAM" ]; then
  echo "feeder-standalone: camera $CAM"
  # The webcam keeps its own census (and its evidence photos, which go beside the database), so what it sees
  # never mixes with the reel's counts. The latch angles stay the ones the calibration page saves.
  mkdir -p data/camera
  exec .venv/bin/python -m feeder_census --camera "$CAM" --camera-rotate "$ROTATE" --detector auto --latch "$LATCH" \
    --db data/camera/census.db --latch-angles data/latch_angles.json --port "$PORT" --photo-every-s "$PHOTO" --pest-threshold "$PEST_THRESHOLD" --latch-close-frames "$CLOSE_FRAMES" --latch-open-frames "$OPEN_FRAMES"
fi
echo "feeder-standalone: no camera found, playing the recorded reel"
exec .venv/bin/python -m feeder_census --videos videos --detector auto --latch "$LATCH" --db data/census.db --port "$PORT" \
  --photo-every-s "$PHOTO" --pest-threshold "$PEST_THRESHOLD" --latch-close-frames "$CLOSE_FRAMES" --latch-open-frames "$OPEN_FRAMES"
