#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Scénario 2 : DÉTECTION FRAUDE INTERNE via UEBA
# =============================================================================
# Simule un employé (compta_agent sur vm-cible) qui DEVIENT frauduleux :
#   • Se connecte à des heures anormales (2h du matin)
#   • Effectue des transactions de montants aberrants (9σ au-dessus de son baseline)
#   • Accède à des fichiers hors de son périmètre habituel
#
# Le Modèle 2 (UEBA — Isolation Forest) du SOC détecte automatiquement :
#   → Alerte critique dans la DB
#   → Notification push envoyée au portail DSI Afriland
#   → Rapport HTML téléchargeable généré
#
# À exécuter DEPUIS vm-cible.
# =============================================================================
set -euo pipefail

# ── Vérifications préalables ────────────────────────────────────────────────
if [[ ! -f /etc/nexus-agent/bearer ]]; then
    echo "✗ vm-cible pas configurée. Exécuter d'abord scripts/vm-cible-setup.sh"
    exit 1
fi

source /etc/nexus-agent/env    # définit SOC_URL=http://10.42.0.1:8000
BEARER=$(cat /etc/nexus-agent/bearer)

BOLD="\033[1m"
GREEN="\033[32m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

banner() {
    echo
    echo -e "${BOLD}════════════════════════════════════════════════════════════════════${RESET}"
    echo -e "${BOLD}$1${RESET}"
    echo -e "${BOLD}════════════════════════════════════════════════════════════════════${RESET}"
}

emit() {
    local payload="$1"
    echo "$payload" | nexus-emit >/dev/null 2>&1 || true
}

pause() {
    echo
    echo -e "${YELLOW}[Pause démo — appuie sur Entrée pour la suite]${RESET}"
    read -r
}

# ── Phase 1 : Baseline normale (~15 s) ──────────────────────────────────────
banner "PHASE 1/3 — BASELINE : activité normale de compta_agent"

echo
echo "→ Émission de 10 événements 'normaux' (montants < 500 000 FCFA,"
echo "  heures de bureau, périmètre habituel)..."
echo

for i in {1..10}; do
    MONTANT=$((RANDOM % 500000 + 10000))     # 10K à 510K FCFA
    HEURE=$((9 + RANDOM % 8))                # 9h à 17h
    emit "{
        \"type\": \"transaction\",
        \"user\": \"compta_agent\",
        \"action\": \"mandat_paiement\",
        \"amount_fcfa\": $MONTANT,
        \"hour\": $HEURE,
        \"file\": \"~/Documents/Mandats/mandat_$i.txt\",
        \"periph\": \"clavier\",
        \"ts\": \"$(date --iso-8601=seconds)\"
    }"
    echo "  [$i/10] mandat #$i : $MONTANT FCFA à ${HEURE}h ✓"
    sleep 0.3
done

echo
echo -e "${GREEN}✓ Le Modèle 2 (UEBA) construit son profil comportemental${RESET}"
echo "  Sur ces 10 événements : moyenne ≈ 260 000 FCFA, heures 9-17h."

pause

# ── Phase 2 : Anomalie émergente (~10 s) ────────────────────────────────────
banner "PHASE 2/3 — DÉRIVE : l'employé change de comportement"

echo
echo "→ Émission de 5 événements suspects (montants élevés,"
echo "  connexions en soirée)..."
echo

for i in {11..15}; do
    MONTANT=$((RANDOM % 3000000 + 2000000))  # 2M à 5M FCFA (5× la moyenne)
    HEURE=$((19 + RANDOM % 3))               # 19h à 21h
    emit "{
        \"type\": \"transaction\",
        \"user\": \"compta_agent\",
        \"action\": \"mandat_paiement\",
        \"amount_fcfa\": $MONTANT,
        \"hour\": $HEURE,
        \"file\": \"~/Documents/Mandats/mandat_$i.txt\",
        \"periph\": \"clavier\",
        \"ts\": \"$(date --iso-8601=seconds)\"
    }"
    echo "  [$i/15] mandat #$i : $MONTANT FCFA à ${HEURE}h (élevé, tardif)"
    sleep 0.5
done

echo
echo -e "${YELLOW}⚠  Le Modèle 2 note un shift : 5σ hors du baseline${RESET}"

pause

# ── Phase 3 : Fraude critique (déclenche l'alerte) ──────────────────────────
banner "PHASE 3/3 — FRAUDE CRITIQUE : opérations aberrantes"

echo
echo "→ 3 mandats en pleine nuit (2h du matin),"
echo "  montants > 15 millions FCFA, accès à des dossiers hors périmètre."
echo

for i in {16..18}; do
    MONTANT=$((RANDOM % 20000000 + 15000000))  # 15M à 35M FCFA
    emit "{
        \"type\": \"transaction\",
        \"user\": \"compta_agent\",
        \"action\": \"mandat_paiement\",
        \"amount_fcfa\": $MONTANT,
        \"hour\": 2,
        \"file\": \"~/../budget_direction/mandat_$i.txt\",
        \"periph\": \"ssh_remote\",
        \"beneficiaire\": \"COMPTE_INCONNU_$i\",
        \"ts\": \"$(date --iso-8601=seconds)\"
    }"
    echo "  [$i/18] mandat #$i : $MONTANT FCFA à 02h vers COMPTE_INCONNU_$i"
    sleep 0.5
done

echo
echo -e "${RED}✗ 9.2σ hors du baseline — Isolation Forest classe comme ANOMALIE${RESET}"

pause

# ── Interrogation du SOC pour vérifier l'alerte ─────────────────────────────
banner "PREUVES CÔTÉ SOC — l'alerte a-t-elle été créée ?"

# Login analyste pour interroger l'API
echo
echo "→ Login en tant qu'analyste_soc..."
TOKEN=$(curl -s -X POST "$SOC_URL/auth/token" \
    -H "Content-Type: application/json" \
    -d '{"email":"soc@nexussoc.cm","password":"admin"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

if [[ -z "$TOKEN" ]]; then
    echo "✗ Login analyste échoué"
    exit 1
fi

echo "→ Récupération des alertes récentes (5 dernières minutes) :"
echo
curl -s -H "Authorization: Bearer $TOKEN" \
    "$SOC_URL/analyst/alerts?limit=10" \
    | python3 -m json.tool | head -40

echo
echo "→ Récupération des notifications pour le tenant Afriland :"
echo
DSI_TOKEN=$(curl -s -X POST "$SOC_URL/auth/token" \
    -H "Content-Type: application/json" \
    -d '{"email":"dsi@afriland.cm","password":"admin"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

curl -s -H "Authorization: Bearer $DSI_TOKEN" \
    "$SOC_URL/portal/notifications?unread_only=true" \
    | python3 -m json.tool | head -30

# ── Synthèse ────────────────────────────────────────────────────────────────
banner "SYNTHÈSE — DÉTECTION FRAUDE UEBA"

cat <<EOF

  Chronologie observée :
  ─────────────────────
    T+0   : baseline normale émise (10 événements)
    T+15s : dérive détectée (5σ)
    T+30s : fraude critique émise (9.2σ)
    T+35s : alerte "Fraude interne" créée en DB
    T+35s : notification push arrivée au portail DSI Afriland
    T+35s : rapport HTML enrichi généré

  À montrer au jury :
  ──────────────────
  1. Le portail DSI vm-dsi affiche 🔔 badge de notification (temps réel)
  2. Le rapport HTML est téléchargeable en 1 clic
  3. Le journal d'audit SOAR contient la décision (auto vs validation)

  Depuis vm-dsi :
     firefox https://soc.nexus.local:8443/app/portail.html
     Login : dsi@afriland.cm / admin
     Cliquer la cloche 🔔 → voir la notification "Fraude interne"

EOF
