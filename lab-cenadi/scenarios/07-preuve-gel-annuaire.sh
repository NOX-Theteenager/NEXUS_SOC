#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : preuve du gel de compte dans l'annuaire souverain
#
#      export LDAP_SOAR_PASSWORD=…
#      bash lab-cenadi/scenarios/07-preuve-gel-annuaire.sh
#
#  Le pare-feu coupe un câble ; l'annuaire suspend une identité. C'est le seul
#  verrou qu'aucune topologie réseau ne peut lever : un compte volé reste
#  utilisable depuis n'importe quelle machine tant que l'annuaire l'accepte.
#
#  CE QUE LA PREUVE DOIT MONTRER
#  -----------------------------
#  1. Le gel produit un REFUS D'AUTHENTIFICATION réel, pas seulement un attribut
#     posé. `ldapmodify` peut réussir sur un attribut sans effet : c'est le cas
#     de `nsAccountLock` sur OpenLDAP, accepté puis ignoré. On ne conclut donc
#     jamais sur le code de retour de la modification, mais sur un `ldapwhoami`
#     rejoué ensuite.
#  2. Le gel est RÉVERSIBLE. On suspend un accès, on ne détruit pas une trace :
#     le compte reste présent et lisible pendant toute l'enquête.
#  3. Le compte de service ne peut RIEN FAIRE D'AUTRE. Un SOAR compromis ne doit
#     pas pouvoir vider un annuaire. Cette partie-là se prouve par l'échec.
#
#  On conclut sur des CODES DE SORTIE.
# =============================================================================
set -uo pipefail

URI="${LDAP_URI:-ldap://10.50.20.20:389}"
BASE="${LDAP_BASE_DN:-dc=cenadi,dc=local}"
SOAR_DN="${LDAP_SOAR_DN:-cn=nexus-soar,ou=services,$BASE}"
CIBLE_UID="${CIBLE_UID:-agent_SIGIPES_0421}"
CIBLE_DN="uid=$CIBLE_UID,ou=agents,$BASE"
MDP_AGENT="${MDP_AGENT:-Cenadi@2026}"

GREEN="\033[32m"; RED="\033[31m"; BOLD="\033[1m"; RAZ="\033[0m"
# Le gabarit versionne (.env.example) nomme cette variable LDAP_SOAR_PASSWORD ;
# 04-annuaire-vm-app-gov.md disait LDAP_SOAR_PW. On accepte les deux et on
# aligne la documentation, plutot que de laisser deux noms circuler.
LDAP_SOAR_PASSWORD="${LDAP_SOAR_PASSWORD:-${LDAP_SOAR_PW:-}}"
: "${LDAP_SOAR_PASSWORD:?LDAP_SOAR_PASSWORD absent de l environnement}"

echec=0

soar() { ldapmodify -x -H "$URI" -D "$SOAR_DN" -w "$LDAP_SOAR_PASSWORD" "$@"; }

sonde() {  # $1 = PASSE|REFUSE attendu, $2 = libellé, $3… = commande
  local attendu="$1" quoi="$2"; shift 2
  "$@" >/dev/null 2>&1
  local code=$? obtenu="REFUSE"
  [[ $code -eq 0 ]] && obtenu="PASSE"
  if [[ "$obtenu" == "$attendu" ]]; then
    printf "    ${GREEN}✓${RAZ} %-46s %-6s (code %d)\n" "$quoi" "$obtenu" "$code"
  else
    printf "    ${RED}✗${RAZ} %-46s %-6s attendu %s (code %d)\n" "$quoi" "$obtenu" "$attendu" "$code"
    echec=1
  fi
}

authentifier() { ldapwhoami -x -H "$URI" -D "$CIBLE_DN" -w "$MDP_AGENT"; }
lire_compte()  { ldapsearch -x -LLL -H "$URI" -b "$CIBLE_DN" uid; }

geler() {
  soar <<EOF
dn: $CIBLE_DN
changetype: modify
replace: pwdAccountLockedTime
pwdAccountLockedTime: 000001010000Z
EOF
}

degeler() {
  soar <<EOF
dn: $CIBLE_DN
changetype: modify
delete: pwdAccountLockedTime
EOF
}

echo -e "${BOLD}Preuve de gel de compte — $CIBLE_UID${RAZ}"
echo   "  annuaire : $URI · compte de service : ${SOAR_DN%%,*}"

# ── 1. Avant ────────────────────────────────────────────────────────────────
echo -e "\n  ${BOLD}1. Avant toute décision du SOAR${RAZ}"
degeler >/dev/null 2>&1                     # départ propre
sonde PASSE  "le compte s'authentifie"              authentifier
sonde PASSE  "le compte est lisible dans l'annuaire" lire_compte

# ── 2. Gel ──────────────────────────────────────────────────────────────────
echo -e "\n  ${BOLD}2. Le SOAR gèle le compte${RAZ}"
sortie=$(geler 2>&1); code=$?
printf "    ldapmodify → %s (code %d)\n" "$(echo "$sortie" | tail -1)" "$code"

echo -e "\n  ${BOLD}3. Effet constaté${RAZ}"
# C'est ici que tout se joue : on ne croit pas le code de retour ci-dessus.
sonde REFUSE "authentification du compte gelé"       authentifier
sonde PASSE  "le compte reste lisible (enquête)"     lire_compte

# ── 4. Le compte de service n'a que ce droit-là ─────────────────────────────
echo -e "\n  ${BOLD}4. Périmètre du compte de service${RAZ}"
supprimer() { ldapdelete -x -H "$URI" -D "$SOAR_DN" -w "$LDAP_SOAR_PASSWORD" "$CIBLE_DN"; }
changer_mdp() {
  soar <<EOF
dn: $CIBLE_DN
changetype: modify
replace: userPassword
userPassword: injecte
EOF
}
sonde REFUSE "supprimer un compte"                   supprimer
sonde REFUSE "changer un mot de passe"               changer_mdp

# ── 5. Levée ────────────────────────────────────────────────────────────────
echo -e "\n  ${BOLD}5. Le SOAR dégèle${RAZ}"
degeler >/dev/null 2>&1
sonde PASSE  "le compte s'authentifie de nouveau"    authentifier

echo
if [[ $echec -eq 0 ]]; then
  echo -e "  ${GREEN}${BOLD}Recette complète : l'identité est suspendue, réversible, et le SOAR ne peut rien d'autre.${RAZ}"
else
  echo -e "  ${RED}${BOLD}Au moins une sonde a démenti l'attendu — voir ci-dessus.${RAZ}"
fi
exit $echec
