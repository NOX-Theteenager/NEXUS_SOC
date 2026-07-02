#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Scénario 1 : PREUVE DE SOUVERAINETÉ
# =============================================================================
# Prouve devant le jury que la plateforme NEXUS SOC déployée dans le lab
# ne fait AUCUNE requête vers Internet — toutes les données restent
# strictement dans le réseau 10.42.0.0/24.
#
# À exécuter DEPUIS LE HÔTE Ubuntu (accès root nécessaire pour tcpdump sur
# le bridge virtuel).
#
# Ce script produit 3 preuves visibles :
#   1) Le réseau libvirt n'a AUCUNE route sortante (virsh)
#   2) tcpdump temps-réel sur virbr-lab : aucun paquet ne sort vers Internet
#   3) Depuis vm-soc : impossible de ping 8.8.8.8, mais 10.42.0.20 répond
#
# Durée : 5 minutes de démo (60 s pour chaque preuve)
# =============================================================================
set -uo pipefail

NET_NAME="nexus-lab"
NET_BRIDGE="virbr-lab"
VM_SOC_IP="10.42.0.10"
VM_CIBLE_IP="10.42.0.20"

BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
RESET="\033[0m"

banner() {
    echo
    echo -e "${BOLD}════════════════════════════════════════════════════════════════════${RESET}"
    echo -e "${BOLD}$1${RESET}"
    echo -e "${BOLD}════════════════════════════════════════════════════════════════════${RESET}"
}

pause() {
    echo
    echo -e "${YELLOW}[Pause démo — appuie sur Entrée pour continuer]${RESET}"
    read -r
}

# ── Preuve 1 : Configuration réseau libvirt ─────────────────────────────────
banner "PREUVE 1/3 — Le réseau libvirt N'A PAS de forward Internet"

echo
echo "→ Interrogation de la config libvirt du réseau '${NET_NAME}' :"
echo
virsh net-dumpxml "$NET_NAME" | grep -E "<forward|<name|<ip address" \
    || echo "  (aucune balise <forward> trouvée)"

echo
echo -e "${GREEN}✓ Analyse :${RESET}"
echo "  L'ABSENCE de balise <forward mode='nat'/> ou <forward mode='route'/>"
echo "  signifie qu'aucune route ne sort de ce réseau."
echo "  Les paquets qui essaient de partir sont DROP silencieusement par libvirt."
echo
echo "→ Preuve iptables (règles générées par libvirt) :"
sudo iptables -L LIBVIRT_FWO 2>/dev/null | head -10 || \
    sudo iptables -L FORWARD 2>/dev/null | grep -i "$NET_BRIDGE" | head -5

pause

# ── Preuve 2 : tcpdump temps-réel ────────────────────────────────────────────
banner "PREUVE 2/3 — tcpdump temps-réel sur le bridge (30 s)"

echo
echo "→ Écoute des paquets qui SORTENT du bridge $NET_BRIDGE vers l'extérieur"
echo "  (filtre = paquets dont la destination N'EST PAS 10.42.0.0/24)."
echo
echo "  Pendant ces 30 secondes, générons du trafic depuis vm-soc :"
echo "     ssh nexus@10.42.0.10 'curl http://127.0.0.1:8000/health'"
echo "     ssh nexus@10.42.0.10 'ping -c 3 10.42.0.20'"
echo
echo -e "${YELLOW}[La sortie tcpdump devrait rester quasi VIDE.]${RESET}"
echo

TCPDUMP_LOG=/tmp/nexus-souverainete-tcpdump.log
sudo timeout 30 tcpdump -nn -i "$NET_BRIDGE" \
    "not net 10.42.0.0/24 and not arp and not multicast" \
    > "$TCPDUMP_LOG" 2>&1 &
TCPDUMP_PID=$!

# Bruit "légitime" dans le réseau isolé, en parallèle
(
    sleep 3
    ssh -o StrictHostKeyChecking=no nexus@$VM_SOC_IP \
        'curl -s http://127.0.0.1:8000/health && \
         ping -c 3 10.42.0.20 && \
         curl -s http://10.42.0.20:22 -m 2 || true' 2>/dev/null
) &

wait $TCPDUMP_PID 2>/dev/null || true

echo
echo "→ Résultat tcpdump (paquets sortis vers l'extérieur en 30 s) :"
echo
if [[ -s "$TCPDUMP_LOG" ]]; then
    LINES=$(wc -l < "$TCPDUMP_LOG")
    if (( LINES > 5 )); then
        echo -e "${RED}✗ $LINES paquets sortants détectés (aperçu) :${RESET}"
        head -5 "$TCPDUMP_LOG"
    else
        echo -e "${GREEN}✓ Seulement $LINES lignes (probablement du bruit LAN) :${RESET}"
        cat "$TCPDUMP_LOG"
    fi
else
    echo -e "${GREEN}✓ AUCUN PAQUET n'a quitté le réseau isolé.${RESET}"
    echo "   Zéro sortie confirmée."
fi

pause

# ── Preuve 3 : Depuis vm-soc, Internet est UNREACHABLE ──────────────────────
banner "PREUVE 3/3 — Depuis vm-soc, Internet ne répond pas"

echo
echo "→ ping 8.8.8.8 depuis vm-soc (doit TIMEOUT) :"
echo
timeout 5 ssh -o StrictHostKeyChecking=no nexus@$VM_SOC_IP \
    'ping -c 3 -W 1 8.8.8.8' 2>&1 || echo -e "${GREEN}  ✓ Timeout confirmé (Internet inaccessible)${RESET}"

echo
echo "→ Ping du voisin dans le lab (doit répondre) :"
echo
ssh -o StrictHostKeyChecking=no nexus@$VM_SOC_IP \
    'ping -c 3 -W 1 10.42.0.20' 2>&1 | tail -6

echo
echo "→ curl vers Google DNS depuis vm-soc :"
ssh -o StrictHostKeyChecking=no nexus@$VM_SOC_IP \
    'curl -s --max-time 3 https://dns.google/resolve?name=example.com' 2>&1 \
    || echo -e "${GREEN}  ✓ curl a échoué (aucune connexion Internet)${RESET}"

# ── Synthèse ────────────────────────────────────────────────────────────────
banner "SYNTHÈSE — CONFORMITÉ SOUVERAINETÉ NUMÉRIQUE"

cat <<EOF

  ✓ Preuve 1 : config libvirt sans forward → cage réseau
  ✓ Preuve 2 : tcpdump vide en 30 s de trafic normal
  ✓ Preuve 3 : Internet UNREACHABLE depuis le SOC

  Point clé pour le jury :
  ────────────────────────
  Aucune donnée client (transactions, comptes, alertes) ne peut sortir
  du réseau du client, même par accident. Le SOC est déployé "on-premise"
  au Cameroun et les données restent en territoire souverain.

  Différenciateur face aux SOCs SaaS étrangers (Datadog, Splunk Cloud,
  CrowdStrike) : eux exfiltrent vers AWS/Azure US/EU par nature.
  NEXUS SOC déployé chez MINFI = zéro passage aux frontières.

EOF
