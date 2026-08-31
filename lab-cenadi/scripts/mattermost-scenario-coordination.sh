#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : mise en scène d'une coordination d'incident
#
#      CANAL=incident-AAAAMMJJ-xxxxxxxx \
#      bash lab-cenadi/scripts/mattermost-scenario-coordination.sh
#
#  ────────────────────────────────────────────────────────────────────────
#  CE SCRIPT MET EN SCÈNE. IL NE CONSTATE PAS.
#  ────────────────────────────────────────────────────────────────────────
#  Les messages publiés ici sont écrits d'avance. Ils illustrent la façon dont
#  une cellule se coordonnerait autour d'un incident ; ils ne sont pas la trace
#  d'un échange réel entre des personnes.
#
#  Les comptes portent des noms de RÔLES du laboratoire — `rssi-cenadi`,
#  `operateur-cenadi`, `dsi-cenadi` — et jamais le nom d'une personne. Toute
#  figure produite à partir de ce canal doit être légendée comme une
#  **simulation de coordination**, au même titre que les attaques rejouées
#  depuis KaliPrime. La présenter autrement serait présenter une conversation
#  fabriquée comme une preuve d'intervention.
#
#  Ce qui est DIT dans ces messages, en revanche, correspond à ce que la
#  plateforme a réellement fait : la quarantaine a bien été appliquée, la
#  télémétrie a bien continué de parvenir, et la réserve sur les sessions
#  établies est bien celle que l'audit consigne.
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

set -a; . ./.env; set +a
URL="${MATTERMOST_URL:-http://10.50.0.2:8065}"
EQUIPE="${MATTERMOST_EQUIPE:-cenadi-soc}"
CANAL="${CANAL:?CANAL attendu — nom du canal d incident}"
GREEN="\033[32m"; RED="\033[31m"; JAUNE="\033[33m"; RAZ="\033[0m"

echo -e "${JAUNE}Mise en scène — les messages sont écrits d'avance, pas constatés.${RAZ}"
echo

ADMIN_MDP=$(head -1 /var/tmp/nexus-opnsense/mm-admin.txt)
JETON=$(curl -s -m20 -i -H 'Content-Type: application/json' -X POST \
        -d "$(python3 -c "import json,sys;print(json.dumps({'login_id':'nexus-admin','password':sys.argv[1]}))" "$ADMIN_MDP")" \
        "$URL/api/v4/users/login" | grep -i '^token:' | tr -d '\r' | awk '{print $2}')
[[ -z "$JETON" ]] && { echo -e "${RED}✗ connexion administrateur refusée${RAZ}"; exit 1; }
auth() { curl -s -m20 -H "Authorization: Bearer $JETON" -H 'Content-Type: application/json' "$@"; }

EQ=$(auth "$URL/api/v4/teams/name/$EQUIPE" | python3 -c "
import sys,json,re
v=str(json.load(sys.stdin).get('id',''))
print(v if re.fullmatch(r'[a-z0-9]{26}',v) else '')")
CANAL_ID=$(auth "$URL/api/v4/teams/$EQ/channels/name/$CANAL" | python3 -c "
import sys,json,re
v=str(json.load(sys.stdin).get('id',''))
print(v if re.fullmatch(r'[a-z0-9]{26}',v) else '')")
[[ -z "$CANAL_ID" ]] && { echo -e "${RED}✗ canal « $CANAL » introuvable${RAZ}"; exit 1; }

MDP_ROLE="Cenadi@Lab2026!"

creer_role() {  # $1 = identifiant, $2 = libellé
  local id="$1" libelle="$2"
  docker exec nexus-mattermost mmctl --local user create \
      --email "$id@cenadi.local" --username "$id" --password "$MDP_ROLE" \
      --firstname "$libelle" >/dev/null 2>&1
  local uid
  uid=$(auth "$URL/api/v4/users/username/$id" | python3 -c "
import sys,json,re
v=str(json.load(sys.stdin).get('id',''))
print(v if re.fullmatch(r'[a-z0-9]{26}',v) else '')")
  [[ -z "$uid" ]] && { echo -e "  ${RED}✗ compte $id absent${RAZ}"; return 1; }
  auth -o /dev/null -X POST -d "{\"team_id\":\"$EQ\",\"user_id\":\"$uid\"}" "$URL/api/v4/teams/$EQ/members"
  auth -o /dev/null -X POST -d "{\"user_id\":\"$uid\"}" "$URL/api/v4/channels/$CANAL_ID/members"
  echo -e "  ${GREEN}✓${RAZ} $id — $libelle"
  echo "$uid"
}

publier() {  # $1 = identifiant du rôle, $2 = message
  local jeton
  jeton=$(curl -s -m20 -i -H 'Content-Type: application/json' -X POST \
          -d "$(python3 -c "import json,sys;print(json.dumps({'login_id':sys.argv[1],'password':sys.argv[2]}))" "$1" "$MDP_ROLE")" \
          "$URL/api/v4/users/login" | grep -i '^token:' | tr -d '\r' | awk '{print $2}')
  [[ -z "$jeton" ]] && { echo -e "  ${RED}✗ $1 ne peut pas publier${RAZ}"; return 1; }
  curl -s -m20 -o /dev/null -H "Authorization: Bearer $jeton" -H 'Content-Type: application/json' \
       -X POST -d "$(python3 -c "import json,sys;print(json.dumps({'channel_id':sys.argv[1],'message':sys.argv[2]}))" "$CANAL_ID" "$2")" \
       "$URL/api/v4/posts"
  sleep 1
}

echo "  Comptes de rôle :"
creer_role rssi-cenadi      "RSSI (rôle de laboratoire)"      >/dev/null
creer_role operateur-cenadi "Opérateur SOC (rôle de laboratoire)" >/dev/null
creer_role dsi-cenadi       "DSI (rôle de laboratoire)"       >/dev/null

echo
echo "  Échange :"
publier rssi-cenadi "Je prends l'incident. La machine est bien en quarantaine côté pare-feu — je vois les rejets dans la vue temps réel."
publier operateur-cenadi "Confirmé de mon côté : l'alias \`nexus_quarantaine\` contient bien l'adresse, relue sur l'appliance. La télémétrie de la machine continue d'arriver sur le cœur SOC, on ne l'a pas perdue de vue."
publier rssi-cenadi "C'est ce qui compte. **Réserve à connaître** : les sessions déjà ouvertes ne sont pas coupées — le compte de service n'a pas le privilège de purger les états. L'isolation ne vaut donc que pour les nouvelles connexions."
publier operateur-cenadi "Noté. J'ai versé la chaîne reconstituée dans la chronologie du dossier IRIS, et les sept observables sont importés. Dossier passé en **confinement**."
publier dsi-cenadi "Merci. Périmètre Réseau/LAN CENADI, aucune donnée ANTILOPE concernée — je n'ouvre pas de communication de crise à ce stade. Tenez-moi au courant avant toute levée de la quarantaine."
publier rssi-cenadi "Entendu. La levée passera par la console, avec relecture de l'alias — elle sera tracée dans \`soar_audit\` au même titre que la pose."

echo
echo -e "  ${GREEN}Échange publié dans #$CANAL${RAZ}"
echo -e "  ${JAUNE}Rappel : à légender comme une simulation de coordination.${RAZ}"
