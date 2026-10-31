#!/usr/bin/env bash
#
# AkerGate - Installation Script
# Developed by Muhammad El-Shaikh | Non-Commercial
#

set -e

if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run the installer as root: sudo ./install.sh"
  exit 1
fi

echo "[*] Installing AkerGate Multi-Auth System..."

INSTALL_LIB_DIR="/usr/local/lib/akergate"
INSTALL_BIN_DIR="/usr/local/bin"
SYSTEMD_DIR="/etc/systemd/system"

# 1. Create system directories with strict permissions
mkdir -p /etc/akergate /var/lib/akergate /var/log/akergate /etc/akergate/pam_backups
chmod 700 /etc/akergate /var/lib/akergate
chmod 755 /var/log/akergate

# 2. Copy application source
mkdir -p "$INSTALL_LIB_DIR"
cp -r akergate "$INSTALL_LIB_DIR/"

# 3. Install CLI binaries
cp bin/akergate "$INSTALL_BIN_DIR/akergate"
cp bin/akergate-pam "$INSTALL_BIN_DIR/akergate-pam"
chmod +x "$INSTALL_BIN_DIR/akergate" "$INSTALL_BIN_DIR/akergate-pam"

# Update python path in installed binaries if needed
sed -i "s|project_root = .*|project_root = Path('$INSTALL_LIB_DIR')|g" "$INSTALL_BIN_DIR/akergate"
sed -i "s|project_root = .*|project_root = Path('$INSTALL_LIB_DIR')|g" "$INSTALL_BIN_DIR/akergate-pam"

# 4. Install Systemd Sentry Service
cp systemd/akergate-sentry.service "$SYSTEMD_DIR/"
systemctl daemon-reload

echo "[+] Installation completed successfully!"
echo ""
echo "Next Steps:"
echo "1. Run the interactive setup TUI:"
echo "   sudo akergate"
echo ""
echo "2. Generate your TOTP key and scan the QR code."
echo "3. Configure your Telegram bot."
echo "4. Activate PAM protection safely."
