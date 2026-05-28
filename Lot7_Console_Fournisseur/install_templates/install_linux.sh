#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC — Script d'installation de l'agent (Linux)
# Généré automatiquement par la console fournisseur.
# =============================================================================
# Variables injectées par le serveur NEXUS SOC :
NEXUS_SERVER="{{SERVER_URL}}"
NEXUS_TOKEN="{{BEARER_TOKEN}}"
NEXUS_HMAC_KEY="{{HMAC_KEY}}"
NEXUS_TENANT_ID="{{TENANT_ID}}"
NEXUS_AGENT_ID="{{AGENT_ID}}"
NEXUS_HOSTNAME="{{HOSTNAME}}"
NEXUS_VERSION="{{VERSION}}"
# =============================================================================

set -euo pipefail

# Couleurs
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[NEXUS]${NC} $*"; }
success() { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
fail()    { echo -e "${RED}[✗]${NC} $*"; exit 1; }

INSTALL_DIR="/usr/local/bin"
CONFIG_DIR="/etc/nexusagent"
DATA_DIR="/var/lib/nexusagent/queue"
LOG_DIR="/var/log/nexusagent"
SERVICE_USER="nexusagent"
BINARY_NAME="nexusagent"
SERVICE_NAME="nexusagent"

# --------------------------------------------------------------------------- #
# Vérifications préalables
# --------------------------------------------------------------------------- #
[[ $EUID -ne 0 ]] && fail "Ce script doit être exécuté en tant que root (sudo)."

ARCH=$(uname -m)
case "$ARCH" in
  x86_64)  ARCH_TAG="amd64"  ;;
  aarch64) ARCH_TAG="arm64"  ;;
  *)       fail "Architecture non supportée : $ARCH" ;;
esac

command -v curl  >/dev/null 2>&1 || fail "curl est requis (apt install curl / yum install curl)."
command -v systemctl >/dev/null 2>&1 || warn "systemd non détecté — le service ne sera pas enregistré automatiquement."

info "=== Installation de l'agent NEXUS SOC ==="
info "Tenant   : ${NEXUS_TENANT_ID}"
info "Hostname : ${NEXUS_HOSTNAME}"
info "Serveur  : ${NEXUS_SERVER}"
info "Arch     : ${ARCH_TAG}"

# --------------------------------------------------------------------------- #
# 1. Créer l'utilisateur système non-privilégié
# --------------------------------------------------------------------------- #
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  info "Création de l'utilisateur système '$SERVICE_USER'..."
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  success "Utilisateur '$SERVICE_USER' créé."
else
  info "Utilisateur '$SERVICE_USER' déjà présent."
fi

# --------------------------------------------------------------------------- #
# 2. Télécharger (ou utiliser la copie locale) le binaire
# --------------------------------------------------------------------------- #
BINARY_PATH="${INSTALL_DIR}/${BINARY_NAME}"
DOWNLOAD_URL="${NEXUS_SERVER}/agent/download/${NEXUS_VERSION}/linux/${ARCH_TAG}/${BINARY_NAME}"

info "Téléchargement du binaire (${NEXUS_VERSION} linux/${ARCH_TAG})..."
if curl -fsSL --connect-timeout 10 \
       -H "Authorization: Bearer ${NEXUS_TOKEN}" \
       -o "${BINARY_PATH}.tmp" \
       "${DOWNLOAD_URL}"; then
  mv "${BINARY_PATH}.tmp" "${BINARY_PATH}"
  chmod 755 "${BINARY_PATH}"
  chown root:root "${BINARY_PATH}"
  success "Binaire installé dans ${BINARY_PATH}."
else
  # Fallback : binaire inclus dans le pack offline
  OFFLINE_BIN="$(dirname "$0")/nexusagent"
  if [[ -f "$OFFLINE_BIN" ]]; then
    warn "Téléchargement impossible — utilisation du binaire offline."
    install -m 755 -o root -g root "$OFFLINE_BIN" "${BINARY_PATH}"
    success "Binaire offline installé dans ${BINARY_PATH}."
  else
    fail "Impossible d'obtenir le binaire (réseau et offline tous deux indisponibles)."
  fi
fi

# --------------------------------------------------------------------------- #
# 3. Créer les répertoires et la configuration
# --------------------------------------------------------------------------- #
info "Création des répertoires..."
mkdir -p "${CONFIG_DIR}" "${DATA_DIR}" "${LOG_DIR}"
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${DATA_DIR}" "${LOG_DIR}"
chmod 750 "${CONFIG_DIR}"

info "Écriture de la configuration..."
cat > "${CONFIG_DIR}/config.json" <<CONFIG
{
  "server_url":   "${NEXUS_SERVER}/ingest",
  "enroll_token": "${NEXUS_TOKEN}",
  "hmac_key":     "${NEXUS_HMAC_KEY}",
  "agent_id":     "${NEXUS_AGENT_ID}",
  "tenant_id":    "${NEXUS_TENANT_ID}",
  "hostname":     "${NEXUS_HOSTNAME}",
  "interval_sec": 30,
  "watch_dirs":   ["/home", "/tmp", "/var/log", "/etc"],
  "queue_dir":    "${DATA_DIR}",
  "queue_max_mb": 50,
  "tls_verify":   true
}
CONFIG
chmod 600 "${CONFIG_DIR}/config.json"
chown "${SERVICE_USER}:${SERVICE_USER}" "${CONFIG_DIR}/config.json"
success "Configuration écrite dans ${CONFIG_DIR}/config.json."

# --------------------------------------------------------------------------- #
# 4. Créer l'unité systemd
# --------------------------------------------------------------------------- #
if command -v systemctl >/dev/null 2>&1; then
  info "Création du service systemd..."
  cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=NEXUS SOC Agent
Documentation=https://nexussoc.cm/docs/agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
ExecStart=${BINARY_PATH} -config ${CONFIG_DIR}/config.json
Restart=on-failure
RestartSec=30
TimeoutStopSec=20

# Durcissement
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${DATA_DIR} ${LOG_DIR}
PrivateTmp=yes
PrivateDevices=yes
CapabilityBoundingSet=
AmbientCapabilities=

StandardOutput=append:${LOG_DIR}/agent.log
StandardError=append:${LOG_DIR}/agent.log

[Install]
WantedBy=multi-user.target
UNIT

  systemctl daemon-reload
  systemctl enable --now "${SERVICE_NAME}.service"
  success "Service '${SERVICE_NAME}' activé et démarré."
else
  warn "systemd non disponible. Démarrer l'agent manuellement :"
  warn "  sudo -u ${SERVICE_USER} ${BINARY_PATH} -config ${CONFIG_DIR}/config.json &"
fi

# --------------------------------------------------------------------------- #
# 5. Vérifier le premier contact avec le serveur
# --------------------------------------------------------------------------- #
info "Vérification de la connexion au serveur (attente jusqu'à 60 s)..."
ATTEMPTS=0
until curl -fsSL --connect-timeout 5 \
           -H "Authorization: Bearer ${NEXUS_TOKEN}" \
           "${NEXUS_SERVER}/health" >/dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  [[ $ATTEMPTS -ge 12 ]] && warn "Serveur injoignable après 60 s. Vérifiez le réseau et le token." && break
  sleep 5
done

if [[ $ATTEMPTS -lt 12 ]]; then
  success "Agent en contact avec le serveur NEXUS SOC."
fi

# --------------------------------------------------------------------------- #
# Résumé final
# --------------------------------------------------------------------------- #
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Agent NEXUS SOC installé avec succès               ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║${NC} Binaire   : ${BINARY_PATH}"
echo -e "${GREEN}║${NC} Config    : ${CONFIG_DIR}/config.json"
echo -e "${GREEN}║${NC} Logs      : ${LOG_DIR}/agent.log"
echo -e "${GREEN}║${NC} Service   : systemctl status ${SERVICE_NAME}"
echo -e "${GREEN}║${NC} Désactiver: systemctl disable --now ${SERVICE_NAME}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
warn "Ce token d'enrôlement est à usage unique. Ne pas le réutiliser."
