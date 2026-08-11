#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC — Cutover de la base de production vers le schéma REFONTE (CENADI)
# -----------------------------------------------------------------------------
# Aligne la base live (ancien schéma : offre / colonnes PLG) sur le code refonte
# (colonne criticite, périmètres CENADI). Ne contient QUE des données de démo.
#
# IMPORTANT : ce script ARRÊTE le service nexus-soc pendant la migration (sinon
# ses connexions verrouillent les tables et la suppression se bloque). Le site
# est indisponible ~1 minute, puis le service redémarre automatiquement.
#
# Usage :  bash cutover_prod_refonte.sh
# =============================================================================
set -euo pipefail

DB_CONTAINER="nexus-postgres"
DB_USER="nexus"
DB_NAME="nexus_soc"
BK_DIR="$HOME/nexus-soc-backups"
mkdir -p "$BK_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
BK="$BK_DIR/prod_pre_cutover_$TS.sql"

psql() { docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" "$@"; }

# sudo seulement si nécessaire pour systemctl
SC="systemctl"
if ! systemctl stop nexus-soc >/dev/null 2>&1; then SC="sudo systemctl"; fi

echo "== 1/6  Backup de sécurité =="
docker exec -i "$DB_CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" > "$BK"
if [ ! -s "$BK" ]; then echo "   ✗ backup vide — ARRÊT"; exit 1; fi
echo "   → $BK  ($(du -h "$BK" | cut -f1))"

echo "== 2/6  Arrêt du service nexus-soc (libère les verrous) =="
$SC stop nexus-soc || true
sleep 2
echo "   nexus-soc : $(systemctl is-active nexus-soc 2>/dev/null || echo inconnu)"

echo "== 3/6  Fermeture des connexions restantes à la base =="
psql -q -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true

echo "== 4/6  Suppression des tables (ancien schéma + PLG) =="
psql -v ON_ERROR_STOP=1 -q <<'SQL'
SET lock_timeout = '15s';
DO $$ DECLARE r RECORD; BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
    EXECUTE 'DROP TABLE IF EXISTS public.'||quote_ident(r.tablename)||' CASCADE';
  END LOOP;
END $$;
DROP FUNCTION IF EXISTS suspend_expired_trials() CASCADE;
SQL
echo "   tables restantes : $(psql -tA -c "SELECT count(*) FROM pg_tables WHERE schemaname='public';")"

echo "== 5/6  Ré-application des schémas refonte + seed CENADI =="
for f in Lot0_Socle/01_schema_patched.sql \
         Lot7_Console_Fournisseur/01_schema_analyst.sql \
         Lot7_Console_Fournisseur/01_schema_provisioning.sql \
         Lot0_Socle/03_schema_notifications.sql \
         Lot0_Socle/02_seed_demo.sql; do
  printf "   %-52s" "$f"
  if psql -v ON_ERROR_STOP=1 -q < "$f" >/tmp/nexus_cutover.log 2>&1; then
    echo "OK"
  else
    echo "ÉCHEC"; tail -5 /tmp/nexus_cutover.log
    echo "   → Rollback : docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME < \"$BK\""
    $SC start nexus-soc || true
    exit 1
  fi
done

echo "== 6/6  Redémarrage du service + vérification =="
$SC start nexus-soc || true
for i in $(seq 1 40); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health 2>/dev/null)" = "200" ] && break
  sleep 2
done
TOK=$(curl -s -X POST http://127.0.0.1:8000/auth/token -H 'Content-Type: application/json' \
      -d '{"email":"admin@nexussoc.cm","password":"admin"}' \
      | python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null)
echo "   /health           -> $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health)"
echo "   /admin/perimetres -> $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/admin/perimetres -H "Authorization: Bearer $TOK")"
echo "   /admin/tenants    -> $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/admin/tenants -H "Authorization: Bearer $TOK")"

echo
echo "✅ Cutover terminé. Périmètres : SIGIPES, ANTILOPE, Réseau/LAN CENADI."
echo "   Comptes (mdp: admin) : admin@nexussoc.cm · soc@nexussoc.cm · resp.sigipes@cenadi.cm"
echo "   ROLLBACK si besoin :"
echo "     docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME < \"$BK\""
