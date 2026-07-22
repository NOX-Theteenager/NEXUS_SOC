-- =============================================================================
--  NEXUS SOC — Schéma d'initialisation (PostgreSQL 16 + TimescaleDB)
--  Démontre : cloisonnement des périmètres supervisés (colonne technique
--  tenant_id + Row-Level Security), RBAC, stockage des alertes + audit SOAR,
--  métriques en série temporelle.
--
--  « Périmètre supervisé » = une zone ou un système que le CENADI héberge et
--  supervise (ex. SIGIPES, ANTILOPE, réseau/LAN interne). La colonne technique
--  reste nommée tenant_id : c'est l'identifiant de cloisonnement porté par la RLS.
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- Rôle applicatif (soumis à la RLS — ne possède PAS BYPASSRLS).
-- C'est sous ce rôle que l'API positionne app.current_tenant pour isoler
-- chaque périmètre supervisé. Créé ici car les schémas analyst/provisioning
-- lui accordent des droits (GRANT ... TO nexus_app).
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_app') THEN
        CREATE ROLE nexus_app LOGIN PASSWORD 'change_me' NOSUPERUSER NOBYPASSRLS;
        RAISE NOTICE 'Rôle nexus_app créé.';
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Périmètres supervisés (systèmes / zones hébergés et supervisés par le CENADI)
-- La table conserve le nom « tenants » et la colonne « tenant_id » : ce sont les
-- identifiants techniques portés par la RLS. Sémantiquement, une ligne = un
-- périmètre (ex. SIGIPES, ANTILOPE, réseau/LAN interne), pas un client payant.
-- ---------------------------------------------------------------------------
CREATE TABLE tenants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nom         TEXT NOT NULL,
    -- Catégorie du périmètre supervisé
    type        TEXT NOT NULL CHECK (type IN ('application_metier','reseau','infrastructure','poste_utilisateur')),
    -- Niveau de criticité (pilote la priorisation des incidents)
    criticite   TEXT CHECK (criticite IN ('standard','sensible','critique')),
    cree_le     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Utilisateurs + RBAC (rôles)
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID REFERENCES tenants(id) ON DELETE CASCADE,  -- NULL = personnel plateforme
    email         TEXT UNIQUE NOT NULL,
    mot_de_passe  TEXT NOT NULL,                                   -- hash (jamais en clair)
    role          TEXT NOT NULL CHECK (role IN ('admin_plateforme','analyste_soc','dsi_client','lecteur')),
    actif         BOOLEAN NOT NULL DEFAULT TRUE,
    cree_le       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_tenant ON users(tenant_id);

-- ---------------------------------------------------------------------------
-- Agents (postes/serveurs surveillés)
-- ---------------------------------------------------------------------------
CREATE TABLE agents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    hostname    TEXT NOT NULL,
    os          TEXT CHECK (os IN ('windows','linux')),
    statut      TEXT NOT NULL DEFAULT 'actif' CHECK (statut IN ('actif','isole','hors_ligne')),
    vu_le       TIMESTAMPTZ
);
CREATE INDEX idx_agents_tenant ON agents(tenant_id);

-- ---------------------------------------------------------------------------
-- Alertes (sorties des modèles + corrélation)
-- ---------------------------------------------------------------------------
CREATE TABLE alerts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_modele TEXT,                       -- 'Modèle 1 (réseau)' | 'Modèle 2 (UEBA)'
    type          TEXT NOT NULL,              -- 'Fraude interne', 'Ransomware', ...
    entite        TEXT NOT NULL,              -- agent ou compte concerné
    risque        INT  NOT NULL CHECK (risque BETWEEN 0 AND 100),
    raisons       JSONB,                      -- explicabilité (liste de raisons)
    mitre         TEXT,
    statut        TEXT NOT NULL DEFAULT 'ouverte' CHECK (statut IN ('ouverte','en_cours','resolue','faux_positif')),
    cree_le       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_alerts_tenant_date ON alerts(tenant_id, cree_le DESC);

-- ---------------------------------------------------------------------------
-- Journal d'audit du SOAR (chaque action automatisée)
-- ---------------------------------------------------------------------------
CREATE TABLE soar_audit (
    id          BIGSERIAL PRIMARY KEY,
    alert_id    UUID REFERENCES alerts(id) ON DELETE CASCADE,
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    action      TEXT NOT NULL,
    impact      TEXT CHECK (impact IN ('info','faible','moyen','fort')),
    decision    TEXT,
    statut      TEXT,                         -- EXÉCUTÉE / EN ATTENTE DE VALIDATION / ANNULÉE / IGNORÉE
    acteur      TEXT,
    detail      TEXT,
    horodatage  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_alert ON soar_audit(alert_id);

-- ---------------------------------------------------------------------------
-- Métriques comportementales / système (série temporelle → hypertable)
-- ---------------------------------------------------------------------------
CREATE TABLE metrics (
    ts          TIMESTAMPTZ NOT NULL,
    tenant_id   UUID NOT NULL,
    agent_id    UUID,
    metrique    TEXT NOT NULL,                -- ex. 'cpu', 'score_risque', 'octets_sortants'
    valeur      DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('metrics', 'ts');
CREATE INDEX idx_metrics_tenant ON metrics(tenant_id, metrique, ts DESC);

-- =============================================================================
--  CLOISONNEMENT DES PÉRIMÈTRES — Row-Level Security (RLS)
--  Chaque requête ne voit que les données de son périmètre (variable de session
--  app.current_tenant positionnée par l'API après authentification).
-- =============================================================================
ALTER TABLE alerts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents     ENABLE ROW LEVEL SECURITY;
ALTER TABLE soar_audit ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_alerts ON alerts
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
CREATE POLICY tenant_isolation_agents ON agents
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
CREATE POLICY tenant_isolation_audit ON soar_audit
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

-- =============================================================================
--  Données de démonstration
-- =============================================================================
INSERT INTO tenants (id, nom, type, criticite) VALUES
    ('11111111-1111-1111-1111-111111111111', 'SIGIPES', 'application_metier', 'critique'),
    ('22222222-2222-2222-2222-222222222222', 'Réseau/LAN CENADI', 'reseau', 'sensible');

INSERT INTO users (tenant_id, email, mot_de_passe, role) VALUES
    (NULL, 'admin@nexussoc.cm', crypt('admin', gen_salt('bf')), 'admin_plateforme'),
    ('11111111-1111-1111-1111-111111111111', 'resp.sigipes@cenadi.cm', crypt('demo', gen_salt('bf')), 'dsi_client');

INSERT INTO agents (tenant_id, hostname, os, statut, vu_le) VALUES
    ('11111111-1111-1111-1111-111111111111', 'SRV-SIGIPES-01', 'linux', 'actif', now()),
    ('11111111-1111-1111-1111-111111111111', 'POSTE-RH-07', 'windows', 'actif', now());
