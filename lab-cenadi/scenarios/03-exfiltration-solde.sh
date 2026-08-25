#!/usr/bin/env bash
# =============================================================================
# CENADI Scénario 3 : TENTATIVE D'EXFILTRATION DE LA SOLDE + DÉTECTION + SOAR
# =============================================================================
# Un agent interne malveillant tente d'aspirer massivement des données de
# personnel/solde. Le Modèle 2 (UEBA) détecte le comportement aberrant.
#
# À exécuter DEPUIS la VM surveillée (vm-app-gov ou vm-antilope) où le
# collecteur NEXUS est déjà installé (vm-*-setup.sh).
# =============================================================================
set -uo pipefail
SOC=${SOC:-10.50.0.2}
AGENT=/opt/nexus-agent/nexus_collector.py
export SOC_URL="http://${SOC}:8000"
export NEXUS_AGENT_DIR=/etc/nexus-agent

BOLD="\033[1m"; GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; RESET="\033[0m"
banner(){ echo; echo -e "${BOLD}════════════════════════════════════════════════════════${RESET}"; echo -e "${BOLD}$1${RESET}"; echo -e "${BOLD}════════════════════════════════════════════════════════${RESET}"; }
pause(){ echo; echo -e "${YELLOW}[Entrée pour continuer]${RESET}"; read -r; }

[[ -f "$AGENT" ]] || { echo "✗ Collecteur absent. Lancer d'abord vm-*-setup.sh"; exit 1; }

banner "PHASE 1/3 — BASELINE : activité normale (mesures réelles)"
echo "→ Envoi d'une collecte réelle de l'hôte (activité normale)..."
sudo -E python3 "$AGENT" --once
echo -e "${GREEN}✓ Profil normal transmis — risque bas attendu.${RESET}"
pause

banner "PHASE 2/3 — EXFILTRATION : aspiration massive de la solde"
echo "→ Bascule en comportement malveillant : export massif de dossiers"
echo "  personnel, la nuit, volume anormal, accès dossiers sensibles..."
echo "  (télémétrie d'attaque réaliste, envoyée par le pipeline signé HMAC)"
sudo -E python3 "$AGENT" --simulate exfil
echo -e "${RED}✗ Comportement très au-dessus du profil — le Modèle 2 déclenche une ALERTE${RESET}"
pause

banner "PHASE 3/3 — DÉTECTION SOC + RÉPONSE SOAR"
echo "→ Interrogation du SOC souverain..."
sleep 3
AT=$(curl -s -X POST "${SOC_URL}/auth/token" -H "Content-Type: application/json" \
    -d '{"email":"admin@nexussoc.cm","password":"admin"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
echo
echo "→ Alertes récentes vues par l'équipe SOC du CENADI :"
curl -s -H "Authorization: Bearer $AT" "${SOC_URL}/analyst/alerts?limit=5" 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);rows=(d if isinstance(d,list) else d.get('alerts',[]));[print(f\"  🔴 {a.get('type')} — {a.get('entite')} (risque {a.get('risque')})\") for a in rows[:5]]" 2>/dev/null \
  || echo "  (vérifier que le pipeline de scoring tourne côté SOC)"

banner "SYNTHÈSE — DÉTECTION SOUVERAINE"
cat <<EOF

  Chaîne de défense CENADI :
  ──────────────────────────
    1. Le collecteur NEXUS sur la VM émet la télémétrie (signée HMAC)
    2. Le Modèle 2 (UEBA) détecte le pattern d'exfiltration
    3. Le SOAR propose : gel du compte + préservation des logs (auto),
       isolation du poste (⏸ validation RSSI obligatoire)
    4. Le RSSI valide depuis vm-rssi → poste isolé, enquête lancée

  TOUT s'est passé DANS le datacenter CENADI. Aucune donnée de solde n'a
  transité par un tiers.

  À MONTRER (visualisation temps réel) :
    • Console opérateur → File d'alertes  (l'alerte apparaît)
    • Console opérateur → Supervision      (le risque UEBA monte à 100)
    • Portail du périmètre                 (vue du responsable)
    depuis vm-rssi : firefox ${SOC_URL}/app/login.html
    (soc@nexussoc.cm / admin)

EOF
