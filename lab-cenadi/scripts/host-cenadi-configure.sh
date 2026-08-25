#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC — LAB CENADI : configuration du HÔTE en SOC SOUVERAIN
# =============================================================================
# Transforme le hôte en cœur SOC souverain CENADI :
#   1) PKI INTERNE : autorité de certification racine "CENADI Root CA" +
#      certificat serveur pour soc.cenadi.local (PAS Let's Encrypt/Cloudflare)
#   2) .env souverain : aucune dépendance Internet (SMTP interne, VT off,
#      secrets régénérés, CORS interne)
#   3) uvicorn en écoute sur 10.50.0.2 (mgmt) uniquement — pas d'exposition
#      Internet
#   4) Caddy TLS avec le certificat de l'AC interne
#
# NB : réutilise le MÊME code NEXUS SOC que le reste du dépôt. Seule la
# configuration change → preuve du produit unique bi-marché.
#
# À exécuter UNE FOIS sur le hôte, après 01-network-setup.sh.
# =============================================================================
set -euo pipefail

PROJECT_DIR=/home/noxtheteenager/Documents/Projets/NEXUS_SOC
HOST_IP="10.50.0.2"
PKI_DIR=~/pki-cenadi
ENV_CENADI="$PROJECT_DIR/.env.cenadi"

BOLD="\033[1m"; GREEN="\033[32m"; YELLOW="\033[33m"; RESET="\033[0m"
banner() { echo; echo -e "${BOLD}═══ $1 ═══${RESET}"; }

# ── 1. Vérifier le réseau mgmt ──────────────────────────────────────────────
banner "1/5 Réseau souverain nexus-cenadi-mgmt"
if ! ip -o addr show virbr-cen-mgmt 2>/dev/null | grep -q "$HOST_IP"; then
    echo "✗ Le hôte n'a pas $HOST_IP sur virbr-cen-mgmt."
    echo "  Exécuter d'abord : ./01-network-setup.sh"
    exit 1
fi
echo -e "${GREEN}✓${RESET} Hôte présent sur $HOST_IP (cœur SOC)"

# ── 2. PKI INTERNE SOUVERAINE (AC racine CENADI) ────────────────────────────
banner "2/5 PKI interne — Autorité racine CENADI"
mkdir -p "$PKI_DIR" && cd "$PKI_DIR"

if [[ ! -f "$PKI_DIR/cenadi-root-ca.crt" ]]; then
    # Autorité racine souveraine (10 ans) — la clé privée reste sur ce hôte
    openssl genrsa -out cenadi-root-ca.key 4096
    openssl req -x509 -new -nodes -key cenadi-root-ca.key -sha256 -days 3650 \
        -out cenadi-root-ca.crt \
        -subj "/C=CM/ST=Centre/L=Yaounde/O=CENADI/OU=SOC Souverain/CN=CENADI Root CA"
    echo -e "${GREEN}✓${RESET} AC racine créée (CENADI Root CA, valide 10 ans)"
else
    echo "  AC racine déjà présente"
fi

# Certificat serveur pour soc.cenadi.local (signé par l'AC interne)
if [[ ! -f "$PKI_DIR/soc.cenadi.local.crt" ]]; then
    openssl genrsa -out soc.cenadi.local.key 2048
    cat > /tmp/san.cnf <<EOF
[req]
distinguished_name=req
[san]
subjectAltName=DNS:soc.cenadi.local,DNS:portail.soc.cenadi.local,DNS:api.soc.cenadi.local,IP:$HOST_IP
EOF
    openssl req -new -key soc.cenadi.local.key \
        -subj "/C=CM/O=CENADI/CN=soc.cenadi.local" -out soc.cenadi.local.csr
    openssl x509 -req -in soc.cenadi.local.csr -CA cenadi-root-ca.crt \
        -CAkey cenadi-root-ca.key -CAcreateserial -days 825 -sha256 \
        -extfile /tmp/san.cnf -extensions san -out soc.cenadi.local.crt
    rm -f /tmp/san.cnf soc.cenadi.local.csr
    echo -e "${GREEN}✓${RESET} Certificat serveur soc.cenadi.local signé par l'AC CENADI"
fi
chmod 600 "$PKI_DIR"/*.key
echo "  → AC racine à distribuer sur les postes : $PKI_DIR/cenadi-root-ca.crt"

# ── 3. .env SOUVERAIN (aucune dépendance Internet) ──────────────────────────
banner "3/5 Génération du .env souverain"
JWT=$(openssl rand -base64 32)
PSEUDO=$(openssl rand -base64 32)
cat > "$ENV_CENADI" <<EOF
# NEXUS SOC — Configuration SOUVERAINE CENADI (généré $(date -I))
# Aucune dépendance Internet. Secrets régénérés.
DB_DSN=postgresql://nexus:change_me@localhost:5432/nexus_soc

JWT_SECRET=$JWT
PSEUDO_SECRET=$PSEUDO
PSEUDO_ENABLED=true
ACCESS_TOKEN_TTL_S=900
REFRESH_TOKEN_TTL_S=604800

# Tout est interne (pas de Cloudflare / Internet)
NEXUS_SERVER_URL=https://soc.cenadi.local
NEXUS_CORS_ORIGINS=https://soc.cenadi.local,https://portail.soc.cenadi.local

# E-mail via SMTP interne (Postfix), PAS Gmail
EMAIL_BACKEND=smtp
SMTP_HOST=smtp.cenadi.local
SMTP_PORT=25
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=soc@cenadi.local
SMTP_FROM_NAME=NEXUS SOC CENADI
SMTP_MODE=live
OTP_TTL_S=300

# Pas d'enrichissement Internet (base de menaces locale à la place)
VIRUSTOTAL_ENABLED=false

# Pas de paiement (déploiement souverain, outil interne)
CINETPAY_MODE=stub

NEXUS_BASE_URL=http://localhost:8000
NEXUS_TEST_PWD=admin
EOF
chmod 600 "$ENV_CENADI"
echo -e "${GREEN}✓${RESET} $ENV_CENADI généré (JWT + PSEUDO régénérés, aucune clé Internet)"
echo -e "${YELLOW}  → Pour activer : cp $ENV_CENADI $PROJECT_DIR/.env puis redémarrer nexus-soc${RESET}"

# ── 4. Firewall : le SOC n'écoute QUE sur les interfaces internes ───────────
banner "4/5 Firewall (le SOC n'est pas exposé à Internet)"
if command -v ufw >/dev/null; then
    sudo ufw allow in on virbr-cen-mgmt to any port 8000 proto tcp comment "SOC CENADI mgmt" || true
    sudo ufw allow in on virbr-cen-mgmt to any port 8443 proto tcp comment "SOC CENADI TLS" || true
    # Les zones app/sens/adm parlent au SOC via le routeur → arrivent sur mgmt
    echo -e "${GREEN}✓${RESET} ufw : port 8000/8443 autorisés sur virbr-cen-mgmt uniquement"
else
    echo "  ufw absent — vérifier iptables"
fi

# ── 5. Caddy TLS avec le certificat de l'AC interne ─────────────────────────
banner "5/5 Caddy TLS (certificat AC interne CENADI)"
if command -v caddy >/dev/null; then
    sudo mkdir -p /etc/caddy/cenadi
    sudo tee /etc/caddy/cenadi/Caddyfile >/dev/null <<CADDY
{
    admin off
    auto_https off
}
https://soc.cenadi.local:8443, https://portail.soc.cenadi.local:8443 {
    bind $HOST_IP
    tls $PKI_DIR/soc.cenadi.local.crt $PKI_DIR/soc.cenadi.local.key
    reverse_proxy 127.0.0.1:8000
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
    }
}
CADDY
    echo -e "${GREEN}✓${RESET} Caddy configuré (TLS via AC CENADI, bind $HOST_IP:8443)"
    echo "  Démarrer : sudo caddy run --config /etc/caddy/cenadi/Caddyfile"
else
    echo -e "${YELLOW}  Caddy absent — installer si TLS interne souhaité${RESET}"
fi

banner "CONFIGURATION SOUVERAINE TERMINÉE"
cat <<EOF

  Le HÔTE est désormais le CŒUR SOC SOUVERAIN CENADI :
    • PKI interne     : $PKI_DIR/cenadi-root-ca.crt (à pousser sur les postes)
    • .env souverain  : $ENV_CENADI (à copier en .env pour activer)
    • Écoute interne  : $HOST_IP:8000 (HTTP) / :8443 (TLS AC interne)
    • ZÉRO dépendance Internet (SMTP interne, VirusTotal off, pas de Cloudflare)

  Activer la config souveraine :
    cp $ENV_CENADI $PROJECT_DIR/.env
    sudo systemctl restart nexus-soc

  Distribuer l'AC racine au poste RSSI :
    scp $PKI_DIR/cenadi-root-ca.crt rssi@10.50.40.40:/tmp/

EOF
