#!/usr/bin/env bash
#
# AkerGate - Uninstallation Script
# Safely reverts PAM before removing application files.
#

set -e

if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run the uninstaller as root: sudo ./uninstall.sh"
  exit 1
fi

echo "[*] Uninstalling AkerGate..."

# 1. Unpatch PAM first to guarantee safety
if [ -f "/usr/local/bin/akergate" ]; then
  echo "[*] Reverting PAM configuration to system default..."
  /usr/local/bin/akergate unpatch || true
fi

# 2. Stop and disable Sentry service
if systemctl is-active --quiet akergate-sentry.service; then
  echo "[*] Stopping akergate-sentry.service..."
  systemctl stop akergate-sentry.service || true
fi
if systemctl is-enabled --quiet akergate-sentry.service 2>/dev/null; then
  systemctl disable akergate-sentry.service || true
fi
rm -f /etc/systemd/system/akergate-sentry.service
systemctl daemon-reload

# 3. Remove installed binaries and libraries
rm -f /usr/local/bin/akergate
rm -f /usr/local/bin/akergate-pam
rm -rf /usr/local/lib/akergate

echo "[+] AkerGate application removed."

# 4. Optional purge of configuration and data
read -p "[?] Do you want to purge configuration and logs in /etc/akergate and /var/lib/akergate? (y/N) " confirm
if [[ "$confirm" =~ ^[Yy]$ ]]; then
  rm -rf /etc/akergate /var/lib/akergate /var/log/akergate
  echo "[+] Configuration and data purged."
else
  echo "[*] Configuration preserved in /etc/akergate."
fi

echo "[+] Uninstallation complete."
