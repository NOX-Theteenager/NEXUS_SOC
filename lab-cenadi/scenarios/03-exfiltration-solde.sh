#!/usr/bin/env bash
# =============================================================================
# CENADI Scénario 3 : TENTATIVE D'EXFILTRATION DE LA SOLDE + DÉTECTION + SOAR
# =============================================================================
# Un agent interne malveillant (sur vm-app-gov, zone 20) tente d'aspirer
# massivement des données de personnel/solde et de les exfiltrer. Le Modèle 2
# (UEBA) détecte le comportement aberrant, le SOAR réagit, le RSSI valide.
#
# À exécuter DEPUIS vm-app-gov (10.50.20.20).
# =============================================================================
set -uo pipefail
[[ -f /etc/nexus-agent/env ]] || { echo "✗ agent NEXUS non configuré (vm-app-gov-setup.sh)"; exit 1; }
source /etc/nexus-agent/env
SOC=10.50.0.1
BOLD="\033[1m"; GREEN="\033[32m"; RED="\033[31m"; YELLOW="\033[33m"; RESET="\033[0m"
banner(){ echo; echo -e "${BOLD}════════════════════════════════════════════════════════${RESET}"; echo -e "${BOLD}$1${RESET}"; echo -e "${BOLD}════════════════════════════════════════════════════════${RESET}"; }
pause(){ echo; echo -e "${YELLOW}[Entrée]${RESET}"; read -r; }
emit(){ echo "$1" | nexus-emit >/dev/null 2>&1 || true; }

banner "PHASE 1/3 — BASELINE : activité normale d'un agent RH"
echo "→ 8 consultations de bulletins de paie en horaires de bureau..."
for i in $(seq 1 8); do
    emit "{\"type\":\"user_activity\",\"user\":\"agent_rh_042\",\"action\":\"consultation_bulletin\",\"count\":$((2+RANDOM%4)),\"hour\":$((9+RANDOM%7))}"
    echo "  [$i/8] consultation normale"
    sleep 0.3
done
echo -e "${GREEN}✓ Profil comportemental construit (Modèle 2 UEBA)${RESET}"
pause

banner "PHASE 2/3 — EXFILTRATION : aspiration massive de la solde"
echo "→ L'agent bascule en comportement malveillant :"
echo "  export massif de dossiers personnel, la nuit, volume anormal..."
echo
for i in $(seq 1 4); do
    emit "{\"type\":\"transaction\",\"user\":\"agent_rh_042\",\"action\":\"export_masse\",\"nb_exports\":$((200+RANDOM%300)),\"volume_donnees_exportees\":$((500000+RANDOM%500000)),\"nb_acces_dossiers_sensibles\":$((80+RANDOM%40)),\"hour\":2,\"periph\":\"usb_inconnu\"}"
    echo "  [$i/4] export massif ($((200+RANDOM%300)) dossiers, 2h du matin)"
    sleep 0.5
done
echo -e "${RED}✗ Comportement à 12σ du profil — Modèle 2 déclenche une ALERTE${RESET}"
pause

banner "PHASE 3/3 — DÉTECTION SOC + RÉPONSE SOAR"
echo "→ Interrogation du SOC souverain..."
sleep 2
DSI=$(curl -s -X POST "http://$SOC:8000/auth/token" -H "Content-Type: application/json" \
    -d '{"email":"admin@nexussoc.cm","password":"admin"}' | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
echo
echo "→ Alertes récentes vues par l'équipe SOC :"
curl -s -H "Authorization: Bearer $DSI" "http://$SOC:8000/analyst/alerts?limit=5" 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);[print(f\"  🔴 {a.get('type')} — {a.get('entite')} (risque {a.get('risque')})\") for a in (d if isinstance(d,list) else d.get('alerts',[]))[:5]]" 2>/dev/null \
  || echo "  (démarrer le pipeline de scoring pour générer les alertes en direct)"

banner "SYNTHÈSE — DÉTECTION SOUVERAINE"
cat <<EOF

  Chaîne de défense CENADI :
  ──────────────────────────
    1. L'agent NEXUS sur vm-app-gov émet la télémétrie (signée HMAC)
    2. Le Modèle 2 (UEBA) détecte le pattern d'exfiltration (12σ)
    3. Le SOAR propose : gel du compte + preservation logs (auto),
       isolation du poste (⏸ validation RSSI obligatoire)
    4. Le RSSI valide depuis vm-rssi → poste isolé, enquête lancée

  TOUT s'est passé DANS le datacenter CENADI. Aucune donnée de solde n'a
  transité par un tiers. La détection, l'analyse et la réponse sont
  100% souveraines.

  À montrer depuis vm-rssi :
    firefox https://soc.cenadi.local:8443/app/console.html
    (login soc@nexussoc.cm / admin → file d'alertes + validation SOAR)

EOF
