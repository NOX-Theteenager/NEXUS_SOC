#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC — Script de sauvegarde complète
# Usage : sudo bash backup.sh [--dest /chemin/backup] [--compress]
# Sauvegarde : PostgreSQL/TimescaleDB + index Wazuh + modèles IA + configuration
# =============================================================================
set -euo pipefail

DEST="${BACKUP_DEST:-/opt/nexus-backups}"
COMPRESS="${COMPRESS:-true}"
KEEP_DAYS="${KEEP_DAYS:-14}"           # conserver les N derniers jours
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="${DEST}/nexus_${TS}"
LOG="${DEST}/backup.log"
DB_CONTAINER="nexus-postgres"
DB_NAME="${POSTGRES_DB:-nexus_soc}"
DB_USER="${POSTGRES_USER:-nexus}"
WAZUH_INDEXER_CONTAINER="nexus-wazuh-indexer"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*" | tee -a "$LOG"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*" | tee -a "$LOG"; }
fail()    { echo -e "${RED}[FAIL]${NC} $*" | tee -a "$LOG"; exit 1; }

# Arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)     DEST="$2"; BACKUP_DIR="${DEST}/nexus_${TS}"; shift 2 ;;
    --compress) COMPRESS=true; shift ;;
    --no-compress) COMPRESS=false; shift ;;
    *) fail "Argument inconnu : $1" ;;
  esac
done

mkdir -p "$BACKUP_DIR"
info "=== Sauvegarde NEXUS SOC démarrée → $BACKUP_DIR ==="

# ────────────────────────────────────────────────────────────────────────────
# 1. PostgreSQL / TimescaleDB (dump complet)
# ────────────────────────────────────────────────────────────────────────────
info "1/4 PostgreSQL dump..."
PG_DUMP_FILE="${BACKUP_DIR}/nexus_postgres_${TS}.sql"
if docker exec "$DB_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" > "$PG_DUMP_FILE" 2>>"$LOG"; then
  ROWS=$(wc -l < "$PG_DUMP_FILE")
  info "    → ${ROWS} lignes SQL sauvegardées dans $(basename $PG_DUMP_FILE)"
  if [[ "$COMPRESS" == "true" ]]; then
    gzip -f "$PG_DUMP_FILE"
    info "    → compressé en $(basename $PG_DUMP_FILE).gz"
  fi
else
  warn "    PostgreSQL dump échoué (conteneur arrêté ?). Sauvegarde du volume brut..."
  PG_VOLUME=$(docker inspect "$DB_CONTAINER" --format '{{ range .Mounts }}{{ if eq .Destination "/var/lib/postgresql/data" }}{{ .Source }}{{ end }}{{ end }}' 2>/dev/null || echo "")
  if [[ -n "$PG_VOLUME" ]]; then
    tar -czf "${BACKUP_DIR}/nexus_pg_volume_${TS}.tar.gz" -C "$(dirname $PG_VOLUME)" "$(basename $PG_VOLUME)"
    info "    → volume brut sauvegardé"
  fi
fi

# ────────────────────────────────────────────────────────────────────────────
# 2. Wazuh Indexer (snapshot via API Elasticsearch-compatible)
# ────────────────────────────────────────────────────────────────────────────
info "2/4 Wazuh Indexer snapshot..."
WAZUH_API="https://localhost:9200"
SNAP_REPO="nexus_backup"
SNAP_NAME="nexus_snap_${TS}"

# Créer le dépôt de snapshot (répertoire partagé)
SNAP_DIR="${BACKUP_DIR}/wazuh_snapshot"
mkdir -p "$SNAP_DIR"

# Enregistrer le dépôt si nécessaire
CURL_OPTS="-k -s -u admin:admin -H 'Content-Type: application/json'"
REGISTER=$(curl -k -s -u admin:admin -X PUT "${WAZUH_API}/_snapshot/${SNAP_REPO}" \
  -H 'Content-Type: application/json' \
  -d "{\"type\":\"fs\",\"settings\":{\"location\":\"${SNAP_DIR}\"}}" 2>/dev/null || echo "")
if echo "$REGISTER" | grep -q '"acknowledged":true'; then
  # Lancer le snapshot
  SNAP_RESULT=$(curl -k -s -u admin:admin -X PUT "${WAZUH_API}/_snapshot/${SNAP_REPO}/${SNAP_NAME}?wait_for_completion=true" 2>/dev/null || echo "")
  if echo "$SNAP_RESULT" | grep -q '"SUCCESS"\|"state":"SUCCESS"'; then
    info "    → Snapshot Wazuh créé : ${SNAP_NAME}"
  else
    warn "    Snapshot Wazuh échoué : ${SNAP_RESULT:0:120}"
  fi
else
  warn "    API Wazuh Indexer inaccessible — sauvegarde du volume brut..."
  WAZUH_VOLUME=$(docker inspect "$WAZUH_INDEXER_CONTAINER" --format '{{ range .Mounts }}{{ if eq .Destination "/var/lib/wazuh-indexer" }}{{ .Source }}{{ end }}{{ end }}' 2>/dev/null || echo "")
  if [[ -n "$WAZUH_VOLUME" ]]; then
    tar -czf "${BACKUP_DIR}/wazuh_volume_${TS}.tar.gz" -C "$(dirname $WAZUH_VOLUME)" "$(basename $WAZUH_VOLUME)" 2>>"$LOG" && \
      info "    → volume brut Wazuh sauvegardé"
  fi
fi

# ────────────────────────────────────────────────────────────────────────────
# 3. Modèles IA (fichiers .joblib)
# ────────────────────────────────────────────────────────────────────────────
info "3/4 Modèles IA..."
MODELS_DIR="./models"
if [[ -d "$MODELS_DIR" ]]; then
  tar -czf "${BACKUP_DIR}/nexus_models_${TS}.tar.gz" "$MODELS_DIR" 2>>"$LOG"
  info "    → modèles sauvegardés dans nexus_models_${TS}.tar.gz"
else
  warn "    Répertoire models/ non trouvé"
fi

# ────────────────────────────────────────────────────────────────────────────
# 4. Configuration (.env, certificats, config Wazuh)
# ────────────────────────────────────────────────────────────────────────────
info "4/4 Configuration..."
CONFIG_ARCHIVE="${BACKUP_DIR}/nexus_config_${TS}.tar.gz"
tar -czf "$CONFIG_ARCHIVE" \
  .env 2>/dev/null || true \
  config/ 2>/dev/null || true \
  docker-compose.yml \
  2>>"$LOG" && info "    → configuration archivée"

# ────────────────────────────────────────────────────────────────────────────
# Nettoyage des vieilles sauvegardes
# ────────────────────────────────────────────────────────────────────────────
info "Nettoyage des sauvegardes > ${KEEP_DAYS} jours..."
find "$DEST" -maxdepth 1 -name "nexus_*" -type d -mtime "+${KEEP_DAYS}" -exec rm -rf {} + 2>/dev/null || true

# ────────────────────────────────────────────────────────────────────────────
# Rapport final
# ────────────────────────────────────────────────────────────────────────────
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1 || echo "?")
info ""
info "╔══════════════════════════════════════════════════╗"
info "║   Sauvegarde NEXUS SOC terminée                  ║"
info "╠══════════════════════════════════════════════════╣"
info "║ Destination : $BACKUP_DIR"
info "║ Taille      : $TOTAL_SIZE"
info "║ Log         : $LOG"
info "╚══════════════════════════════════════════════════╝"
