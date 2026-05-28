-- =============================================================================
--  NEXUS SOC — Lot 7 : Schéma SQL — Cycle de vie des tokens d'enrôlement
--  À exécuter après 01_schema_patched.sql (Lot 0) et 01_schema_analyst.sql (Lot 7)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Colonnes de cycle de vie sur la table agents
-- ---------------------------------------------------------------------------
ALTER TABLE agents
  ADD COLUMN IF NOT EXISTS token_expires_at   TIMESTAMPTZ,          -- NULL = pas d'expiration
  ADD COLUMN IF NOT EXISTS token_used_at      TIMESTAMPTZ,          -- NULL = pas encore utilisé
  ADD COLUMN IF NOT EXISTS token_used_by_ip   TEXT,                 -- IP du premier enrôlement
  ADD COLUMN IF NOT EXISTS token_binding_host TEXT,                 -- hostname autorisé (NULL = libre)
  ADD COLUMN IF NOT EXISTS token_one_time     BOOLEAN DEFAULT TRUE, -- invalidé après 1er usage
  ADD COLUMN IF NOT EXISTS version_agent      TEXT;                 -- ex. "1.0.0"

-- Vue calculée du statut du token (utile pour les requêtes de la console)
CREATE OR REPLACE VIEW v_agent_token_status AS
SELECT
  a.id,
  a.tenant_id,
  a.hostname,
  a.os,
  a.statut,
  a.vu_le,
  a.token_expires_at,
  a.token_used_at,
  a.token_binding_host,
  a.token_one_time,
  CASE
    WHEN a.token_hash IS NULL                          THEN 'aucun'
    WHEN a.token_used_at IS NOT NULL                   THEN 'utilise'
    WHEN a.token_expires_at IS NOT NULL
         AND a.token_expires_at < now()               THEN 'expire'
    ELSE 'actif'
  END AS token_statut,
  -- Temps restant avant expiration (NULL si pas d'expiration ou déjà expiré)
  CASE
    WHEN a.token_expires_at IS NOT NULL AND a.token_expires_at > now()
    THEN EXTRACT(EPOCH FROM (a.token_expires_at - now()))::int
    ELSE NULL
  END AS token_ttl_seconds
FROM agents a;

GRANT SELECT ON v_agent_token_status TO nexus_app, nexus_analyst;

-- ---------------------------------------------------------------------------
-- 2. Table de journal des enrôlements (audit complet)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS enrollment_log (
  id          BIGSERIAL PRIMARY KEY,
  agent_id    UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  tenant_id   UUID NOT NULL,
  horodatage  TIMESTAMPTZ NOT NULL DEFAULT now(),
  ip_source   TEXT,
  os_detecte  TEXT,
  version     TEXT,
  succes      BOOLEAN NOT NULL,
  detail      TEXT
);
CREATE INDEX IF NOT EXISTS idx_enrollment_agent ON enrollment_log(agent_id);
CREATE INDEX IF NOT EXISTS idx_enrollment_tenant ON enrollment_log(tenant_id);

GRANT SELECT, INSERT ON enrollment_log TO nexus_app;
GRANT USAGE ON SEQUENCE enrollment_log_id_seq TO nexus_app;
GRANT SELECT ON enrollment_log TO nexus_analyst;

-- ---------------------------------------------------------------------------
-- 3. Table de provisioning en masse (suivi des imports CSV)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bulk_provisioning (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  initiateur  TEXT NOT NULL,
  nb_agents   INT  NOT NULL DEFAULT 0,
  statut      TEXT NOT NULL DEFAULT 'en_cours'
              CHECK (statut IN ('en_cours','termine','erreur')),
  detail      JSONB,
  cree_le     TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE ON bulk_provisioning TO nexus_app;
GRANT SELECT ON bulk_provisioning TO nexus_analyst;
