#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : première mise en service de Mattermost
#
#      bash lab-cenadi/scripts/mattermost-amorcer.sh
#
#  Crée, dans cet ordre : l'administrateur, l'équipe du SOC, le robot qui
#  publie les incidents, et son jeton. Le jeton part dans `.env`.
#
#  POURQUOI UN ROBOT ET PAS UN COMPTE ORDINAIRE
#  --------------------------------------------
#  Ses publications sont visiblement signées « BOT ». Personne ne confond un
#  résumé automatique avec l'avis d'un collègue — ce qui compte le jour où la
#  conversation servira à justifier une décision. Un robot ne consomme pas non
#  plus de licence et ne peut pas lire les messages privés.
#
#  Idempotent : relançable. Ce qui existe déjà est réutilisé, pas recréé.
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

URL="${MATTERMOST_URL:-http://10.50.0.2:8065}"
EQUIPE="${MATTERMOST_EQUIPE:-cenadi-soc}"
ADMIN_MAIL="${MM_ADMIN_EMAIL:-soc@cenadi.local}"
ADMIN_NOM="${MM_ADMIN_LOGIN:-nexus-admin}"

GREEN="\033[32m"; RED="\033[31m"; RAZ="\033[0m"
api() { curl -s -m20 -H 'Content-Type: application/json' "$@"; }

echo "Amorçage de Mattermost — $URL"

# ── 1. Attendre que le service réponde ──────────────────────────────────────
printf "  service… "
for _ in $(seq 1 60); do
  api -o /dev/null -w '' "$URL/api/v4/system/ping" 2>/dev/null && break
  sleep 5
done
ETAT=$(api -o /dev/null -w '%{http_code}' "$URL/api/v4/system/ping")
[[ "$ETAT" != "200" ]] && { echo -e "${RED}injoignable (HTTP $ETAT)${RAZ}"; exit 1; }
echo -e "${GREEN}prêt${RAZ}"

# ── 2. Administrateur ───────────────────────────────────────────────────────
# Le premier compte créé sur une instance vierge devient administrateur système.
umask 077
FIC=/var/tmp/nexus-opnsense/mm-admin.txt
if [[ -s "$FIC" ]]; then
  MDP=$(head -1 "$FIC")
  echo "  administrateur : mot de passe déjà connu"
else
  MDP=$(openssl rand -base64 30 | tr -d '/+=\n' | cut -c1-24)Aa1!
  printf '%s\n' "$MDP" > "$FIC"; chmod 600 "$FIC"
  # Par mmctl et non par l'API : l'inscription par courriel est DÉSACTIVÉE sur
  # cette instance (le SOC n'ouvre pas ses canaux au premier venu), ce qui
  # empêche aussi de créer le premier administrateur. mmctl passe par une prise
  # UNIX interne au conteneur, exposée sur aucun réseau.
  REP=$(docker exec nexus-mattermost mmctl --local user create \
          --email "$ADMIN_MAIL" --username "$ADMIN_NOM" \
          --password "$MDP" --system-admin 2>&1)
  # On ne cherche PAS un champ « id » : une réponse d'ERREUR de Mattermost en
  # contient un aussi, et l'échec passerait pour un succès. On demande au
  # serveur si le compte existe — la seule question qui tranche.
  if docker exec nexus-mattermost mmctl --local user search "$ADMIN_NOM" 2>/dev/null \
       | grep -q "$ADMIN_NOM"; then
    echo -e "  administrateur : ${GREEN}créé${RAZ} ($ADMIN_NOM)"
  else
    echo -e "  ${RED}✗ administrateur non créé${RAZ} — $(head -c 160 <<< "$REP")"
    exit 1
  fi
fi

JETON=$(curl -s -m20 -i -H 'Content-Type: application/json' -X POST \
        -d "{\"login_id\":\"$ADMIN_NOM\",\"password\":\"$MDP\"}" \
        "$URL/api/v4/users/login" | grep -i '^token:' | tr -d '\r' | awk '{print $2}')
[[ -z "$JETON" ]] && { echo -e "  ${RED}✗ connexion administrateur refusée${RAZ}"; exit 1; }
auth() { curl -s -m20 -H "Authorization: Bearer $JETON" -H 'Content-Type: application/json' "$@"; }
MOI=$(auth "$URL/api/v4/users/me" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo -e "  session      : ${GREEN}ouverte${RAZ}"

# ── 3. Équipe ───────────────────────────────────────────────────────────────
# `id` NE PROUVE RIEN. Les réponses d'ERREUR de Mattermost portent elles aussi
# un champ « id » — ici « app.team.get_by_name.missing.app_error ». Le lire sans
# précaution fait conclure « équipe déjà présente » sur un 404, et la veille
# échoue ensuite sans qu'on comprenne pourquoi. Cela s'est produit le 29 août.
#
# On exige donc un identifiant Mattermost véritable : 26 caractères, et pas de
# point. Un identifiant d'erreur en contient toujours.
extraire_id() {
  python3 -c "
import sys, json, re
try:
    v = str(json.load(sys.stdin).get('id', ''))
except Exception:
    v = ''
print(v if re.fullmatch(r'[a-z0-9]{26}', v) else '')"
}
EQ=$(auth "$URL/api/v4/teams/name/$EQUIPE" | extraire_id)
if [[ -z "$EQ" ]]; then
  EQ=$(auth -X POST -d "{\"name\":\"$EQUIPE\",\"display_name\":\"SOC CENADI\",\"type\":\"I\"}" \
       "$URL/api/v4/teams" | extraire_id)
  echo -e "  équipe       : ${GREEN}créée${RAZ} ($EQUIPE, invitation seulement)"
else
  echo "  équipe       : déjà présente"
fi
[[ -z "$EQ" ]] && { echo -e "  ${RED}✗ équipe introuvable${RAZ}"; exit 1; }
auth -o /dev/null -X POST -d "{\"team_id\":\"$EQ\",\"user_id\":\"$MOI\"}" "$URL/api/v4/teams/$EQ/members"

# ── 4. Robot ────────────────────────────────────────────────────────────────
BOT=$(auth "$URL/api/v4/bots" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(next((b['user_id'] for b in (d if isinstance(d, list) else [])
            if b.get('username') == 'nexus-soc'), ''))" 2>/dev/null)
if [[ -z "$BOT" ]]; then
  BOT=$(auth -X POST -d '{"username":"nexus-soc","display_name":"NEXUS SOC","description":"Publie les incidents escalades. Ne lit rien."}' \
        "$URL/api/v4/bots" | python3 -c "
import sys, json, re
try:
    v = str(json.load(sys.stdin).get('user_id', ''))
except Exception:
    v = ''
print(v if re.fullmatch(r'[a-z0-9]{26}', v) else '')")
  echo -e "  robot        : ${GREEN}créé${RAZ} (nexus-soc)"
else
  echo "  robot        : déjà présent"
fi
[[ -z "$BOT" ]] && { echo -e "  ${RED}✗ robot introuvable${RAZ}"; exit 1; }
auth -o /dev/null -X POST -d "{\"team_id\":\"$EQ\",\"user_id\":\"$BOT\"}" "$URL/api/v4/teams/$EQ/members"

# ── 5. Jeton du robot ───────────────────────────────────────────────────────
# Le robot doit pouvoir créer des canaux : sans ce rôle, il publierait dans des
# canaux qu'un humain devrait ouvrir d'avance — c'est-à-dire jamais au bon
# moment.
auth -o /dev/null -X PUT -d '{"roles":"system_user system_post_all"}' "$URL/api/v4/users/$BOT/roles"
JETON_BOT=$(auth -X POST -d '{"description":"NEXUS SOC — publication des incidents"}' \
            "$URL/api/v4/users/$BOT/tokens" \
            | python3 -c "import sys,json;print(json.load(sys.stdin).get('token',''))")
[[ -z "$JETON_BOT" ]] && { echo -e "  ${RED}✗ jeton du robot non délivré${RAZ}"; exit 1; }

python3 - "$JETON_BOT" "$EQUIPE" <<'FINPY'
import sys
jeton, equipe = sys.argv[1], sys.argv[2]
lignes = open('.env', encoding='utf-8').read().split('\n')
valeurs = {'MATTERMOST_TOKEN': jeton, 'MATTERMOST_EQUIPE': equipe}
vus = set()
for i, l in enumerate(lignes):
    cle = l.split('=', 1)[0].strip()
    if cle in valeurs:
        lignes[i] = f'{cle}={valeurs[cle]}'
        vus.add(cle)
manquants = [f'{c}={v}' for c, v in valeurs.items() if c not in vus]
if manquants:
    lignes += ['', '# Robot Mattermost — publie les incidents escalades.'] + manquants
open('.env', 'w', encoding='utf-8').write('\n'.join(lignes))
print("  jeton        : \033[32mécrit dans .env\033[0m")
FINPY
chmod 600 .env

echo
echo "  Interface  : $URL  (utilisateur $ADMIN_NOM)"
echo "  Mot de passe administrateur : $FIC"
echo "  Redémarrer le cœur SOC pour que la veille prenne le jeton :"
echo "      sudo systemctl restart nexus-soc"
