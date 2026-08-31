-- =============================================================================
--  NEXUS SOC — Canaux de discussion d'incident (phase 4)
--
--    docker exec -i nexus-postgres psql -U nexus -d nexus_soc -v ON_ERROR_STOP=1 \
--      < Lot0_Socle/09_schema_discussion.sql
--
--  Idempotent : relançable sans effet de bord.
--
--  POURQUOI CETTE TABLE EXISTE
--  ---------------------------
--  Pour qu'un incident n'ait JAMAIS deux canaux. La veille tourne en boucle :
--  sans mémoire de ce qu'elle a déjà ouvert, chaque tour rouvrirait un canal
--  sur le même incident, et la conversation se disperserait entre plusieurs
--  endroits — exactement le contraire de ce qu'on cherche.
--
--  On garde aussi la trace des ÉCHECS. Un canal qu'on n'a pas su ouvrir doit
--  se voir : sinon la cellule de crise attend une notification qui ne viendra
--  jamais, en croyant que le silence veut dire « rien à signaler ».
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS incident_canal (
    id               BIGSERIAL PRIMARY KEY,

    -- Même clé que la file vers IRIS : l'UUID de l'alerte NEXUS. Un incident
    -- porte le même identifiant d'un bout à l'autre de la chaîne.
    reference_source TEXT NOT NULL,
    alert_id         UUID REFERENCES alerts(id) ON DELETE SET NULL,
    tenant_id        UUID,

    -- Identifiants côté outils, relevés et non devinés.
    alerte_iris      TEXT,
    canal_id         TEXT,
    canal_nom        TEXT,
    canal_lien       TEXT,

    etat             TEXT NOT NULL DEFAULT 'a_ouvrir'
                     CHECK (etat IN ('a_ouvrir', 'ouvert', 'echec')),
    derniere_erreur  TEXT,
    tentatives       INTEGER NOT NULL DEFAULT 0,

    cree_le          TIMESTAMPTZ NOT NULL DEFAULT now(),
    ouvert_le        TIMESTAMPTZ
);

-- Un incident, un canal. C'est cette contrainte qui rend la veille inoffensive
-- quelle que soit sa fréquence.
CREATE UNIQUE INDEX IF NOT EXISTS incident_canal_reference_unique
    ON incident_canal (reference_source);

CREATE INDEX IF NOT EXISTS incident_canal_a_ouvrir
    ON incident_canal (cree_le) WHERE etat = 'a_ouvrir';

COMMENT ON TABLE incident_canal IS
  'Correspondance incident -> canal de discussion. Garantit qu''un incident n''a
   jamais deux canaux, quelle que soit la frequence de la veille.';
COMMENT ON COLUMN incident_canal.etat IS
  'a_ouvrir : escalade vue, canal pas encore cree. ouvert : canal en place.
   echec : n''a pas pu etre ouvert — doit se voir, car la cellule attend sinon
   une notification qui ne viendra pas.';

COMMIT;
