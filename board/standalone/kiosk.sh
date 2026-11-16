#!/bin/sh
# Shows the Feeder Census page full screen on the HDMI display once the demo answers.
xset s off -dpms 2>/dev/null
until curl -s -o /dev/null http://localhost:8088/; do sleep 2; done
exec chromium --kiosk --no-first-run --noerrdialogs --disable-infobars --disable-session-crashed-bubble \
  --password-store=basic --renderer-process-limit=1 --disable-features=Translate http://localhost:8088/?kiosk
