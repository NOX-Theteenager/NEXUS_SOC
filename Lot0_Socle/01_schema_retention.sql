-- =============================================================================
-- NEXUS SOC — Politique de rétention des données (TimescaleDB)
-- À appliquer après 01_schema_patched.sql
-- Principe : données chaudes en ligne, données froides compressées, suppression auto
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Compression automatique des métriques (> 7 jours)
-- ---------------------------------------------------------------------------
SELECT add_compression_policy('metrics', INTERVAL '7 days')
  WHERE NOT EXISTS (
    SELECT 1 FROM timescaledb_information.jobs
    WHERE application_name LIKE '%Compression%' AND hypertable_name = 'metrics'
  );

ALTER TABLE metrics SET (
  timescaledb.compress,
  timescaledb.compress_orderby      = 'ts DESC',
  timescaledb.compress_segmentby    = 'tenant_id, metrique'
);

-- ---------------------------------------------------------------------------
-- 2. Suppression automatique (rétention configurable par offre)
-- ---------------------------------------------------------------------------
-- Métriques brutes : 90 jours (compression active entre J7 et J90)
SELECT add_retention_policy('metrics', INTERVAL '90 days')
  WHERE NOT EXISTS (
    SELECT 1 FROM timescaledb_information.jobs
    WHERE application_name LIKE '%Retention%' AND hypertable_name = 'metrics'
  );

-- ---------------------------------------------------------------------------
-- 3. Archivage des alertes résolues (> 1 an → table d'archive froide)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts_archive (LIKE alerts INCLUDING ALL);
ALTER TABLE alerts_archive ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_alerts_archive ON alerts_archive
  USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
GRANT SELECT, INSERT ON alerts_archive TO nexus_app;
GRANT SELECT ON alerts_archive TO nexus_analyst;

-- Procédure d'archivage (à appeler par pg_cron ou depuis l'application)
CREATE OR REPLACE PROCEDURE archive_old_alerts()
LANGUAGE plpgsql AS $$
BEGIN
  -- Déplacer les alertes résolues / faux positifs > 1 an
  INSERT INTO alerts_archive
    SELECT * FROM alerts
    WHERE statut IN ('resolue', 'faux_positif')
      AND cree_le < now() - INTERVAL '1 year'
    ON CONFLICT DO NOTHING;

  DELETE FROM alerts
  WHERE statut IN ('resolue', 'faux_positif')
    AND cree_le < now() - INTERVAL '1 year';

  RAISE NOTICE 'Archivage terminé : % alertes archivées', ROW_COUNT;
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. Suppression des tokens expirés dans la table agents
-- ---------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE cleanup_expired_tokens()
LANGUAGE plpgsql AS $$
BEGIN
  -- Invalider les tokens expirés mais non utilisés (garder la trace de l'agent)
  UPDATE agents
  SET token_hash = NULL, hmac_key_hash = NULL
  WHERE token_expires_at IS NOT NULL
    AND token_expires_at < now()
    AND token_used_at IS NULL;   -- jamais utilisé ET expiré → nettoyer

  -- Supprimer les agents hors-ligne depuis > 180 jours sans enrôlement réussi
  DELETE FROM agents
  WHERE statut = 'hors_ligne'
    AND token_used_at IS NULL
    AND token_expires_at < now() - INTERVAL '180 days';
END;
$$;

-- ---------------------------------------------------------------------------
-- 5. Table de journal de rétention (audit des suppressions)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS retention_log (
  id         BIGSERIAL PRIMARY KEY,
  operation  TEXT NOT NULL,
  nb_rows    INT  NOT NULL DEFAULT 0,
  execute_le TIMESTAMPTZ NOT NULL DEFAULT now(),
  detail     TEXT
);
GRANT INSERT ON retention_log TO nexus_app;
GRANT SELECT ON retention_log TO nexus_analyst;
GRANT USAGE ON SEQUENCE retention_log_id_seq TO nexus_app;

-- ---------------------------------------------------------------------------
-- 6. Durées de rétention par offre (table de configuration)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS retention_policy (
  offre               TEXT PRIMARY KEY,
  alerts_hot_days     INT NOT NULL DEFAULT 365,   -- alertes chaudes (en ligne)
  alerts_cold_years   INT NOT NULL DEFAULT 5,     -- alertes froides (archive)
  metrics_days        INT NOT NULL DEFAULT 90,
  audit_years         INT NOT NULL DEFAULT 7      -- journal SOAR (légal)
);
INSERT INTO retention_policy (offre, alerts_hot_days, metrics_days) VALUES
  ('starter',        180, 30),
  ('business',       365, 90),
  ('enterprise',     730, 365),
  ('contrat_public', 730, 365)
ON CONFLICT DO NOTHING;
