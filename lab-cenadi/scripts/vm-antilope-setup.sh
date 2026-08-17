#!/usr/bin/env bash
# =============================================================================
# CENADI : setup vm-antilope (10.50.30.30) — ZONE SENSIBLE AIR-GAP
# =============================================================================
# Simule le serveur ANTILOPE (solde de l'État). En air-gap : il ne peut
# QU'émettre sa télémétrie vers le SOC. Déploie le VRAI collecteur (mesures
# réelles), rattaché au périmètre supervisé « ANTILOPE ».
#
# PRÉREQUIS : la règle OPNsense LAN_SENS → 10.50.0.2 (tcp 8000/443) doit exister
# et DROP tout le reste (voir SECURISATION.md couche 2).
# =============================================================================
set -euo pipefail

SOC=${SOC:-10.50.0.1}
export SOC_URL="http://${SOC}:8000"
AGENT_HOSTNAME=${AGENT_HOSTNAME:-SRV-ANTILOPE-01}
PERIMETRE=${PERIMETRE:-ANTILOPE}
INSTALL_DIR=/opt/nexus-agent

echo "═══ 0/4 Connectivité SOC (seul flux autorisé en air-gap) ═══"
if ! curl -s --max-time 3 "${SOC_URL}/health" | grep -q '"status":"ok"'; then
    echo "✗ SOC injoignable. En air-gap, SEUL 10.50.0.1 doit être joignable."
    echo "  Vérifier la règle OPNsense : LAN_SENS → 10.50.0.2 autorisé, reste rejeté."
    exit 1
fi
echo "✓ SOC accessible (flux télémétrie unidirectionnel)"

echo "  Contrôle air-gap :"
ping -c1 -W2 8.8.8.8 >/dev/null 2>&1 && echo "    ⚠ Internet joignable — AIR-GAP ROMPU" || echo "    ✓ Internet injoignable"
ping -c1 -W2 10.50.20.20 >/dev/null 2>&1 && echo "    ⚠ zone app joignable — cloisonnement rompu" || echo "    ✓ zones latérales injoignables"

echo "═══ 1/4 Paquets (python3 + iproute2) ═══"
sudo apt-get update -qq && sudo apt-get install -y -qq python3 iproute2 curl

echo "═══ 2/4 Récupération du collecteur réel depuis le SOC ═══"
sudo mkdir -p "$INSTALL_DIR"
sudo curl -fsSL "${SOC_URL}/app/agent/nexus_collector.py" -o "$INSTALL_DIR/nexus_collector.py"
sudo chmod +x "$INSTALL_DIR/nexus_collector.py"

echo "═══ 3/4 Enrôlement sur le périmètre « $PERIMETRE » (zone sensible) ═══"
sudo env SOC_URL="$SOC_URL" NEXUS_AGENT_DIR=/etc/nexus-agent \
  python3 "$INSTALL_DIR/nexus_collector.py" --enroll \
  --hostname "$AGENT_HOSTNAME" --perimetre "$PERIMETRE"

echo "═══ 4/4 Service de collecte continue (systemd) ═══"
sudo tee /etc/systemd/system/nexus-collector.service >/dev/null <<EOF
[Unit]
Description=NEXUS SOC — Collecteur télémétrie réelle ($AGENT_HOSTNAME, air-gap)
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
echo "✓ Setup vm-antilope terminé (ZONE SENSIBLE AIR-GAP) — périmètre « $PERIMETRE »"
echo "  Collecte réelle toutes les 30 s, flux unidirectionnel vers le SOC."
echo "  Scénario : sudo bash scenarios/02-airgap-zone-sensible.sh"
echo "             sudo bash scenarios/03-exfiltration-solde.sh"
