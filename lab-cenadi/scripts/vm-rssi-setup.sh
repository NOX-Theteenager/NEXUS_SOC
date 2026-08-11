#!/usr/bin/env bash
# =============================================================================
# CENADI : setup vm-rssi (10.50.40.40) — poste du RSSI / DSI
# =============================================================================
# Importe l'AC racine CENADI (pour que Firefox accepte soc.cenadi.local sans
# alerte), configure /etc/hosts et un raccourci vers la console SOC.
# =============================================================================
set -euo pipefail
SOC=10.50.0.1

echo "═══ 1/3 /etc/hosts (résolution interne) ═══"
if ! grep -q "soc.cenadi.local" /etc/hosts; then
    echo "$SOC soc.cenadi.local portail.soc.cenadi.local api.soc.cenadi.local" | sudo tee -a /etc/hosts
fi

echo "═══ 2/3 Import de l'AC racine CENADI ═══"
# Depuis le HÔTE : scp ~/pki-cenadi/cenadi-root-ca.crt rssi@10.50.40.40:/tmp/
if [[ -f /tmp/cenadi-root-ca.crt ]]; then
    sudo cp /tmp/cenadi-root-ca.crt /usr/local/share/ca-certificates/cenadi-root-ca.crt
    sudo update-ca-certificates
    echo "✓ AC racine CENADI installée dans le trust store système"
    # Firefox : utiliser le trust store système
    FF=$(find ~/.mozilla/firefox -maxdepth 1 -name "*.default*" -type d 2>/dev/null | head -1)
    [[ -n "$FF" ]] && echo 'pref("security.enterprise_roots.enabled", true);' > "$FF/user.js" && echo "✓ Firefox configuré"
else
    echo "⚠ /tmp/cenadi-root-ca.crt absent."
    echo "  Depuis le HÔTE : scp ~/pki-cenadi/cenadi-root-ca.crt rssi@10.50.40.40:/tmp/"
fi

echo "═══ 3/3 Raccourci console SOC ═══"
D=~/Bureau; [[ -d "$D" ]] || D=~/Desktop; mkdir -p "$D"
cat > "$D/NEXUS-SOC-CENADI.desktop" <<DESK
[Desktop Entry]
Version=1.0
Type=Application
Name=NEXUS SOC — Console CENADI
Comment=Console SOC souverain (RSSI/DSI)
Exec=firefox https://soc.cenadi.local:8443/app/console.html
Icon=firefox
Terminal=false
DESK
chmod +x "$D/NEXUS-SOC-CENADI.desktop"

echo
echo "✓ Setup vm-rssi terminé"
echo "  Console SOC : firefox https://soc.cenadi.local:8443/app/console.html"
echo "  Comptes     : soc@nexussoc.cm / admin (analyste), admin@nexussoc.cm / admin"
