-- =============================================================================
--  NEXUS SOC — File de sortie vers les dossiers d'enquête (phase 3)
--
--    docker exec -i nexus-postgres psql -U nexus -d nexus_soc -v ON_ERROR_STOP=1 \
--      < Lot0_Socle/08_schema_dossiers.sql
--
--  Idempotent : relançable sans effet de bord.
--
--  POURQUOI UNE FILE, ET PAS UN APPEL DIRECT
--  -----------------------------------------
--  `/ingest` est le chemin le plus chaud de la plateforme : c'est par lui que
--  passe toute la télémétrie. Y placer un appel HTTP vers IRIS ferait dépendre
--  l'INGESTION de la disponibilité d'un outil d'enquête. IRIS redémarre, et le
--  SOC cesse de voir — exactement l'inverse de ce qu'on construit.
--
--  L'ingestion écrit donc une ligne ici, en transaction séparée, et rend la
--  main. Un ouvrier vide la file en arrière-plan. IRIS peut tomber dix minutes :
--  la file grossit, rien ne se perd, et tout part au redémarrage.
--
--  L'IDEMPOTENCE N'EST PAS UNE OPTION
--  ----------------------------------
--  Un ouvrier qui reprend après une panne ne sait pas si son dernier envoi est
--  arrivé. Sans clé d'idempotence, un rejeu crée un second dossier sur le même
--  incident, et l'analyste travaille en double sans le savoir.
--
--  `reference_source` porte l'UUID de l'alerte NEXUS. C'est lui qui part dans
--  `alert_source_ref` côté IRIS, qui refuse alors le doublon. L'unicité est
--  posée ici AUSSI, pour que la file elle-même ne puisse pas contenir deux fois
--  le même incident.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS dossier_sortie (
    id                BIGSERIAL PRIMARY KEY,

    -- Le fait observé. Une entrée de file n'existe jamais sans son alerte.
    alert_id          UUID NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    tenant_id         UUID NOT NULL,

    -- Clé d'idempotence, partagée avec `alert_source_ref` côté IRIS.
    reference_source  TEXT NOT NULL,

    -- La charge prête à poster, construite au moment de la décision. On fige
    -- ici ce que l'on a VU alors : rejouer un envoi trois heures plus tard ne
    -- doit pas produire un dossier reconstruit avec des données qui ont bougé.
    charge            JSONB NOT NULL,

    etat              TEXT NOT NULL DEFAULT 'en_attente'
                      CHECK (etat IN ('en_attente', 'envoye', 'abandonne')),

    tentatives        INTEGER NOT NULL DEFAULT 0,
    -- Report exponentiel : un IRIS en panne ne doit pas être martelé.
    prochaine_tentative TIMESTAMPTZ NOT NULL DEFAULT now(),
    derniere_erreur   TEXT,

    -- Identifiant rendu par IRIS. Sa présence est la seule preuve d'envoi :
    -- on ne marque pas « envoyé » sur un code HTTP, on le marque sur un
    -- identifiant que l'outil distant nous a donné.
    dossier_externe   TEXT,

    cree_le           TIMESTAMPTZ NOT NULL DEFAULT now(),
    envoye_le         TIMESTAMPTZ
);

-- Une alerte, un envoi. C'est cette contrainte qui rend le rejeu inoffensif.
CREATE UNIQUE INDEX IF NOT EXISTS dossier_sortie_reference_unique
    ON dossier_sortie (reference_source);

-- L'ouvrier ne lit que ce qui est dû : index partiel, il reste minuscule même
-- si la table accumule des années d'envois réussis.
CREATE INDEX IF NOT EXISTS dossier_sortie_a_traiter
    ON dossier_sortie (prochaine_tentative)
    WHERE etat = 'en_attente';

COMMENT ON TABLE dossier_sortie IS
  'File persistee des alertes a pousser vers DFIR-IRIS. L''ingestion y ecrit et
   rend la main : elle ne depend jamais de la disponibilite d''IRIS.';
COMMENT ON COLUMN dossier_sortie.reference_source IS
  'Cle d''idempotence, egale a alert_source_ref cote IRIS. Un rejeu ne cree pas
   de second dossier sur le meme incident.';
COMMENT ON COLUMN dossier_sortie.charge IS
  'Charge figee au moment de la decision. Rejouer un envoi ne doit pas
   reconstruire un dossier avec des donnees qui ont bouge depuis.';
COMMENT ON COLUMN dossier_sortie.dossier_externe IS
  'Identifiant rendu par IRIS. Sa presence, et non un code HTTP, atteste
   l''envoi.';

-- ── Correspondance des périmètres ──────────────────────────────────────────
-- IRIS numérote ses `customer` ; NEXUS identifie ses périmètres par UUID. La
-- correspondance est une DONNÉE, pas une constante dans le code : elle change
-- d'une instance IRIS à l'autre, et la coder en dur rendrait le connecteur
-- inutilisable ailleurs qu'ici.
CREATE TABLE IF NOT EXISTS perimetre_iris (
    tenant_id     UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    customer_id   INTEGER NOT NULL,
    customer_nom  TEXT,
    mis_a_jour_le TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE perimetre_iris IS
  'Correspondance perimetre NEXUS -> customer IRIS. Les identifiants IRIS sont
   propres a chaque instance : les figer dans le code interdirait tout autre
   deploiement.';

-- ── Ce que l'exploitant doit pouvoir voir en une requête ────────────────────
CREATE OR REPLACE VIEW v_dossier_sortie_sante AS
SELECT
    etat,
    count(*)                                        AS nombre,
    min(cree_le)                                    AS plus_ancienne,
    max(tentatives)                                 AS tentatives_max,
    count(*) FILTER (WHERE derniere_erreur IS NOT NULL) AS en_erreur
FROM dossier_sortie
GROUP BY etat;

COMMENT ON VIEW v_dossier_sortie_sante IS
  'Sante de la file. « plus_ancienne » en etat en_attente est la metrique qui
   compte : elle dit depuis combien de temps un incident n''est pas parti.';

COMMIT;
