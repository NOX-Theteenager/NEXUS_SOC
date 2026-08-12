-- =============================================================================
--  NEXUS SOC — Demandes internes de mise sous supervision
--  Alimente POST /contact/perimetre-request (formulaire contact.html).
--  À exécuter APRÈS 01_schema_analyst.sql avec le super-utilisateur.
--
--    psql -U postgres -d nexus_soc -f Lot7_Console_Fournisseur/02_schema_contact.sql
--
--  Ce n'est pas une table de prospection commerciale : elle trace les demandes
--  d'un service du CENADI vers l'équipe SOC du CENADI.
-- =============================================================================

-- Séquence dédiée à la référence lisible (DEM-2026-0147)
CREATE SEQUENCE IF NOT EXISTS perimetre_request_seq START 1;

CREATE TABLE IF NOT EXISTS perimetre_requests (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reference   TEXT NOT NULL UNIQUE
                DEFAULT 'DEM-' || to_char(now(), 'YYYY') || '-'
                     || lpad(nextval('perimetre_request_seq')::text, 4, '0'),
    systeme     TEXT NOT NULL,
    type        TEXT NOT NULL
                CHECK (type IN ('application_metier','reseau','infrastructure','poste_utilisateur')),
    criticite   TEXT NOT NULL
                CHECK (criticite IN ('standard','sensible','critique')),
    parc        TEXT,
    contexte    TEXT,
    responsable TEXT NOT NULL,
    statut      TEXT NOT NULL DEFAULT 'nouvelle'
                CHECK (statut IN ('nouvelle','en_qualification','acceptee','refusee')),
    tenant_id   UUID REFERENCES tenants(id) ON DELETE SET NULL,  -- rempli à la création du périmètre
    cree_le     TIMESTAMPTZ NOT NULL DEFAULT now(),
    traite_le   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_perimetre_requests_statut ON perimetre_requests(statut, cree_le DESC);

-- Le formulaire est ouvert à tout agent du CENADI : pas de RLS par périmètre,
-- la demande précède justement l'existence du périmètre.
GRANT SELECT, INSERT ON perimetre_requests TO nexus_app;
GRANT USAGE ON SEQUENCE perimetre_request_seq TO nexus_app;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_analyst') THEN
        GRANT SELECT, UPDATE ON perimetre_requests TO nexus_analyst;
    END IF;
END $$;
