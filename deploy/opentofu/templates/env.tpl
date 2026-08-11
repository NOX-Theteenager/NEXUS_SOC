# =============================================================================
# NEXUS SOC — Variables d'environnement générées par OpenTofu
# Institution : ${institution}
# Domaine     : ${nexus_domain}
# ATTENTION   : Ce fichier contient des secrets. Ne pas committer. chmod 600.
# =============================================================================

# ── Base de données ──────────────────────────────────────────────────────────
POSTGRES_USER=nexus
POSTGRES_PASSWORD=${pg_pass}
POSTGRES_DB=nexus_soc
DB_DSN=postgresql://nexus:${pg_pass}@postgres:5432/nexus_soc

# ── Kafka ────────────────────────────────────────────────────────────────────
KAFKA_BOOTSTRAP=kafka:9092
TELEMETRY_TOPIC=nexus.telemetry
RAW_TOPIC=nexus.telemetry.raw
ALERTS_TOPIC=nexus.alerts

# ── Modèles IA ───────────────────────────────────────────────────────────────
MODEL1_PATH=/models/model1_isoforest.joblib
MODEL2_PATH=/models/model2_isoforest.joblib
RISK_THRESHOLD=${risk_threshold}

# ── Sécurité ─────────────────────────────────────────────────────────────────
JWT_SECRET=${jwt_secret}
PSEUDO_SECRET=${pseudo_secret}
WAZUH_ADMIN_PASSWORD=${wazuh_pass}

# ── Rate limiting ────────────────────────────────────────────────────────────
RATE_LIMIT_REQ=100
RATE_LIMIT_WIN=60
INGEST_LIMIT_REQ=${ingest_rate_limit}
INGEST_LIMIT_WIN=60

# ── Tokens JWT ───────────────────────────────────────────────────────────────
ACCESS_TOKEN_TTL_S=900
REFRESH_TOKEN_TTL_S=604800

# ── SIEM ─────────────────────────────────────────────────────────────────────
CORR_WINDOW_MIN=30
MASS_FILE_THRESHOLD=20
ACCOUNT_CREATE_THRESHOLD=5

# ── Wazuh ────────────────────────────────────────────────────────────────────
WAZUH_API_URL=https://wazuh.indexer:9200

# ── NEXUS SOC ────────────────────────────────────────────────────────────────
NEXUS_SERVER_URL=https://${nexus_domain}
NEXUS_AGENT_VERSION=${nexus_version}
INSTITUTION=${institution}

# ── Sauvegarde ───────────────────────────────────────────────────────────────
BACKUP_DEST=/opt/nexus-soc/backups
KEEP_DAYS=14
