#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Configuration du HÔTE Ubuntu pour jouer le rôle de vm-soc
# =============================================================================
# Ce script REMPLACE l'ancien vm-soc-setup.sh. Puisque le hôte a déjà :
#   ✓ nexus-soc.service (uvicorn en systemd)
#   ✓ cloudflared.service (tunnel HTTPS vers nexussoc.cm)
#   ✓ PostgreSQL / TimescaleDB (container Docker)
#   ✓ Les schémas SQL appliqués + seed démo
#
# ...il ne reste qu'à :
#   1) faire écouter uvicorn sur 10.42.0.1 (en plus de 127.0.0.1)
#   2) autoriser au firewall les VMs du lab à joindre le port 8000
#   3) installer Caddy pour la terminaison TLS local (soc.nexus.local)
#   4) exporter le CA racine mkcert pour que les VMs le fassent confiance
#
# À exécuter UNE SEULE FOIS depuis le hôte.
# =============================================================================
set -euo pipefail

PROJECT_DIR=/home/noxtheteenager/Documents/Projets/NEXUS_SOC
HOST_LAB_IP="10.42.0.1"
CERT_DIR=~/certs-lab

if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "✗ $PROJECT_DIR introuvable"
    exit 1
fi

BOLD="\033[1m"; GREEN="\033[32m"; YELLOW="\033[33m"; RESET="\033[0m"
banner() { echo; echo -e "${BOLD}═══ $1 ═══${RESET}"; }

# ── 1. Vérifier que le réseau de management nexus-mgmt est créé ─────────────
banner "1/6 Vérification du réseau libvirt nexus-mgmt"
if ! virsh net-info nexus-mgmt >/dev/null 2>&1; then
    echo "✗ Le réseau libvirt 'nexus-mgmt' n'existe pas."
    echo "  Exécuter d'abord : ./lab/01-network-setup.sh"
    exit 1
fi
if ! ip -o addr show virbr-mgmt 2>/dev/null | grep -q "$HOST_LAB_IP"; then
    echo "✗ Le hôte n'a pas $HOST_LAB_IP sur virbr-mgmt."
    echo "  virsh net-start nexus-mgmt"
    exit 1
fi
echo -e "${GREEN}✓${RESET} Réseau OK, hôte a $HOST_LAB_IP sur virbr-mgmt"

# ── 2. Vérifier que uvicorn écoute sur 0.0.0.0 (nexus-soc.service à jour) ──
banner "2/6 Binding uvicorn (0.0.0.0:8000)"
if ! ss -ltn 2>/dev/null | grep -qE "0\.0\.0\.0:8000|:::8000"; then
    echo -e "${YELLOW}⚠${RESET}  uvicorn écoute seulement sur 127.0.0.1 :"
    ss -ltn 2>/dev/null | grep 8000 | head -3
    echo
    echo "  Mettre à jour le service (fichier déjà corrigé dans le repo) :"
    echo "    sudo cp $PROJECT_DIR/00_Documents/nexus-soc.service /etc/systemd/system/"
    echo "    sudo systemctl daemon-reload && sudo systemctl restart nexus-soc"
    echo "  Puis relancer ce script."
    exit 1
fi
echo -e "${GREEN}✓${RESET} uvicorn écoute sur 0.0.0.0:8000"

# ── 3. Test de joignabilité depuis l'IP lab ─────────────────────────────────
banner "3/6 Test /health depuis $HOST_LAB_IP"
if curl -s --max-time 3 "http://${HOST_LAB_IP}:8000/health" | grep -q '"status":"ok"'; then
    echo -e "${GREEN}✓${RESET} /health répond via $HOST_LAB_IP"
else
    echo -e "${YELLOW}⚠${RESET}  /health ne répond PAS via $HOST_LAB_IP."
    echo "  Cause probable : ufw bloque le port 8000 sur virbr-mgmt."
    echo "  Fix : sudo ufw allow in on virbr-mgmt to any port 8000 proto tcp"
    exit 1
fi

# ── 4. Ouvrir le firewall pour les VMs du lab ───────────────────────────────
banner "4/6 Règles firewall (ufw) pour virbr-mgmt"
if command -v ufw >/dev/null; then
    if sudo ufw status | grep -qE "10\.42\.0|virbr-mgmt"; then
        echo -e "${GREEN}✓${RESET} Règle déjà présente"
    else
        # Autoriser tout depuis le sous-réseau du lab vers les services SOC
        sudo ufw allow in on virbr-mgmt to any port 8000 proto tcp comment "NEXUS SOC lab" || true
        sudo ufw allow in on virbr-mgmt to any port 8443 proto tcp comment "NEXUS SOC TLS lab" || true
        sudo ufw allow in on virbr-mgmt to any port 514  proto udp comment "Syslog lab" || true
        echo -e "${GREEN}✓${RESET} Règles ufw ajoutées pour virbr-mgmt"
    fi
else
    echo "  ufw absent — aucune règle à modifier (iptables direct)"
fi

# ── 5. Certificats TLS locaux (mkcert) pour soc.nexus.local ─────────────────
banner "5/6 Certificats mkcert pour soc.nexus.local"
if ! command -v mkcert >/dev/null; then
    curl -sSL -o /tmp/mkcert \
        "https://github.com/FiloSottile/mkcert/releases/latest/download/mkcert-v1.4.4-linux-amd64"
    sudo install -m 755 /tmp/mkcert /usr/local/bin/mkcert
fi
mkcert -install 2>/dev/null || true

mkdir -p "$CERT_DIR" && cd "$CERT_DIR"
if [[ ! -f "$CERT_DIR/soc.nexus.local+3.pem" ]]; then
    mkcert soc.nexus.local api.soc.nexus.local portail.soc.nexus.local "$HOST_LAB_IP"
    echo -e "${GREEN}✓${RESET} Certificat créé dans $CERT_DIR"
fi

# Exporter le CA racine pour distribution aux VMs
CA_ROOT=$(mkcert -CAROOT)
cp "$CA_ROOT/rootCA.pem" "$CERT_DIR/rootCA.pem"
echo "  CA racine copié → $CERT_DIR/rootCA.pem"
echo "  (à distribuer sur vm-cible et vm-dsi via scp)"

# ── 6. Caddy pour terminer TLS sur 10.42.0.1:8443 (soc.nexus.local) ─────────
banner "6/6 Caddy (reverse-proxy TLS pour le lab)"
if ! command -v caddy >/dev/null; then
    echo "→ Installation Caddy..."
    curl -1sSLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sSLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt-get update && sudo apt-get install -y caddy
fi

# Config Caddy : écoute uniquement sur 10.42.0.1:8443 (pas sur les autres IF)
# → n'expose PAS le SOC hors du lab, garde le tunnel nexussoc.cm intact.
sudo mkdir -p /etc/caddy/lab
sudo tee /etc/caddy/lab/Caddyfile > /dev/null <<CADDY
# NEXUS SOC LAB — Caddyfile dédié au lab (bind 10.42.0.1 / virbr-mgmt)
# Ne PAS remplacer /etc/caddy/Caddyfile principal — chargé en parallèle.
{
    admin off
    auto_https off
}

https://soc.nexus.local:8443, https://portail.soc.nexus.local:8443, https://api.soc.nexus.local:8443 {
    bind 10.42.0.1
    tls $CERT_DIR/soc.nexus.local+3.pem $CERT_DIR/soc.nexus.local+3-key.pem
    reverse_proxy 127.0.0.1:8000
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options    "nosniff"
        X-Frame-Options           "SAMEORIGIN"
    }
}
CADDY

# Service systemd dédié (pour ne pas casser Caddy principal si présent)
sudo tee /etc/systemd/system/nexus-lab-caddy.service > /dev/null <<UNIT
[Unit]
Description=NEXUS SOC Lab — Caddy TLS (10.42.0.1:8443)
After=network-online.target nexus-soc.service libvirtd.service

[Service]
ExecStart=/usr/bin/caddy run --config /etc/caddy/lab/Caddyfile
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now nexus-lab-caddy

sleep 2
if curl -sk --max-time 3 "https://soc.nexus.local:8443/health" 2>/dev/null | grep -q '"status":"ok"'; then
    echo -e "${GREEN}✓${RESET} Caddy actif sur https://soc.nexus.local:8443"
else
    echo -e "${YELLOW}⚠${RESET}  Caddy démarré mais /health via TLS ne répond pas encore."
    echo "  Vérifier : sudo journalctl -u nexus-lab-caddy -n 20"
fi

# ── Résumé ──────────────────────────────────────────────────────────────────
banner "CONFIGURATION HÔTE TERMINÉE"

cat <<EOF

  Le HÔTE joue désormais 3 rôles :
  ────────────────────────────────
    • Serveur NEXUS SOC pour le lab   → 10.42.0.1:8000  (HTTP)
                                       → 10.42.0.1:8443 (HTTPS via Caddy)
    • Tunnel Cloudflare               → https://nexussoc.cm
    • Poste de démo (Firefox)         → pour la démo PLG SaaS

  Vérifications :
    • Depuis le hôte    : curl http://127.0.0.1:8000/health
    • Depuis le hôte    : curl -k https://soc.nexus.local:8443/health
    • Depuis vm-cible   : curl http://10.42.0.1:8000/health
    • Depuis vm-dsi     : https://soc.nexus.local:8443/app/portail.html

  Distribuer le CA racine aux VMs (pour que Firefox accepte le certif) :
    scp $CERT_DIR/rootCA.pem dsi@10.42.10.40:/tmp/rootCA.pem
    (à faire après création de vm-dsi)

EOF
