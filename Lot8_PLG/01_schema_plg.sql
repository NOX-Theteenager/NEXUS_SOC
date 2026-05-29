-- =============================================================================
-- NEXUS SOC — Lot 8 : Schéma PLG (Product-Led Growth)
-- À appliquer après : 01_schema_patched.sql, 01_schema_provisioning.sql
-- =============================================================================

-- Enrichissement de la table tenants avec les champs PLG
ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS plan              VARCHAR(20)  DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS trial_ends_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS suspended_at      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS max_agents        INTEGER      DEFAULT 5,
    ADD COLUMN IF NOT EXISTS max_daily_events  INTEGER      DEFAULT 10000;

-- Vérifier que la colonne 'type' existe déjà (ajoutée si manquante)
ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS type VARCHAR(20) DEFAULT 'client';

-- =============================================================================
-- Pipeline d'inscription : de l'email à la création du tenant
-- =============================================================================
CREATE TABLE IF NOT EXISTS plg_registrations (
    id                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email                 VARCHAR(255) NOT NULL UNIQUE,
    organization_name     VARCHAR(255),
    sector                VARCHAR(50),  -- microfinance | assurance | cabinet | autre
    email_verified        BOOLEAN      DEFAULT FALSE,
    verification_token    VARCHAR(64)  UNIQUE,
    verification_sent_at  TIMESTAMPTZ,
    preauth_completed     BOOLEAN      DEFAULT FALSE,
    preauth_reference     VARCHAR(128),
    preauth_completed_at  TIMESTAMPTZ,
    tenant_id             UUID         REFERENCES tenants(id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ  DEFAULT NOW(),
    ip_address            INET,
    user_agent            TEXT
);

-- =============================================================================
-- Suivi des quotas journaliers pour les tenants en période d'essai
-- =============================================================================
CREATE TABLE IF NOT EXISTS trial_quotas (
    tenant_id    UUID   NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date         DATE   NOT NULL DEFAULT CURRENT_DATE,
    agent_count  INTEGER DEFAULT 0,    -- nb d'agents distincts ayant envoyé de la télémétrie
    event_count  BIGINT  DEFAULT 0,    -- total événements ingérés ce jour
    PRIMARY KEY (tenant_id, date)
);

-- =============================================================================
-- Abonnements payants
-- =============================================================================
CREATE TABLE IF NOT EXISTS subscriptions (
    id                UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID         NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    plan              VARCHAR(20)  NOT NULL,    -- starter | business | enterprise
    status            VARCHAR(20)  DEFAULT 'active', -- active | suspended | cancelled
    started_at        TIMESTAMPTZ  DEFAULT NOW(),
    ends_at           TIMESTAMPTZ,
    amount_fcfa       INTEGER      NOT NULL,
    payment_reference VARCHAR(128),
    created_at        TIMESTAMPTZ  DEFAULT NOW()
);

-- =============================================================================
-- Index
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_tenants_plan
    ON tenants(plan);

CREATE INDEX IF NOT EXISTS idx_tenants_trial_ends
    ON tenants(trial_ends_at)
    WHERE plan = 'trial';

CREATE INDEX IF NOT EXISTS idx_tenants_suspended
    ON tenants(suspended_at)
    WHERE suspended_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_trial_quotas_tenant_date
    ON trial_quotas(tenant_id, date);

CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant
    ON subscriptions(tenant_id);

CREATE INDEX IF NOT EXISTS idx_plg_reg_token
    ON plg_registrations(verification_token)
    WHERE email_verified = FALSE AND verification_token IS NOT NULL;

-- =============================================================================
-- Vue : tenants en essai proches de l'expiration (pour alertes admin)
-- =============================================================================
CREATE OR REPLACE VIEW v_trial_expiry AS
SELECT
    t.id                                                        AS tenant_id,
    t.name                                                      AS tenant_name,
    r.email,
    t.trial_ends_at,
    EXTRACT(EPOCH FROM (t.trial_ends_at - NOW())) / 86400       AS days_remaining,
    COALESCE(q.agent_count, 0)                                  AS agents_active_today,
    t.max_agents,
    COALESCE(q.event_count, 0)                                  AS events_today,
    t.max_daily_events
FROM tenants t
JOIN plg_registrations r ON r.tenant_id = t.id
LEFT JOIN trial_quotas q  ON q.tenant_id = t.id AND q.date = CURRENT_DATE
WHERE t.plan = 'trial'
ORDER BY t.trial_ends_at ASC;

-- =============================================================================
-- Vue : abonnements actifs avec facturation
-- =============================================================================
CREATE OR REPLACE VIEW v_active_subscriptions AS
SELECT
    t.id          AS tenant_id,
    t.name        AS tenant_name,
    s.plan,
    s.status,
    s.amount_fcfa,
    s.started_at,
    s.ends_at,
    s.payment_reference
FROM subscriptions s
JOIN tenants t ON t.id = s.tenant_id
WHERE s.status = 'active'
ORDER BY s.started_at DESC;

-- =============================================================================
-- Fonction : suspension automatique des essais expirés
-- Appelée par un cron ou à chaque requête d'ingestion
-- =============================================================================
CREATE OR REPLACE FUNCTION suspend_expired_trials()
RETURNS INTEGER
LANGUAGE plpgsql AS $$
DECLARE
    n INTEGER;
BEGIN
    UPDATE tenants
    SET
        plan         = 'expired',
        suspended_at = NOW()
    WHERE
        plan         = 'trial'
        AND trial_ends_at < NOW()
        AND suspended_at IS NULL;

    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$;

-- =============================================================================
-- Données de référence : configuration des plans
-- =============================================================================
CREATE TABLE IF NOT EXISTS plan_config (
    plan              VARCHAR(20) PRIMARY KEY,
    label_fr          VARCHAR(50),
    amount_fcfa       INTEGER,
    max_agents        INTEGER,
    max_daily_events  INTEGER
);

INSERT INTO plan_config VALUES
    ('trial',      'Essai gratuit',  0,       5,   10000),
    ('starter',    'Starter',        25000,   10,  50000),
    ('business',   'Business',       75000,   50,  200000),
    ('enterprise', 'Enterprise',     200000,  200, 1000000)
ON CONFLICT (plan) DO UPDATE SET
    amount_fcfa      = EXCLUDED.amount_fcfa,
    max_agents       = EXCLUDED.max_agents,
    max_daily_events = EXCLUDED.max_daily_events;
