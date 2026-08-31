#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : recette de la matrice de flux
#
#      bash lab-cenadi/scenarios/05-matrice-de-flux.sh
#
#  À exécuter DEPUIS L'HÔTE (cœur SOC, 10.50.0.2). Chaque test compare un
#  résultat OBSERVÉ à un résultat ATTENDU. Aucune sortie n'est interprétée :
#  seuls les codes de retour comptent, parce qu'un test qui lit du texte finit
#  par mentir sur ce qu'il mesure.
#
#  Prérequis : les quatre machines sont sur le plan 10.50 et n'ont plus de
#  carte sur le réseau de gestion (sans quoi les preuves d'étanchéité sont
#  fausses : le trafic contourne le pare-feu).
# =============================================================================
set -uo pipefail
GREEN="\033[32m"; RED="\033[31m"; GRIS="\033[90m"; BOLD="\033[1m"; RAZ="\033[0m"

SOC=10.50.0.2
declare -A HOTE=(
  [applicatif]="noxtheteenager@10.50.20.20"
  [sensible]="antilope@10.50.30.30"
  [admin]="rssi@10.50.40.40"
)
DELAI_SSH=${DELAI_SSH:-120}
ok=0; ko=0

distant() {  # exécute une commande dans une machine, rend son code
  timeout "$DELAI_SSH" ssh -o BatchMode=yes -o StrictHostKeyChecking=no \
    -o ConnectTimeout=10 "$1" "$2" >/dev/null 2>&1
}

essai() {  # $1=zone $2=libellé $3=commande $4=OK|BLOQUE
  local cible="${HOTE[$1]}" obtenu
  if distant "$cible" "$3"; then obtenu=PASSE; else obtenu=BLOQUE; fi
  local attendu="$4"
  [ "$attendu" = "OK" ] && attendu=PASSE
  if [ "$obtenu" = "$attendu" ]; then
    printf "  ${GREEN}✓${RAZ} %-10s %-42s %s\n" "$1" "$2" "$obtenu"; ok=$((ok+1))
  else
    printf "  ${RED}✗${RAZ} %-10s %-42s obtenu %s, attendu %s\n" "$1" "$2" "$obtenu" "$attendu"; ko=$((ko+1))
  fi
}

echo -e "${BOLD}Recette de la matrice de flux — CENADI${RAZ}"
echo -e "${GRIS}Depuis l'hôte (cœur SOC $SOC), à travers OPNsense 10.50.0.1${RAZ}"
echo

echo -e "${BOLD}1. Le cœur SOC atteint toutes les zones (collecte)${RAZ}"
for t in "10.50.20.20 applicatif" "10.50.30.30 sensible" "10.50.40.40 admin" "10.50.50.50 menace"; do
  set -- $t
  if ping -c1 -W2 "$1" >/dev/null 2>&1; then
    printf "  ${GREEN}✓${RAZ} %-10s %-42s joignable\n" "$2" "SOC vers $1"; ok=$((ok+1))
  else
    printf "  ${RED}✗${RAZ} %-10s %-42s MUET\n" "$2" "SOC vers $1"; ko=$((ko+1))
  fi
done

echo
echo -e "${BOLD}2. Air-gap de la zone sensible${RAZ}"
essai sensible "telemetrie vers le SOC (tcp 8000)" \
  "curl -sf -m6 -o /dev/null http://$SOC:8000/health" OK
essai sensible "vers la zone applicative" \
  "ping -c1 -W2 10.50.20.20" BLOQUE
essai sensible "vers Internet" \
  "ping -c1 -W2 8.8.8.8" BLOQUE
essai sensible "ssh vers la zone applicative" \
  "timeout 4 bash -c '</dev/tcp/10.50.20.20/22'" BLOQUE

echo
echo -e "${BOLD}3. Cloisonnement des autres zones${RAZ}"
essai applicatif "telemetrie vers le SOC" \
  "curl -sf -m6 -o /dev/null http://$SOC:8000/health" OK
essai applicatif "vers la zone sensible" \
  "ping -c1 -W2 10.50.30.30" BLOQUE
essai admin      "vers la zone sensible" \
  "ping -c1 -W2 10.50.30.30" BLOQUE
essai admin      "resolution de noms par la passerelle" \
  "getent hosts opnsense.cenadi.local || nslookup -timeout=3 opnsense 10.50.40.1" OK

echo
echo -e "${BOLD}Bilan${RAZ}"
printf "  %d conformes, %d écarts\n" "$ok" "$ko"
[ "$ko" -eq 0 ] || echo -e "  ${RED}La matrice n'est pas respectée.${RAZ}"
exit $(( ko > 0 ))
