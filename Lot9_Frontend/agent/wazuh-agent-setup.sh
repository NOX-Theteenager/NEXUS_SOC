#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC — LAB CENADI : enrôlement d'un agent Wazuh vers le manager souverain
# -----------------------------------------------------------------------------
# Complète le collecteur NEXUS (télémétrie -> IA) par la couche SIEM par règles
# (logs SSH/sudo, intégrité de fichiers, rootcheck, MITRE, conformité).
# À lancer SUR chaque VM à superviser. Manager = HÔTE (10.50.0.1).
#
#   WAZUH_AGENT_NAME=SRV-APP-GOV-01 sudo -E bash wazuh-agent-setup.sh
# =============================================================================
set -euo pipefail

MANAGER=${WAZUH_MANAGER:-10.50.0.1}
NAME=${WAZUH_AGENT_NAME:-$(hostname)}
VERSION=${WAZUH_VERSION:-4.9.0-1}   # aligné sur le manager 4.9.0

echo "═══ Agent Wazuh → manager ${MANAGER}  (nom: ${NAME}, v${VERSION}) ═══"

# 0. Connectivité au service d'enrôlement (1515) + comms (1514)
for p in 1515 1514; do
  if ! timeout 3 bash -c "cat < /dev/null > /dev/tcp/${MANAGER}/${p}" 2>/dev/null; then
    echo "✗ ${MANAGER}:${p} injoignable — vérifier la route vers le SOC."; exit 1
  fi
done
echo "✓ Manager joignable (1514 + 1515)"

# 1. Dépôt Wazuh (clé GPG + source apt)
echo "═══ 1/3 Dépôt Wazuh ═══"
if [ ! -f /usr/share/keyrings/wazuh.gpg ]; then
  curl -fsSL https://packages.wazuh.com/key/GPG-KEY-WAZUH \
    | gpg --batch --yes --no-default-keyring \
          --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import
  chmod 644 /usr/share/keyrings/wazuh.gpg
fi
echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" \
  > /etc/apt/sources.list.d/wazuh.list
apt-get update -qq

# 2. Installation (auto-config manager + nom via variables du paquet)
echo "═══ 2/3 Installation de wazuh-agent ═══"
WAZUH_MANAGER="${MANAGER}" WAZUH_AGENT_NAME="${NAME}" \
  apt-get install -y "wazuh-agent=${VERSION}" || \
  WAZUH_MANAGER="${MANAGER}" WAZUH_AGENT_NAME="${NAME}" apt-get install -y wazuh-agent

# Empêche une montée de version qui désynchroniserait agent/manager
apt-mark hold wazuh-agent >/dev/null 2>&1 || true

# 3. Démarrage + enrôlement auto (authd sur 1515)
echo "═══ 3/3 Démarrage + enrôlement ═══"
systemctl daemon-reload
systemctl enable --now wazuh-agent

sleep 5
echo
if systemctl is-active --quiet wazuh-agent; then
  echo "✓ Agent ${NAME} actif. Enrôlement auprès de ${MANAGER}."
  echo "  Côté manager : il apparaît dans le dashboard Wazuh → Agents (~1 min)."
  echo "  Test d'alerte : provoquer un échec SSH ou 'sudo cat /etc/shadow'."
else
  echo "⚠ Agent installé mais non actif — voir : journalctl -u wazuh-agent -n 30"
fi
