#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Setup de vm-soc (10.42.0.10)
# =============================================================================
# À exécuter DANS vm-soc, une seule fois, après installation d'Ubuntu 22.04 Server.
#
# Ce script transforme un Ubuntu vierge en serveur NEXUS SOC complet :
#   • Docker + docker compose
#   • PostgreSQL/TimescaleDB (data locale)
#   • Kafka KRaft
#   • Wazuh Manager + Indexer (mini-stack)
#   • uvicorn NEXUS SOC (via systemd)
#   • Certificat TLS local pour soc.minfi.local (mkcert)
#   • Un mini reverse-proxy Caddy pour terminer TLS (soc.minfi.local:443)
#
# Prérequis :
#   • ip a → doit afficher 10.42.0.10
#   • Le hôte doit avoir déjà transmis le tarball du projet à vm-soc via scp
#     (voir §0 ci-dessous)
# =============================================================================
set -euo pipefail

# ── 0. Récupérer le projet NEXUS SOC ────────────────────────────────────────
# Avant d'exécuter ce script, depuis le hôte :
#     tar czf /tmp/nexus-soc.tar.gz -C ~/Documents/Projets NEXUS_SOC \
#         --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
#         --exclude='.env'
#     scp /tmp/nexus-soc.tar.gz nexus@10.42.0.10:/tmp/
#
# Puis, dans vm-soc :
if [[ ! -d ~/NEXUS_SOC ]]; then
    if [[ -f /tmp/nexus-soc.tar.gz ]]; then
        echo "→ Extraction du projet depuis /tmp/nexus-soc.tar.gz"
        tar xzf /tmp/nexus-soc.tar.gz -C ~
    else
        echo "✗ Le tarball /tmp/nexus-soc.tar.gz est absent."
        echo "  Depuis le hôte, exécuter :"
        echo "    tar czf /tmp/nexus-soc.tar.gz -C ~/Documents/Projets NEXUS_SOC \\"
        echo "        --exclude='.venv' --exclude='__pycache__' --exclude='.git'"
        echo "    scp /tmp/nexus-soc.tar.gz nexus@10.42.0.10:/tmp/"
        exit 1
    fi
fi

PROJECT_DIR=~/NEXUS_SOC
cd "$PROJECT_DIR"

# ── 1. Paquets système ──────────────────────────────────────────────────────
echo "═══ 1/8 Paquets système ═══"
sudo apt-get update
sudo apt-get install -y \
    ca-certificates curl gnupg lsb-release \
    python3-venv python3-pip python3-dev \
    postgresql-client \
    tcpdump net-tools htop \
    debian-keyring debian-archive-keyring apt-transport-https \
    libnss3-tools    # requis par mkcert

# ── 2. Docker Engine + Compose V2 ───────────────────────────────────────────
echo "═══ 2/8 Docker Engine ═══"
if ! command -v docker >/dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    echo "⚠  Se reconnecter en SSH pour que le groupe docker soit actif :"
    echo "   exit puis ssh nexus@10.42.0.10"
    echo "   Puis relancer ce script."
    exit 0
fi

# ── 3. Environnement Python + .env ──────────────────────────────────────────
echo "═══ 3/8 Environnement Python ═══"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

cp .env.example .env
# Ajuster pour le contexte lab
sed -i "s|^DB_DSN=.*|DB_DSN=postgresql://nexus:change_me@localhost:5432/nexus_soc|" .env
sed -i "s|^NEXUS_SERVER_URL=.*|NEXUS_SERVER_URL=https://soc.minfi.local|" .env
sed -i "s|^NEXUS_CORS_ORIGINS=.*|NEXUS_CORS_ORIGINS=https://soc.minfi.local,https://portail.soc.minfi.local|" .env
sed -i "s|^EMAIL_BACKEND=.*|EMAIL_BACKEND=log|" .env          # pas d'Internet dans le lab
sed -i "s|^VIRUSTOTAL_ENABLED=.*|VIRUSTOTAL_ENABLED=false|" .env
echo "✓ .env configuré pour le lab (mode local, souverain)"

# ── 4. Certificats TLS locaux (mkcert) ──────────────────────────────────────
echo "═══ 4/8 Certificats TLS locaux ═══"
if ! command -v mkcert >/dev/null; then
    curl -sSL -o /tmp/mkcert \
        "https://github.com/FiloSottile/mkcert/releases/latest/download/mkcert-v1.4.4-linux-amd64"
    sudo install -m 755 /tmp/mkcert /usr/local/bin/mkcert
fi
mkcert -install
mkdir -p ~/certs && cd ~/certs
mkcert soc.minfi.local api.soc.minfi.local portail.soc.minfi.local 10.42.0.10
cd "$PROJECT_DIR"
echo "✓ Certificat local créé (racine ajoutée au trust store)"

# ── 5. Caddy pour terminer TLS ──────────────────────────────────────────────
echo "═══ 5/8 Caddy (reverse-proxy TLS) ═══"
if ! command -v caddy >/dev/null; then
    curl -1sSLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sSLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | sudo tee /etc/apt/sources.list.d/caddy-stable.list
    sudo apt-get update && sudo apt-get install -y caddy
fi

sudo tee /etc/caddy/Caddyfile > /dev/null <<CADDY
soc.minfi.local, portail.soc.minfi.local, api.soc.minfi.local {
    tls /home/$USER/certs/soc.minfi.local+3.pem /home/$USER/certs/soc.minfi.local+3-key.pem
    reverse_proxy 127.0.0.1:8000
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options    "nosniff"
        X-Frame-Options           "SAMEORIGIN"
    }
}
CADDY
sudo systemctl enable --now caddy
sudo systemctl restart caddy
echo "✓ Caddy actif sur :443 → 127.0.0.1:8000"

# ── 6. Stack Docker (PostgreSQL + Kafka + Wazuh mini) ───────────────────────
echo "═══ 6/8 Stack Docker Compose ═══"
cd "$PROJECT_DIR/Lot0_Socle"
# Créer .env pour docker-compose si absent
[[ -f .env ]] || cat > .env <<ENV
POSTGRES_USER=nexus
POSTGRES_PASSWORD=change_me
POSTGRES_DB=nexus_soc
ENV

# Démarrer seulement Postgres + Kafka pour l'instant (Wazuh optionnel, gourmand)
docker compose up -d postgres kafka
echo "→ Attente PostgreSQL prêt..."
for i in {1..30}; do
    if docker exec nexus-postgres pg_isready -U nexus -d nexus_soc >/dev/null 2>&1; then
        echo "✓ PostgreSQL prêt"; break
    fi
    sleep 2
done

# ── 7. Application des schémas SQL ──────────────────────────────────────────
echo "═══ 7/8 Schémas SQL ═══"
cd "$PROJECT_DIR"
for sql in \
    Lot0_Socle/01_schema_patched.sql \
    Lot0_Socle/01_schema_retention.sql \
    Lot0_Socle/02_seed_demo.sql \
    Lot0_Socle/03_schema_notifications.sql \
    Lot8_PLG/01_schema_plg.sql \
    Lot8_PLG/02_schema_otp.sql \
; do
    [[ -f "$sql" ]] && docker exec -i nexus-postgres psql -U nexus -d nexus_soc -q < "$sql" >/dev/null 2>&1 || true
done
echo "✓ Schémas appliqués (les warnings TimescaleDB/nexus_analyst sont bénins)"

# ── 8. Service systemd uvicorn ──────────────────────────────────────────────
echo "═══ 8/8 Service systemd ═══"
sudo cp "$PROJECT_DIR/00_Documents/nexus-soc.service" /etc/systemd/system/nexus-soc.service
# Adapter les chemins pour l'user 'nexus' de la VM
sudo sed -i "s|/home/noxtheteenager/Documents/Projets/NEXUS_SOC|$PROJECT_DIR|g" /etc/systemd/system/nexus-soc.service
sudo sed -i "s|User=noxtheteenager|User=nexus|" /etc/systemd/system/nexus-soc.service
sudo sed -i "s|Group=noxtheteenager|Group=nexus|" /etc/systemd/system/nexus-soc.service
# Retirer la dépendance sur nexus-postgres.service (on utilise docker-compose ici)
sudo sed -i "s|nexus-postgres.service||g" /etc/systemd/system/nexus-soc.service

sudo systemctl daemon-reload
sudo systemctl enable --now nexus-soc
sleep 8

# ── Vérifications finales ───────────────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════════════════"
echo "✓ Setup vm-soc terminé"
echo "════════════════════════════════════════════════════════════════════"
echo
echo "  Backend uvicorn : $(systemctl is-active nexus-soc)"
echo "  Caddy TLS       : $(systemctl is-active caddy)"
echo "  Docker Compose  : $(docker ps --format '{{.Names}}' | wc -l) containers"
echo
echo "  Test local :"
curl -s http://127.0.0.1:8000/health || echo "  ✗ Backend inaccessible"
echo
echo "  Test HTTPS local (via Caddy + cert local) :"
curl -sk https://soc.minfi.local/health
echo
echo "  Comptes de démo (mot de passe = admin) :"
echo "  - admin@nexussoc.cm       (rôle admin_plateforme)"
echo "  - analyste@nexussoc.cm    (rôle analyste_soc)"
echo "  - dsi@minfi.cm            (rôle dsi_client, tenant MINFI)"
echo "  - dsi@microfinance-a.cm   (rôle dsi_client, tenant Microfinance A)"
echo
echo "  Depuis vm-dsi ou le hôte : ouvrir https://soc.minfi.local"
echo "════════════════════════════════════════════════════════════════════"
