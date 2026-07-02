#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Setup de vm-dsi (10.42.0.40)
# =============================================================================
# Ubuntu 22.04 Desktop : poste du DSI de MINFI.
# Rôle : ouvrir le portail dans Firefox et valider/rejeter les actions SOAR.
# =============================================================================
set -euo pipefail

echo "═══ 1/3 Ajouter soc.minfi.local à /etc/hosts ═══"
if ! grep -q "soc.minfi.local" /etc/hosts; then
    echo "10.42.0.10 soc.minfi.local api.soc.minfi.local portail.soc.minfi.local" \
        | sudo tee -a /etc/hosts
fi

echo "═══ 2/3 Faire confiance au certificat local de vm-soc ═══"
# Le certificat racine mkcert de vm-soc doit être copié pour que Firefox
# n'affiche pas d'avertissement TLS.
if [[ ! -f /usr/local/share/ca-certificates/nexus-lab-rootCA.crt ]]; then
    # Depuis vm-soc : scp ~/.local/share/mkcert/rootCA.pem dsi@10.42.0.40:/tmp/
    if [[ -f /tmp/rootCA.pem ]]; then
        sudo cp /tmp/rootCA.pem /usr/local/share/ca-certificates/nexus-lab-rootCA.crt
        sudo update-ca-certificates
        echo "✓ CA racine installée"
    else
        echo "⚠ /tmp/rootCA.pem absent."
        echo "  Depuis vm-soc, faire :"
        echo "     scp ~/.local/share/mkcert/rootCA.pem dsi@10.42.0.40:/tmp/"
        echo "  Puis relancer ce script."
    fi
fi

# Configuration Firefox pour reconnaître aussi le CA
if command -v firefox >/dev/null; then
    FF_DIR=$(find ~/.mozilla/firefox -name "*.default*" -maxdepth 1 -type d 2>/dev/null | head -1)
    if [[ -n "$FF_DIR" && -f /usr/local/share/ca-certificates/nexus-lab-rootCA.crt ]]; then
        # Créer un pref pour utiliser le trust store système
        echo 'pref("security.enterprise_roots.enabled", true);' > "$FF_DIR/user.js"
        echo "✓ Firefox configuré pour utiliser le trust store système"
    fi
fi

echo "═══ 3/3 Raccourcis bureau ═══"
DESKTOP=~/Bureau
[[ ! -d "$DESKTOP" ]] && DESKTOP=~/Desktop

mkdir -p "$DESKTOP"

cat > "$DESKTOP/NEXUS-SOC-Portail-DSI.desktop" <<DESK
[Desktop Entry]
Version=1.0
Type=Application
Name=NEXUS SOC — Portail DSI
Comment=Portail du DSI MINFI (visualisation des alertes)
Exec=firefox https://soc.minfi.local/app/login.html
Icon=firefox
Terminal=false
Categories=Network;
DESK
chmod +x "$DESKTOP/NEXUS-SOC-Portail-DSI.desktop"

echo
echo "════════════════════════════════════════════════════════════════════"
echo "✓ Setup vm-dsi terminé"
echo "════════════════════════════════════════════════════════════════════"
echo
echo "  Ouvrir le portail : double-clic sur le raccourci du bureau"
echo "  Ou depuis un terminal : firefox https://soc.minfi.local/app/login.html"
echo
echo "  Compte DSI MINFI : dsi@minfi.cm / admin"
echo "════════════════════════════════════════════════════════════════════"
