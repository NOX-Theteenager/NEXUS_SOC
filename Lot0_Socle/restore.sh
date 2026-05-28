#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC — Script de restauration
# Usage : sudo bash restore.sh --backup /opt/nexus-backups/nexus_20260528_090000
# =============================================================================
set -euo pipefail

BACKUP_DIR="${1:-}"
DB_CONTAINER="nexus-postgres"
DB_NAME="${POSTGRES_DB:-nexus_soc}"
DB_USER="${POSTGRES_USER:-nexus}"
WAZUH_API="https://localhost:9200"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail() { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup) BACKUP_DIR="$2"; shift 2 ;;
    *) fail "Argument inconnu : $1" ;;
  esac
done

[[ -z "$BACKUP_DIR" ]] && fail "Usage : bash restore.sh --backup <répertoire>"
[[ -d "$BACKUP_DIR" ]] || fail "Répertoire de backup introuvable : $BACKUP_DIR"

info "=== Restauration NEXUS SOC depuis $BACKUP_DIR ==="
read -p "⚠ ATTENTION : cette opération écrase les données existantes. Continuer ? [oui/NON] " CONFIRM
[[ "$CONFIRM" == "oui" ]] || fail "Annulé par l'utilisateur."

# 1. PostgreSQL
PG_DUMP=$(ls "${BACKUP_DIR}"/nexus_postgres_*.sql.gz 2>/dev/null | head -1 || \
          ls "${BACKUP_DIR}"/nexus_postgres_*.sql     2>/dev/null | head -1 || echo "")
if [[ -n "$PG_DUMP" ]]; then
  info "1/3 Restauration PostgreSQL depuis $(basename $PG_DUMP)..."
  if [[ "$PG_DUMP" == *.gz ]]; then
    gunzip -c "$PG_DUMP" | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"
  else
    docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < "$PG_DUMP"
  fi
  info "    → PostgreSQL restauré."
else
  warn "Dump PostgreSQL introuvable dans $BACKUP_DIR"
fi

# 2. Modèles IA
MODELS_TAR=$(ls "${BACKUP_DIR}"/nexus_models_*.tar.gz 2>/dev/null | head -1 || echo "")
if [[ -n "$MODELS_TAR" ]]; then
  info "2/3 Restauration des modèles IA..."
  tar -xzf "$MODELS_TAR" -C . && info "    → modèles restaurés."
else
  warn "Archive modèles introuvable."
fi

# 3. Wazuh Indexer
SNAP_DIR="${BACKUP_DIR}/wazuh_snapshot"
if [[ -d "$SNAP_DIR" ]]; then
  info "3/3 Restauration Wazuh Indexer depuis snapshot..."
  SNAP_NAME=$(ls "$SNAP_DIR"/index/ 2>/dev/null | grep "snap-" | head -1 | sed 's/snap-/nexus_snap_/' || echo "")
  if [[ -n "$SNAP_NAME" ]]; then
    curl -k -s -u admin:admin -X POST \
      "${WAZUH_API}/_snapshot/nexus_backup/${SNAP_NAME}/_restore?wait_for_completion=true" \
      -H 'Content-Type: application/json' \
      -d '{"ignore_unavailable":true}' && info "    → Wazuh restauré."
  fi
else
  warn "Snapshot Wazuh introuvable."
fi

info "Restauration terminée. Redémarrer la pile : docker compose restart"
