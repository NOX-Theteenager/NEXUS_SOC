#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : preuve des connecteurs de réponse (phase 2)
#
#      export NEXUS_ADMIN_EMAIL=… NEXUS_ADMIN_PASSWORD=…
#      bash lab-cenadi/scenarios/08-preuve-connecteurs.sh
#
#  La phase 1 a montré que le pare-feu obéissait à un appel d'API. Celle-ci
#  montre autre chose : que la PLATEFORME décide, applique, vérifie, et sait
#  dire non. Tout passe par /analyst — aucun appel direct à l'équipement.
#
#  LES TROIS GARDE-FOUS, ÉPROUVÉS UN PAR UN
#  ----------------------------------------
#  1. Une décision humaine d'abord : on n'exécute que ce qui a été approuvé.
#  2. « Exécutée » ne s'écrit qu'après RELECTURE de l'équipement. Un HTTP 200
#     ne suffit pas — OPNsense accepte une adresse dans un alias inutilisé,
#     OpenLDAP accepte un attribut qu'il ignore.
#  3. Un échec ne ment pas : l'action reste « non_executee », le motif est
#     consigné, et la commande manuelle revient comme avant les connecteurs.
#
#  On conclut sur des CODES DE SORTIE.
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

SOC="${SOC_URL:-http://10.50.0.2:8000}"
HOTE_TEST="${HOTE_TEST:-SRV-APP-GOV-01}"
IP_TEST="${IP_TEST:-10.50.20.20}"
HOTE_PROTEGE="${HOTE_PROTEGE:-NoxTheMachine}"      # le cœur SOC lui-même
ALIAS="${OPNSENSE_ALIAS_QUARANTAINE:-nexus_quarantaine}"
PERIMETRE_TEST="11111111-1111-1111-1111-111111111111"

GREEN="\033[32m"; RED="\033[31m"; BOLD="\033[1m"; RAZ="\033[0m"
: "${NEXUS_ADMIN_EMAIL:?NEXUS_ADMIN_EMAIL absent de l environnement}"
: "${NEXUS_ADMIN_PASSWORD:?NEXUS_ADMIN_PASSWORD absent de l environnement}"

echec=0
psql() { docker exec nexus-postgres psql -U nexus -d nexus_soc -At -c "$1" 2>/dev/null; }

JWT=$(curl -s -m10 -X POST "$SOC/auth/token" -H 'Content-Type: application/json' \
      -d "{\"email\":\"$NEXUS_ADMIN_EMAIL\",\"password\":\"$NEXUS_ADMIN_PASSWORD\"}" \
      | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
[[ -z "$JWT" ]] && { echo -e "${RED}✗ authentification refusée${RAZ}"; exit 1; }

api() {  # $1 = méthode+chemin, $2 = corps JSON
  curl -s -m45 -X POST "$SOC$1" -H "Authorization: Bearer $JWT" \
       -H 'Content-Type: application/json' -d "${2:-\{\}}"
}
champ() { python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('$1',''))" 2>/dev/null; }

sonde() {  # $1 = attendu, $2 = libellé, $3… = commande
  local attendu="$1" quoi="$2"; shift 2
  "$@" >/dev/null 2>&1
  local code=$? obtenu="NON"
  [[ $code -eq 0 ]] && obtenu="OUI"
  if [[ "$obtenu" == "$attendu" ]]; then
    printf "    ${GREEN}✓${RAZ} %-48s %-3s\n" "$quoi" "$obtenu"
  else
    printf "    ${RED}✗${RAZ} %-48s %-3s attendu %s\n" "$quoi" "$obtenu" "$attendu"
    echec=1
  fi
}

verifier() {  # $1 = attendu, $2 = libellé, $3 = obtenu
  if [[ "$3" == "$1" ]]; then
    printf "    ${GREEN}✓${RAZ} %-48s %s\n" "$2" "$3"
  else
    printf "    ${RED}✗${RAZ} %-48s %s (attendu %s)\n" "$2" "$3" "$1"
    echec=1
  fi
}

# `soar_audit.alert_id` référence `alerts` : une action de réponse se rattache
# toujours à un fait observé, jamais à un identifiant inventé. La recette
# s'accroche donc à une alerte réelle du périmètre.
ALERTE=$(psql "SELECT id FROM alerts WHERE tenant_id='$PERIMETRE_TEST' ORDER BY 1 LIMIT 1")
[[ -z "$ALERTE" ]] && { echo -e "${RED}✗ aucune alerte sur ce périmètre — alimenter d abord${RAZ}"; exit 1; }

creer_action() {  # $1 = action, $2 = cible, $3 = type ; renvoie l'id
  psql "INSERT INTO soar_audit (alert_id, tenant_id, action, impact, statut,
          detail, cible, cible_type, execution)
        VALUES ('$ALERTE', '$PERIMETRE_TEST', '$1', 'fort',
                'EN ATTENTE DE VALIDATION', 'Recette phase 2 — connecteurs',
                '$2', '$3', 'non_executee') RETURNING id" | head -1
}

echo -e "${BOLD}Preuve des connecteurs de réponse${RAZ}"
echo   "  tout passe par $SOC/analyst — aucun appel direct à l'équipement"

# ── 1. Décision puis exécution ──────────────────────────────────────────────
echo -e "\n  ${BOLD}1. Approuver, puis exécuter${RAZ}"
ID=$(creer_action isolate_host "$HOTE_TEST" hote)
echo "    action $ID créée sur $HOTE_TEST"
verifier "OUI" "l'exécution est refusée avant approbation" \
  "$( [[ $(curl -s -m20 -o /dev/null -w '%{http_code}' -X POST "$SOC/analyst/execute/$ID" \
        -H "Authorization: Bearer $JWT") == "404" ]] && echo OUI || echo NON )"
api "/analyst/approve/$ID" '{"approved_by":"recette"}' >/dev/null
REP=$(api "/analyst/execute/$ID" '{"executed_by":"recette"}')
verifier "True" "exécution rapportée réussie" "$(echo "$REP" | champ execute)"
verifier "$IP_TEST" "nom d'hôte résolu en adresse" "$(echo "$REP" | champ cible_equipement)"
verifier "automatique" "audit marqué exécuté automatiquement" \
  "$(psql "SELECT execution FROM soar_audit WHERE id=$ID")"

# ── 2. Effet réel ───────────────────────────────────────────────────────────
echo -e "\n  ${BOLD}2. Effet réel sur la machine${RAZ}"
sleep 2
sonde NON "SOC → $HOTE_TEST joignable"          ping -c2 -W3 "$IP_TEST"
sonde OUI "SOC → vm-rssi joignable (témoin)"    ping -c2 -W3 10.50.40.40
sleep 35
verifier "OUI" "la machine isolée émet toujours sa télémétrie" \
  "$(psql "SELECT CASE WHEN vu_le > now()-interval '90 seconds' THEN 'OUI' ELSE 'NON' END
           FROM agents WHERE hostname='$HOTE_TEST'")"

# ── 3. Réconciliation ───────────────────────────────────────────────────────
echo -e "\n  ${BOLD}3. La mesure survit à une purge de la table${RAZ}"
python3 lab-cenadi/scripts/opnsense-console.py "pfctl -t $ALIAS -T flush" >/dev/null 2>&1
sleep 2
sonde OUI "après purge : la quarantaine est tombée" ping -c2 -W3 "$IP_TEST"
# On ne compte pas les écarts : le parc en porte d'anciens, hérités d'actions
# marquées « exécutées » avant que les connecteurs n'existent. On vérifie que
# NOTRE mesure a été reposée, ce qui est la seule chose que cette étape prouve.
RECONC=$(api "/analyst/reconcile")
verifier "OUI" "la réconciliation repose la mesure attendue" \
  "$( grep -q "$IP_TEST : reposée" <<< "$RECONC" && echo OUI || echo NON )"
sleep 2
sonde NON "après réconciliation : quarantaine reposée" ping -c2 -W3 "$IP_TEST"

# ── 4. Levée ────────────────────────────────────────────────────────────────
echo -e "\n  ${BOLD}4. Lever${RAZ}"
REP=$(api "/analyst/revert/$ID" '{"reverted_by":"recette"}')
verifier "True" "levée rapportée réussie" "$(echo "$REP" | champ leve)"
verifier "annulee" "audit marqué annulé" "$(psql "SELECT execution FROM soar_audit WHERE id=$ID")"
sleep 2
sonde OUI "SOC → $HOTE_TEST de nouveau joignable" ping -c2 -W3 "$IP_TEST"

# ── 4 bis. L'autre connecteur : l'annuaire ──────────────────────────────────
# Le pare-feu coupe un câble ; l'annuaire suspend une identité. Un compte volé
# reste utilisable depuis n'importe quelle machine tant que l'annuaire
# l'accepte : c'est le seul verrou qu'aucune topologie ne peut poser.
echo -e "\n  ${BOLD}4 bis. Geler une identité, par la plateforme${RAZ}"
COMPTE="${COMPTE_TEST:-agent_SIGIPES_0421}"
IDC=$(creer_action freeze_account "$COMPTE" compte)
api "/analyst/approve/$IDC" '{"approved_by":"recette"}' >/dev/null
REP=$(api "/analyst/execute/$IDC" '{"executed_by":"recette"}')
verifier "True" "gel rapporté réussi" "$(echo "$REP" | champ execute)"
verifier "ldap" "connecteur employé" "$(echo "$REP" | champ connecteur)"
# On ne croit pas la plateforme sur parole : on tente une authentification.
sonde NON "le compte gelé ne s'authentifie plus" \
  ldapwhoami -x -H "${LDAP_URI:-ldap://10.50.20.20:389}" \
    -D "uid=$COMPTE,ou=agents,${LDAP_BASE_DN:-dc=cenadi,dc=local}" -w "${MDP_AGENT:-Cenadi@2026}"
REP=$(api "/analyst/revert/$IDC" '{"reverted_by":"recette"}')
verifier "True" "dégel rapporté réussi" "$(echo "$REP" | champ leve)"
sonde OUI "le compte s'authentifie de nouveau" \
  ldapwhoami -x -H "${LDAP_URI:-ldap://10.50.20.20:389}" \
    -D "uid=$COMPTE,ou=agents,${LDAP_BASE_DN:-dc=cenadi,dc=local}" -w "${MDP_AGENT:-Cenadi@2026}"

# ── 5. Ce que la plateforme REFUSE de faire ─────────────────────────────────
echo -e "\n  ${BOLD}5. Refus — c'est là que se juge une réponse automatique${RAZ}"
IDP=$(creer_action isolate_host "$HOTE_PROTEGE" hote)
api "/analyst/approve/$IDP" '{}' >/dev/null
REP=$(api "/analyst/execute/$IDP" '{}')
verifier "False" "isoler le cœur SOC lui-même : refusé" "$(echo "$REP" | champ execute)"
verifier "non_executee" "l'audit ne prétend pas l'avoir fait" \
  "$(psql "SELECT execution FROM soar_audit WHERE id=$IDP")"
verifier "OUI" "la commande manuelle est tout de même fournie" \
  "$( [[ -n "$(echo "$REP" | champ commande)" ]] && echo OUI || echo NON )"

IDT=$(creer_action block_ip "$HOTE_TEST" hote)
api "/analyst/approve/$IDT" '{}' >/dev/null
REP=$(api "/analyst/execute/$IDT" '{}')
verifier "False" "block_ip sur un nom d'hôte : refusé" "$(echo "$REP" | champ execute)"

echo
if [[ $echec -eq 0 ]]; then
  echo -e "  ${GREEN}${BOLD}Recette complète : la plateforme applique, vérifie, lève — et refuse ce qu'elle ne doit pas faire.${RAZ}"
else
  echo -e "  ${RED}${BOLD}Au moins une sonde a démenti l'attendu — voir ci-dessus.${RAZ}"
fi
exit $echec
