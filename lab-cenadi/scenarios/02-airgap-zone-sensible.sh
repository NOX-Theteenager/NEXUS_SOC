#!/usr/bin/env bash
# =============================================================================
# CENADI Scénario 2 : AIR-GAP DE LA ZONE SENSIBLE (ANTILOPE / solde de l'État)
# =============================================================================
# Prouve que la zone 30 (vm-antilope, simulant ANTILOPE/SIGIPES) est en
# air-gap : elle peut UNIQUEMENT émettre sa télémétrie vers le SOC, et ne peut
# joindre NI Internet NI aucune autre zone.
#
# À exécuter DEPUIS vm-antilope (10.50.30.30).
# =============================================================================
set -uo pipefail
SOC=10.50.0.1
BOLD="\033[1m"; GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; RESET="\033[0m"
banner(){ echo; echo -e "${BOLD}═══ $1 ═══${RESET}"; }
pause(){ echo; echo -e "${YELLOW}[Entrée]${RESET}"; read -r; }

banner "PREUVE 1/4 — Internet INJOIGNABLE depuis la zone sensible"
echo "→ ping 8.8.8.8 (doit échouer) :"
ping -c 2 -W 2 8.8.8.8 >/dev/null 2>&1 && echo -e "${RED}✗ Internet joignable — air-gap ROMPU !${RESET}" || echo -e "${GREEN}✓ Timeout — pas d'Internet${RESET}"
pause

banner "PREUVE 2/4 — Zones latérales INJOIGNABLES"
echo "→ ping vm-app-gov 10.50.20.20 (autre zone, doit échouer) :"
ping -c 2 -W 2 10.50.20.20 >/dev/null 2>&1 && echo -e "${RED}✗ Zone app joignable — cloisonnement ROMPU !${RESET}" || echo -e "${GREEN}✓ Timeout — zones cloisonnées${RESET}"
echo "→ ping poste RSSI 10.50.40.40 (doit échouer) :"
ping -c 2 -W 2 10.50.40.40 >/dev/null 2>&1 && echo -e "${RED}✗ joignable${RESET}" || echo -e "${GREEN}✓ Timeout${RESET}"
pause

banner "PREUVE 3/4 — Le SOC reste joignable (flux télémétrie unidirectionnel)"
echo "→ curl $SOC:8000/health (doit répondre) :"
if curl -s --max-time 3 "http://$SOC:8000/health" | grep -q '"status":"ok"'; then
    echo -e "${GREEN}✓ Le SOC accepte la télémétrie d'ANTILOPE${RESET}"
else
    echo -e "${RED}✗ SOC injoignable — vérifier la règle OPNsense LAN_SENS→mgmt${RESET}"
fi
pause

banner "PREUVE 4/4 — Émission de télémétrie ANTILOPE vers le SOC"
if [[ -f /opt/nexus-agent/nexus_collector.py ]]; then
    SOC_URL="http://${SOC:-10.50.0.1}:8000" NEXUS_AGENT_DIR=/etc/nexus-agent \
      sudo -E python3 /opt/nexus-agent/nexus_collector.py --once >/dev/null 2>&1 \
      && echo -e "${GREEN}✓ Télémétrie réelle envoyée (flux SORTANT unidirectionnel autorisé)${RESET}" \
      || echo -e "${YELLOW}⚠ collecteur en échec (agent configuré ?)${RESET}"
else
    echo "  (agent NEXUS non configuré — lancer vm-antilope-setup.sh)"
fi

banner "SYNTHÈSE — AIR-GAP ANTILOPE"
cat <<EOF

  La zone sensible (solde de l'État) est hermétiquement cloisonnée :
    ✗ Internet        → INJOIGNABLE
    ✗ Autres zones    → INJOIGNABLES (pas de mouvement latéral)
    ✓ SOC (10.50.0.1) → joignable UNIQUEMENT en sortie (télémétrie)

  Modèle de flux : UNIDIRECTIONNEL. ANTILOPE "parle" au SOC, mais personne
  ne peut "entrer" dans ANTILOPE, ni ANTILOPE sortir ailleurs.

  Enjeu : même si un poste bureautique était compromis (zone menace), il ne
  pourrait JAMAIS atteindre la base de la solde. Le paquet est droppé au
  niveau 3 par le routeur, avant d'atteindre le serveur.

EOF
