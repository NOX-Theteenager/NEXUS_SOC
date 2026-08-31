#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : preuve de la discussion d'incident (phase 4)
#
#      bash lab-cenadi/scenarios/10-preuve-discussion.sh
#
#  Ce que cette recette doit établir tient en deux phrases :
#
#    1. Escalader une alerte dans IRIS ouvre un canal d'incident, avec le
#       résumé, le risque, l'entité et les DEUX liens — l'enquête et le calcul.
#    2. **Une panne de Mattermost ne bloque RIEN.** Ni l'escalade, ni l'alerte,
#       ni la détection. C'est la propriété qui compte : un SOC qui s'arrête
#       parce que sa messagerie est en panne a confondu l'accessoire et
#       l'essentiel.
#
#  On conclut sur des CODES DE SORTIE.
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

SOC="${SOC_URL:-http://10.50.0.2:8000}"
CYCLE=40                      # deux tours de veille, large
GREEN="\033[32m"; RED="\033[31m"; JAUNE="\033[33m"; BOLD="\033[1m"; RAZ="\033[0m"
echec=0

set -a; . ./.env; set +a
: "${IRIS_API_KEY:?IRIS_API_KEY absent de l environnement}"
: "${MATTERMOST_TOKEN:?MATTERMOST_TOKEN absent — creer le robot d abord}"

psql() { docker exec nexus-postgres psql -U nexus -d nexus_soc -At -c "$1" 2>/dev/null; }
iris() { curl -sk -m15 -H "Authorization: Bearer $IRIS_API_KEY" \
              -H 'Content-Type: application/json' "$@"; }
mm()   { curl -s  -m15 -H "Authorization: Bearer $MATTERMOST_TOKEN" \
              -H 'Content-Type: application/json' "$@"; }

verifier() {  # $1 = attendu, $2 = libellé, $3 = obtenu
  if [[ "$3" == "$1" ]]; then
    printf "    ${GREEN}✓${RAZ} %-50s %s\n" "$2" "$3"
  else
    printf "    ${RED}✗${RAZ} %-50s %s (attendu %s)\n" "$2" "$3" "$1"
    echec=1
  fi
}
contient() {  # $1 = aiguille, $2 = libellé, $3 = botte de foin
  if grep -qF -- "$1" <<< "$3"; then
    printf "    ${GREEN}✓${RAZ} %-50s présent\n" "$2"
  else
    printf "    ${RED}✗${RAZ} %-50s ABSENT\n" "$2"
    echec=1
  fi
}

echo -e "${BOLD}Preuve de la discussion d'incident${RAZ}"

# ── 0. Une alerte déposée dans IRIS, à escalader ────────────────────────────
REF=$(psql "SELECT reference_source FROM dossier_sortie
             WHERE etat='envoye' AND dossier_externe IS NOT NULL
             ORDER BY id DESC LIMIT 1")
ALERTE_IRIS=$(psql "SELECT dossier_externe FROM dossier_sortie WHERE reference_source='$REF'")
[[ -z "$ALERTE_IRIS" ]] && { echo -e "${RED}✗ aucune alerte déposée dans IRIS${RAZ}"; exit 1; }
echo "    alerte IRIS #$ALERTE_IRIS · référence ${REF:0:13}…"

# On repart d'un état propre : la recette doit pouvoir se rejouer.
psql "DELETE FROM incident_canal WHERE reference_source='$REF'" >/dev/null

# ── 1. Mattermost en panne : l'escalade ne doit rien bloquer ────────────────
echo -e "\n  ${BOLD}1. Mattermost arrêté — l'escalade passe quand même${RAZ}"
docker stop nexus-mattermost >/dev/null 2>&1
sleep 3
CODE=$(iris -o /dev/null -w '%{http_code}' -X POST \
        -d '{"alert_status_id": 8}' "$IRIS_URL/alerts/update/$ALERTE_IRIS")
verifier "200" "IRIS accepte l'escalade sans Mattermost" "$CODE"
verifier "200" "l'ingestion répond toujours" \
  "$(curl -s -m8 -o /dev/null -w '%{http_code}' "$SOC/health")"
sleep "$CYCLE"
verifier "a_ouvrir" "l'escalade est notée, le canal reste à ouvrir" \
  "$(psql "SELECT etat FROM incident_canal WHERE reference_source='$REF'")"
verifier "OUI" "l'échec est consigné, pas tu" \
  "$( [[ -n "$(psql "SELECT derniere_erreur FROM incident_canal WHERE reference_source='$REF'")" ]] && echo OUI || echo NON )"

# ── 2. Mattermost revient : le canal s'ouvre tout seul ──────────────────────
echo -e "\n  ${BOLD}2. Mattermost redémarre — le canal s'ouvre sans intervention${RAZ}"
docker start nexus-mattermost >/dev/null 2>&1
echo "    attente de la remise en service…"
for _ in $(seq 1 30); do
  mm -o /dev/null "$MATTERMOST_URL/api/v4/system/ping" 2>/dev/null && break
  sleep 5
done
sleep "$CYCLE"
verifier "ouvert" "le canal a été ouvert" \
  "$(psql "SELECT etat FROM incident_canal WHERE reference_source='$REF'")"
CANAL=$(psql "SELECT canal_id FROM incident_canal WHERE reference_source='$REF'")
NOM=$(psql "SELECT canal_nom FROM incident_canal WHERE reference_source='$REF'")
verifier "OUI" "son nom porte la date de l'incident" \
  "$( [[ "$NOM" =~ ^incident-[0-9]{8}- ]] && echo OUI || echo NON )"

# ── 3. Ce que le canal contient ─────────────────────────────────────────────
echo -e "\n  ${BOLD}3. Le message d'ouverture se suffit à lui-même${RAZ}"
MSG=$(mm "$MATTERMOST_URL/api/v4/channels/$CANAL/posts" \
      | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('\n'.join(p['message'] for p in (d.get('posts') or {}).values()))" 2>/dev/null)
contient "$REF"                "le lien vers l'explicabilité NEXUS" "$MSG"
contient "alert_id=$ALERTE_IRIS" "le lien vers le dossier d'enquête"  "$MSG"
ENTITE=$(psql "SELECT a.entite FROM alerts a WHERE a.id::text='$REF'")
contient "$ENTITE"             "l'entité concernée"                 "$MSG"

# ── 4. Un incident n'a jamais deux canaux ───────────────────────────────────
echo -e "\n  ${BOLD}4. Rejouer la veille ne rouvre pas un second canal${RAZ}"
psql "UPDATE incident_canal SET etat='a_ouvrir' WHERE reference_source='$REF'" >/dev/null
sleep "$CYCLE"
verifier "$CANAL" "le même canal est retrouvé, pas un nouveau" \
  "$(psql "SELECT canal_id FROM incident_canal WHERE reference_source='$REF'")"
verifier "1" "une seule ligne pour cet incident" \
  "$(psql "SELECT count(*) FROM incident_canal WHERE reference_source='$REF'")"

echo
if [[ $echec -eq 0 ]]; then
  echo -e "  ${GREEN}${BOLD}Recette complète : le canal s'ouvre, et la messagerie ne bloque rien.${RAZ}"
else
  echo -e "  ${RED}${BOLD}Au moins une sonde a démenti l'attendu — voir ci-dessus.${RAZ}"
fi
exit $echec
