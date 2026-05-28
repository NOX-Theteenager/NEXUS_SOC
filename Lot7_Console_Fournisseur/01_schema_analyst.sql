-- =============================================================================
--  NEXUS SOC — Lot 7 : Schéma SQL complémentaire
--  Rôle nexus_analyst (cross-tenant) + colonnes de provisioning agent
--  À exécuter APRÈS 01_schema_patched.sql (Lot 0) avec le super-utilisateur.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Colonne statut sur la table tenants (suspension d'un tenant)
-- ---------------------------------------------------------------------------
ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS statut TEXT NOT NULL DEFAULT 'actif'
        CHECK (statut IN ('actif', 'suspendu'));

-- ---------------------------------------------------------------------------
-- 2. Colonnes de provisioning agent (token hash + clé HMAC hashée)
--    L'agent Go reçoit les valeurs en clair au moment de l'enrôlement ;
--    la plateforme ne conserve que les empreintes SHA-256.
-- ---------------------------------------------------------------------------
ALTER TABLE agents
    ADD COLUMN IF NOT EXISTS token_hash     TEXT,
    ADD COLUMN IF NOT EXISTS hmac_key_hash  TEXT;

-- ---------------------------------------------------------------------------
-- 3. Rôle PostgreSQL nexus_analyst — lecture cross-tenant (BYPASSRLS)
--
--    Approche retenue : BYPASSRLS sur un rôle distinct, séparé de nexus_app.
--    nexus_app    → rôle applicatif client, soumis à la RLS (tenant isolé)
--    nexus_analyst → rôle analyste SOC, contourne la RLS (tous tenants)
--
--    ⚠ nexus_analyst a uniquement les droits SELECT sur les tables sensibles +
--      UPDATE limité sur soar_audit (approbation). Jamais super-utilisateur.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_analyst') THEN
        CREATE ROLE nexus_analyst LOGIN
            PASSWORD 'CHANGE_ME_IN_PRODUCTION'
            BYPASSRLS
            NOINHERIT
            NOSUPERUSER
            NOCREATEROLE
            NOCREATEDB;
        RAISE NOTICE 'Rôle nexus_analyst créé.';
    ELSE
        ALTER ROLE nexus_analyst BYPASSRLS;
        RAISE NOTICE 'Rôle nexus_analyst mis à jour (BYPASSRLS confirmé).';
    END IF;
END
$$;

-- Droits en lecture sur toutes les tables pertinentes
GRANT CONNECT ON DATABASE nexus TO nexus_analyst;
GRANT USAGE ON SCHEMA public TO nexus_analyst;
GRANT SELECT ON tenants, users, agents, alerts, soar_audit, metrics TO nexus_analyst;

-- L'analyste peut approuver des actions SOAR (UPDATE statut + decision + acteur)
GRANT UPDATE (statut, decision, acteur) ON soar_audit TO nexus_analyst;

-- Séquences nécessaires si l'analyste crée des entrées d'audit (journalisation)
GRANT USAGE ON SEQUENCE soar_audit_id_seq TO nexus_analyst;

-- ---------------------------------------------------------------------------
-- 4. Rôle nexus_app — rappel de la politique RLS (ne rien changer)
--    (Documenté ici pour référence ; la politique est dans Lot 0.)
--
--    CREATE POLICY tenant_isolation_alerts ON alerts
--        USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
--
--    nexus_app est soumis à cette politique car il ne possède pas BYPASSRLS.
--    nexus_analyst la contourne légalement via l'attribut BYPASSRLS.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 5. Données de démonstration Lot 7 (utilisateur analyste SOC)
-- ---------------------------------------------------------------------------
INSERT INTO users (tenant_id, email, mot_de_passe, role)
    SELECT NULL, 'soc@nexussoc.cm', crypt('analyst_demo', gen_salt('bf')), 'analyste_soc'
    WHERE NOT EXISTS (SELECT 1 FROM users WHERE email = 'soc@nexussoc.cm');
