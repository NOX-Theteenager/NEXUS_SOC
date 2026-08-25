#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : les six zones réseau du déploiement souverain
#
#      bash lab-cenadi/01-network-setup.sh              # aperçu
#      bash lab-cenadi/01-network-setup.sh --appliquer
#
#  Crée six réseaux libvirt ISOLÉS : ni passerelle, ni service d'adressage.
#  Ces deux fonctions reviennent à OPNsense, qui prend le .1 de chaque zone,
#  route entre les zones et applique la matrice de flux.
#
#      nexus-cenadi-mgmt  10.50.0.0/24   Cœur SOC   (HÔTE = 10.50.0.2)
#      nexus-cenadi-dmz   10.50.10.0/24  DMZ interne
#      nexus-cenadi-app   10.50.20.0/24  Serveurs applicatifs
#      nexus-cenadi-sens  10.50.30.0/24  Zone SENSIBLE ANTILOPE (air-gap)
#      nexus-cenadi-adm   10.50.40.0/24  Postes RSSI/DSI
#      nexus-cenadi-men   10.50.50.0/24  Zone menace
#
#  CE QUI A CHANGÉ, ET POURQUOI
#  ----------------------------
#  La version précédente faisait porter à libvirt l'adresse .1 de chaque zone
#  et un service DHCP par zone. Deux conséquences la rendaient intenable :
#
#    1. L'hôte occupait le .1 que l'architecture attribue au pare-feu. Tant
#       qu'il le garde, OPNsense ne peut pas le prendre et rien ne le traverse.
#    2. L'hôte routait implicitement entre ses propres ponts. Le trafic
#       inter-zone ne passait donc par aucune règle : la matrice de flux
#       n'était appliquée nulle part.
#
#  Les réseaux sont désormais de purs commutateurs virtuels. L'hôte n'y a
#  d'adresse que sur la zone du cœur SOC, en .2, posée par ce script.
#
#  Voir 00_Documents/Decision_Reponse_Collaborative.md, phase 1.
# =============================================================================
set -uo pipefail
export LIBVIRT_DEFAULT_URI="qemu:///system"

APPLIQUER=0
[[ "${1:-}" == "--appliquer" ]] && APPLIQUER=1

BOLD="\033[1m"; GREEN="\033[32m"; RED="\033[31m"; JAUNE="\033[33m"; RAZ="\033[0m"

HOTE_IP="10.50.0.2/24"
HOTE_PONT="virbr-cen-mgmt"

# nom|pont|CIDR documentaire|rôle
ZONES=(
  "nexus-cenadi-mgmt|virbr-cen-mgmt|10.50.0.0/24|Coeur SOC (HOTE en .2)"
  "nexus-cenadi-dmz|virbr-cen-dmz|10.50.10.0/24|DMZ interne"
  "nexus-cenadi-app|virbr-cen-app|10.50.20.0/24|Serveurs applicatifs"
  "nexus-cenadi-sens|virbr-cen-sens|10.50.30.0/24|Zone SENSIBLE (air-gap)"
  "nexus-cenadi-adm|virbr-cen-adm|10.50.40.0/24|Admin RSSI/DSI"
  "nexus-cenadi-men|virbr-cen-men|10.50.50.0/24|Zone menace"
)

xml_zone() {   # $1 = nom, $2 = pont, $3 = rôle
  # Zone du cœur SOC : l'hôte y garde une adresse, en .2, parce qu'il EST le
  # SOC et doit rester joignable depuis sa propre zone. C'est libvirt qui la
  # pose, donc elle survit au redémarrage. Ni DHCP ni DNS : le .1 et
  # l'adressage reviennent à OPNsense.
  if [[ "$2" == "$HOTE_PONT" ]]; then
    cat <<XML
<network>
  <name>$1</name>
  <bridge name='$2' stp='on' delay='0'/>
  <dns enable='no'/>
  <ip address='${HOTE_IP%/*}' netmask='255.255.255.0'/>
</network>
XML
    return
  fi
  # Toutes les autres zones : commutateur pur. Ni <forward>, ni <ip>, ni
  # <dhcp> — l'hôte n'a rien à y faire, il ne les traverse pas.
  cat <<XML
<network>
  <name>$1</name>
  <bridge name='$2' stp='on' delay='0'/>
</network>
XML
}

# ── Aperçu ──────────────────────────────────────────────────────────────────
echo -e "${BOLD}Six zones réseau — CENADI souverain${RAZ}"
echo
printf "  %-20s %-16s %-16s %s\n" "RÉSEAU" "PONT" "PLAN" "ÉTAT ACTUEL"
a_migrer=0
for z in "${ZONES[@]}"; do
  IFS='|' read -r nom pont cidr role <<< "$z"
  if virsh net-info "$nom" >/dev/null 2>&1; then
    xml=$(virsh net-dumpxml "$nom")
    if [[ "$pont" == "$HOTE_PONT" ]]; then
      if grep -q "address='${HOTE_IP%/*}'" <<< "$xml" && ! grep -q "<dhcp>" <<< "$xml"; then
        etat="${GREEN}conforme (hôte en ${HOTE_IP%/*})${RAZ}"
      else
        etat="${JAUNE}à migrer${RAZ}"; a_migrer=1
      fi
    elif grep -q "<ip " <<< "$xml"; then
      etat="${JAUNE}à migrer (porte encore une adresse)${RAZ}"; a_migrer=1
    else
      etat="${GREEN}conforme${RAZ}"
    fi
  else
    etat="${JAUNE}à créer${RAZ}"; a_migrer=1
  fi
  printf "  %-20s %-16s %-16s %b\n" "$nom" "$pont" "$cidr" "$etat"
done

echo
if ip -4 -o addr show dev "$HOTE_PONT" 2>/dev/null | awk '{print $4}' | grep -qx "$HOTE_IP"; then
  echo -e "  Adresse de l'hôte sur $HOTE_PONT : ${GREEN}${HOTE_IP} présente${RAZ}"
else
  echo -e "  Adresse de l'hôte sur $HOTE_PONT : ${JAUNE}${HOTE_IP} à poser${RAZ}"
fi

if [[ $APPLIQUER -eq 0 ]]; then
  echo
  echo "MODE APERÇU — rien n'est modifié. Ajoutez --appliquer pour agir."
  [[ $a_migrer -eq 1 ]] && cat <<'EOF'

Ce que --appliquer fera, dans l'ordre :
  1. arrêt et redéfinition de chaque zone, sans adresse ni service DHCP ;
  2. pose de 10.50.0.2/24 sur virbr-cen-mgmt, pour que le cœur SOC reste
     joignable depuis sa propre zone.

À SAVOIR AVANT DE LANCER
  · Les interfaces de zone des machines allumées seront détachées le temps de
    la redéfinition. Éteignez-les d'abord : elles doivent de toute façon
    redémarrer pour prendre leur nouvelle allocation mémoire.
  · Les réservations d'adresses disparaissent avec le service DHCP. Chaque
    machine reçoit désormais une adresse fixe dans sa propre configuration,
    avec pour passerelle le .1 de sa zone.
  · Tant qu'OPNsense n'est pas configuré, aucune zone ne communique avec une
    autre. C'est attendu : plus rien ne route avant le pare-feu.
EOF
  exit 0
fi

# ── Application ─────────────────────────────────────────────────────────────
allumees=$(virsh list --name | grep -v '^$' || true)
if [[ -n "$allumees" ]]; then
  echo -e "${RED}✗ Des machines sont allumées :${RAZ} $(echo "$allumees" | tr '\n' ' ')"
  echo "  Éteignez-les avant de redéfinir les réseaux."
  exit 1
fi

echo
for z in "${ZONES[@]}"; do
  IFS='|' read -r nom pont cidr role <<< "$z"
  printf "  %-20s " "$nom"
  if virsh net-info "$nom" >/dev/null 2>&1; then
    virsh net-destroy "$nom" >/dev/null 2>&1
    virsh net-undefine "$nom" >/dev/null 2>&1
  fi
  if xml_zone "$nom" "$pont" "$role" | virsh net-define /dev/stdin >/dev/null 2>&1 \
     && virsh net-autostart "$nom" >/dev/null 2>&1 \
     && virsh net-start "$nom" >/dev/null 2>&1; then
    echo -e "${GREEN}✓ isolé, sans adresse ni DHCP${RAZ}"
  else
    echo -e "${RED}✗ échec${RAZ}"
  fi
done

# Constater, pas supposer : on relit l'adresse effectivement portée.
echo
printf "  %-20s " "adresse de l'hôte"
if ip -4 -o addr show dev "$HOTE_PONT" 2>/dev/null | awk '{print $4}' | grep -qx "$HOTE_IP"; then
  echo -e "${GREEN}✓ ${HOTE_IP} portée par ${HOTE_PONT}${RAZ}"
else
  portee=$(ip -4 -o addr show dev "$HOTE_PONT" 2>/dev/null | awk '{print $4}' | tr '\n' ' ')
  echo -e "${RED}✗ attendu ${HOTE_IP}, trouvé : ${portee:-aucune}${RAZ}"
fi

cat <<EOF

════════════════════════════════════════════════════════════════════
Six zones créées, aucune ne route : c'est le pare-feu qui routera.
════════════════════════════════════════════════════════════════════
  HÔTE = cœur SOC        10.50.0.2   (${HOTE_PONT})
  OPNsense prendra       10.50.0.1, 10.50.10.1, 10.50.20.1,
                         10.50.30.1, 10.50.40.1, 10.50.50.1
  vm-app-gov 10.50.20.20 · vm-antilope 10.50.30.30 (AIR-GAP)
  vm-rssi    10.50.40.40 · KaliPrime   10.50.50.50

Suite : lab-cenadi/07-opnsense.md
EOF
