#!/usr/bin/env bash
# =============================================================================
# CENADI : setup vm-app-gov (10.50.20.20) — serveur applicatif gouvernemental
# =============================================================================
# Déploie le VRAI collecteur de télémétrie NEXUS (mesures réelles : compteurs TCP
# du noyau, sessions, accès fichiers sensibles), pas un émetteur de JSON fabriqué.
# Le collecteur est pur stdlib (python3 + iproute2), aucune dépendance lourde.
# =============================================================================
set -euo pipefail

SOC=${SOC:-10.50.0.2}
export SOC_URL="http://${SOC}:8000"
AGENT_HOSTNAME=${AGENT_HOSTNAME:-SRV-APP-GOV-01}
PERIMETRE=${PERIMETRE:-SIGIPES}        # périmètre supervisé existant (voir seed)
INSTALL_DIR=/opt/nexus-agent

echo "═══ 0/4 Connectivité SOC ═══"
curl -s "${SOC_URL}/health" | grep -q '"status":"ok"' || { echo "✗ SOC injoignable ($SOC_URL)"; exit 1; }
echo "✓ SOC souverain accessible"

echo "═══ 1/4 Paquets (python3 + iproute2 pour 'ss') ═══"
sudo apt-get update -qq && sudo apt-get install -y -qq python3 iproute2 curl

echo "═══ 2/4 Récupération du collecteur réel depuis le SOC ═══"
sudo mkdir -p "$INSTALL_DIR"
sudo curl -fsSL "${SOC_URL}/app/agent/nexus_collector.py" -o "$INSTALL_DIR/nexus_collector.py"
sudo chmod +x "$INSTALL_DIR/nexus_collector.py"

echo "═══ 3/4 Enrôlement sur le périmètre « $PERIMETRE » ═══"
# --enroll crée un vrai agent (Bearer + clé HMAC) et écrit la config locale.
# Le périmètre doit exister côté SOC (seed : SIGIPES, ANTILOPE, Réseau/LAN CENADI).
sudo env SOC_URL="$SOC_URL" NEXUS_AGENT_DIR=/etc/nexus-agent \
  python3 "$INSTALL_DIR/nexus_collector.py" --enroll \
  --hostname "$AGENT_HOSTNAME" --perimetre "$PERIMETRE"

echo "═══ 4/4 Service de collecte continue (systemd) ═══"
sudo tee /etc/systemd/system/nexus-collector.service >/dev/null <<EOF
[Unit]
Description=NEXUS SOC — Collecteur de télémétrie réelle ($AGENT_HOSTNAME)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=SOC_URL=${SOC_URL}
Environment=NEXUS_AGENT_DIR=/etc/nexus-agent
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/nexus_collector.py --loop --interval 30
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now nexus-collector

echo
echo "✓ Setup vm-app-gov terminé — périmètre « $PERIMETRE », hostname $AGENT_HOSTNAME"
echo "  Le collecteur envoie de VRAIES mesures toutes les 30 s."
echo "  Visualisation : console opérateur → onglet « Supervision »."
echo "  Scénario d'attaque : sudo bash scenarios/03-exfiltration-solde.sh"
