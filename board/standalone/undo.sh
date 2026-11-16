#!/bin/bash
# Run on the board as root to take the standalone setup away again.
systemctl disable --now feeder-census 2>/dev/null; rm -f /etc/systemd/system/feeder-census.service; systemctl daemon-reload
rm -f /home/arduino/.config/autostart/feeder-census-kiosk.desktop
rm -f /etc/lightdm/lightdm.conf.d/50-birdai.conf
systemctl disable --now ssh; rm -f /etc/ssh/sshd_config.d/50-birdai.conf
chage -d 0 arduino   # back to "password must be changed at first login"
swapoff /swapfile 2>/dev/null; rm -f /swapfile; sed -i '\#^/swapfile#d' /etc/fstab
echo "standalone setup removed; /home/arduino/feeder-standalone and /root/.ssh/authorized_keys left in place"
