#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : preuve du pilotage réel du pare-feu par le SOAR
#
#      export OPNSENSE_KEY=… OPNSENSE_SECRET=… OPNSENSE_GUI_PASSWORD=…
#      bash lab-cenadi/scenarios/06-preuve-quarantaine.sh
#
#  Rien n'est simulé. Le scénario appelle l'API d'OPNsense avec le compte de
#  service « nexus-soar », celui-là même qu'utilise le connecteur de réponse,
#  puis constate l'effet des deux côtés de la frontière.
#
#  CE QUE LA PREUVE DOIT MONTRER
#  -----------------------------
#  Une quarantaine qui coupe tout n'a aucune valeur : elle aveugle le SOC au
#  moment précis où il a besoin de voir. La politique retenue coupe les flux de
#  la machine et LAISSE PASSER sa télémétrie vers le cœur SOC. Les deux
#  propriétés doivent se vérifier dans la même fenêtre de temps.
#
#  DEUX POINTS D'OBSERVATION, PARCE QU'UN SEUL NE SUFFIT PAS
#  --------------------------------------------------------
#    · de l'intérieur   KaliPrime (10.50.50.50), par l'agent invité QEMU :
#                       le canal virtio-serial ne traverse pas le pare-feu, il
#                       reste donc lisible même quand la machine est isolée ;
#    · de l'extérieur   le cœur SOC (10.50.0.2) vers vm-rssi (10.50.40.40) :
#                       la machine mise en quarantaine devient injoignable.
#
#  On conclut sur des CODES DE SORTIE, jamais sur du texte lu au jugé : une
#  sortie mal interprétée a déjà fait conclure l'inverse de la réalité ici.
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

VM_INTERIEUR="${VM_INTERIEUR:-KaliPrime}"
IP_INTERIEUR="${IP_INTERIEUR:-10.50.50.50}"
IP_EXTERIEUR="${IP_EXTERIEUR:-10.50.40.40}"      # vm-rssi, vue depuis le SOC
ALIAS="${ALIAS:-nexus_quarantaine}"
URL="${OPNSENSE_URL:-https://10.50.0.1}"
CAPTURES="${CAPTURES:-}"                          # dossier, ou vide

GREEN="\033[32m"; RED="\033[31m"; BOLD="\033[1m"; RAZ="\033[0m"
: "${OPNSENSE_KEY:?OPNSENSE_KEY absent de l environnement}"
: "${OPNSENSE_SECRET:?OPNSENSE_SECRET absent de l environnement}"

echec=0

alias_poster() {   # $1 = add|delete, $2 = adresse
  curl -sk -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" -X POST \
       -H 'Content-Type: application/json' -d "{\"address\":\"$2\"}" \
       "$URL/api/firewall/alias_util/$1/$ALIAS"
}

table_contient() {  # $1 = adresse ; 0 si présente
  curl -sk -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" \
       "$URL/api/firewall/alias_util/list/$ALIAS" | grep -q "\"$1\""
}

sonde() {  # $1 = PASSE|COUPE attendu, $2 = libellé, $3... = commande
  local attendu="$1" quoi="$2"; shift 2
  "$@" >/dev/null 2>&1
  local code=$? obtenu="COUPE"
  [[ $code -eq 0 ]] && obtenu="PASSE"
  if [[ "$obtenu" == "$attendu" ]]; then
    printf "    ${GREEN}✓${RAZ} %-44s %-5s (code %d)\n" "$quoi" "$obtenu" "$code"
  else
    printf "    ${RED}✗${RAZ} %-44s %-5s attendu %s (code %d)\n" "$quoi" "$obtenu" "$attendu" "$code"
    echec=1
  fi
}

dedans()  { python3 lab-cenadi/scripts/qga-exec.py "$VM_INTERIEUR" "$1"; }

# La page des tables de pare-feu s'ouvre sur « bogons ». Sans cette
# préparation, la capture prouverait l'état d'une table qui ne nous concerne
# pas — c'est le genre de figure qui décrédibilise un mémoire entier.
CHOISIR_ALIAS='(() => { const s=[...document.querySelectorAll("select")].find(x=>[...x.options].some(o=>(o.value||"")==="'"$ALIAS"'")); if(!s) return "select introuvable"; s.value="'"$ALIAS"'"; if(window.jQuery){jQuery(s).val("'"$ALIAS"'").trigger("change"); if(jQuery(s).selectpicker) jQuery(s).selectpicker("refresh");} else {s.dispatchEvent(new Event("change",{bubbles:true}));} return s.value; })()'

capturer() {  # $1 = préfixe ; arguments suivants = pages additionnelles
  [[ -z "$CAPTURES" || -z "${OPNSENSE_GUI_PASSWORD:-}" ]] && return 0
  local prefixe="$1"; shift
  python3 lab-cenadi/scripts/opnsense-captures.py --sortie "$CAPTURES" \
      --page "$prefixe-alias-quarantaine=/ui/firewall/alias_util" \
      --prepare "$prefixe-alias-quarantaine=$CHOISIR_ALIAS" \
      "$@" 2>&1 | grep -E "^  ✓" | sed 's/^  /    · /'
}

echo -e "${BOLD}Preuve de quarantaine pilotée par l'API${RAZ}"
echo   "  intérieur : $VM_INTERIEUR ($IP_INTERIEUR) · extérieur : vm-rssi ($IP_EXTERIEUR)"

# ── 1. État de départ ───────────────────────────────────────────────────────
echo -e "\n  ${BOLD}1. Avant toute décision du SOAR${RAZ}"
alias_poster delete "$IP_INTERIEUR" >/dev/null 2>&1
alias_poster delete "$IP_EXTERIEUR" >/dev/null 2>&1
sleep 1
sonde COUPE "l'alias ne contient pas $IP_INTERIEUR" table_contient "$IP_INTERIEUR"
sonde PASSE "intérieur — résolution de noms de zone"  dedans "dig +time=3 +tries=1 @10.50.50.1 opnsense.cenadi.local +short"
sonde PASSE "intérieur — télémétrie vers le cœur SOC" dedans "curl -s -m6 -o /dev/null http://10.50.0.2:8000/health"
sonde PASSE "SOC → vm-rssi joignable"                 ping -c2 -W3 "$IP_EXTERIEUR"
capturer 01-avant

# ── 2. Décision ─────────────────────────────────────────────────────────────
echo -e "\n  ${BOLD}2. Le SOAR met les deux machines en quarantaine${RAZ}"
for ip in "$IP_INTERIEUR" "$IP_EXTERIEUR"; do
  r=$(alias_poster add "$ip")
  printf "    api add %-14s → %s\n" "$ip" "$r"
  grep -q '"status":"done"' <<< "$r" || { echo -e "    ${RED}✗ l'API a refusé${RAZ}"; echec=1; }
done
# Les états déjà établis survivraient à la nouvelle règle : on les coupe,
# comme le fait le connecteur. Sans cela la preuve dépendrait d'un délai
# d'expiration et non de la règle.
python3 lab-cenadi/scripts/opnsense-console.py "pfctl -k $IP_INTERIEUR; pfctl -k $IP_EXTERIEUR" >/dev/null 2>&1
sleep 2

# ── 3. Effet ────────────────────────────────────────────────────────────────
echo -e "\n  ${BOLD}3. Effet constaté${RAZ}"
sonde PASSE "l'alias contient bien $IP_INTERIEUR"     table_contient "$IP_INTERIEUR"
sonde COUPE "intérieur — résolution de noms de zone"  dedans "dig +time=3 +tries=1 @10.50.50.1 opnsense.cenadi.local +short"
sonde PASSE "intérieur — télémétrie vers le cœur SOC" dedans "curl -s -m6 -o /dev/null http://10.50.0.2:8000/health"
sonde COUPE "SOC → vm-rssi joignable"                 ping -c2 -W3 "$IP_EXTERIEUR"
# On refait du bruit juste avant la capture : la vue temps réel n'affiche que
# ce qui vient de passer, et une capture d'un journal vide ne prouve rien.
dedans "dig +time=2 +tries=1 @10.50.50.1 cenadi.local +short" >/dev/null 2>&1
ping -c3 -W2 "$IP_EXTERIEUR" >/dev/null 2>&1
# firewall_rules.php a disparu d'OPNsense 26 : les règles vivent désormais sous
# /ui/firewall/filter. L'ancien chemin renvoyait une page « not found » que la
# capture enregistrait sans broncher — une figure vide dans un mémoire.
capturer 02-pendant \
  --page "02-pendant-journal-pare-feu=/ui/diagnostics/firewall/log"

# ── 4. Levée ────────────────────────────────────────────────────────────────
echo -e "\n  ${BOLD}4. Le SOAR lève la quarantaine${RAZ}"
for ip in "$IP_INTERIEUR" "$IP_EXTERIEUR"; do
  r=$(alias_poster delete "$ip")
  printf "    api delete %-11s → %s\n" "$ip" "$r"
done
sleep 2
sonde COUPE "l'alias ne contient plus $IP_INTERIEUR"  table_contient "$IP_INTERIEUR"
sonde PASSE "intérieur — résolution de noms de zone"  dedans "dig +time=3 +tries=1 @10.50.50.1 opnsense.cenadi.local +short"
sonde PASSE "SOC → vm-rssi joignable"                 ping -c2 -W3 "$IP_EXTERIEUR"
capturer 03-apres

echo
if [[ $echec -eq 0 ]]; then
  echo -e "  ${GREEN}${BOLD}Recette complète : le pare-feu obéit au SOAR, la télémétrie survit.${RAZ}"
else
  echo -e "  ${RED}${BOLD}Au moins une sonde a démenti l'attendu — voir ci-dessus.${RAZ}"
fi
exit $echec
