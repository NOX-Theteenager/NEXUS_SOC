-- =============================================================================
--  NEXUS SOC — Explicabilité des alertes, présence et intégrité des agents
--
--  À exécuter APRÈS 03_schema_notifications.sql, avec le super-utilisateur :
--
--    docker exec -i nexus-postgres psql -U nexus -d nexus_soc -v ON_ERROR_STOP=1 \
--      < Lot0_Socle/04_schema_explicabilite.sql
--
--  Trois sujets, tous idempotents :
--    1. alerts.chaine + alerts.score_parts  — la chaîne d'attaque et la
--       décomposition du score étaient calculées par le pipeline puis perdues.
--    2. agents : intégrité HMAC vérifiable (schéma dérivé + époque de rotation).
--    3. agents : unicité (périmètre, hôte) — un même poste pouvait être enrôlé
--       plusieurs fois et apparaître en double dans le parc.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. Explicabilité des alertes
-- ---------------------------------------------------------------------------
-- chaine      : étapes reconstituées par le moteur de corrélation, ordonnées.
--               [{heure, tactique, technique_id, technique, detail}]
--               NULL pour une alerte issue du scoring d'un événement isolé :
--               il n'y a alors pas de chaîne, et il ne faut pas en inventer une.
-- score_parts : décomposition additive du risque, [{label, valeur}].
--               Renseignée quand le score EST une somme de contributions
--               (corrélation SIEM). NULL pour les modèles d'anomalie, dont le
--               score est une distance normalisée et non une somme.
ALTER TABLE alerts
    ADD COLUMN IF NOT EXISTS chaine      JSONB,
    ADD COLUMN IF NOT EXISTS score_parts JSONB;

COMMENT ON COLUMN alerts.chaine IS
    'Chaîne d''attaque reconstituée : [{heure, tactique, technique_id, technique, detail}]';
COMMENT ON COLUMN alerts.score_parts IS
    'Décomposition additive du risque : [{label, valeur}]. NULL si le score n''est pas une somme.';

-- Recherche des incidents portant une chaîne (console : file d'alertes enrichie)
CREATE INDEX IF NOT EXISTS idx_alerts_chaine ON alerts USING GIN (chaine)
    WHERE chaine IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 2. Intégrité HMAC des agents
-- ---------------------------------------------------------------------------
-- La base ne stockait que l'EMPREINTE de la clé HMAC (hmac_key_hash), ce qui
-- interdit de recalculer une signature : /ingest ne pouvait donc que constater
-- la présence du header X-Signature, pas le vérifier.
--
-- Schéma retenu : la clé n'est pas stockée du tout, elle est DÉRIVÉE à la
-- demande d'un secret maître serveur :
--
--     hmac_key = HMAC-SHA256(NEXUS_HMAC_MASTER, agent_id || ':' || hmac_epoch)
--
-- Le serveur la recalcule à chaque lot ; rien de réversible n'est au repos.
-- hmac_epoch s'incrémente à chaque rotation, ce qui invalide l'ancienne clé
-- sans changer l'identité de l'agent.
--
-- hmac_scheme :
--   'legacy'  → clé aléatoire d'origine, non recalculable : signature NON
--               vérifiable. L'agent doit être re-enrôlé ou sa clé tournée.
--   'derived' → clé dérivée, signature réellement vérifiée à chaque lot.
ALTER TABLE agents
    ADD COLUMN IF NOT EXISTS hmac_scheme TEXT NOT NULL DEFAULT 'legacy'
        CHECK (hmac_scheme IN ('legacy', 'derived')),
    ADD COLUMN IF NOT EXISTS hmac_epoch  INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN agents.hmac_scheme IS
    'legacy = clé non recalculable, signature non vérifiable ; derived = signature vérifiée';
COMMENT ON COLUMN agents.hmac_epoch IS
    'Incrémenté à chaque rotation de clé ; entre dans la dérivation';

-- Vue d'exploitation : quels agents restent sur l''ancien schéma ?
CREATE OR REPLACE VIEW v_agents_hmac_a_migrer AS
    SELECT a.id, a.tenant_id, t.nom AS perimetre, a.hostname, a.os,
           a.hmac_scheme, a.vu_le
      FROM agents a
      JOIN tenants t ON t.id = a.tenant_id
     WHERE a.hmac_scheme <> 'derived'
     ORDER BY a.vu_le DESC NULLS LAST;

COMMENT ON VIEW v_agents_hmac_a_migrer IS
    'Agents dont la signature des lots ne peut pas être vérifiée — à re-enrôler ou faire tourner';

-- ---------------------------------------------------------------------------
-- 3. Unicité (périmètre, hôte)
-- ---------------------------------------------------------------------------
-- Rien n'empêchait d'enrôler deux fois le même poste : le parc affichait alors
-- deux lignes pour une seule machine, avec deux battements distincts.
--
-- La contrainte n'est posée QUE si le parc est déjà propre. Sinon le script
-- s'arrête avec la liste des doublons : leur arbitrage (laquelle garder) est
-- une décision d'exploitation, pas quelque chose qu'une migration doit trancher
-- toute seule — chaque ligne porte un jeton et un historique d'alertes.
DO $$
DECLARE
    n_doublons INTEGER;
    detail     TEXT;
BEGIN
    SELECT count(*), string_agg(DISTINCT hostname, ', ')
      INTO n_doublons, detail
      FROM (SELECT tenant_id, hostname
              FROM agents
             GROUP BY tenant_id, hostname
            HAVING count(*) > 1) d;

    IF n_doublons > 0 THEN
        RAISE WARNING
          'Contrainte d''unicité NON posée : % hôte(s) en double (%). '
          'Arbitrez avec la requête de la section 4, puis relancez ce script.',
          n_doublons, detail;
    ELSE
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agents_tenant_hostname
            ON agents (tenant_id, hostname);
        RAISE NOTICE 'Unicité (périmètre, hôte) posée sur agents.';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 4. Aide à l'arbitrage des doublons (lecture seule)
-- ---------------------------------------------------------------------------
-- Pour chaque hôte en double : la ligne la plus récemment vue, le nombre
-- d'alertes rattachées, et la commande de suppression suggérée.
CREATE OR REPLACE VIEW v_agents_doublons AS
    WITH d AS (
        SELECT tenant_id, hostname
          FROM agents
         GROUP BY tenant_id, hostname
        HAVING count(*) > 1
    )
    SELECT a.id,
           t.nom AS perimetre,
           a.hostname,
           a.statut,
           a.vu_le,
           a.hmac_scheme,
           (a.vu_le IS NOT DISTINCT FROM
              max(a.vu_le) OVER (PARTITION BY a.tenant_id, a.hostname)) AS plus_recent,
           (SELECT count(*) FROM alerts al WHERE al.entite = a.hostname
                                             AND al.tenant_id = a.tenant_id) AS alertes_liees
      FROM agents a
      JOIN d          ON d.tenant_id = a.tenant_id AND d.hostname = a.hostname
      JOIN tenants t  ON t.id = a.tenant_id
     ORDER BY t.nom, a.hostname, a.vu_le DESC NULLS LAST;

COMMENT ON VIEW v_agents_doublons IS
    'Hôtes enrôlés plusieurs fois. plus_recent = TRUE sur la ligne à conserver a priori.';

GRANT SELECT ON v_agents_doublons        TO nexus_app;
GRANT SELECT ON v_agents_hmac_a_migrer   TO nexus_app;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nexus_analyst') THEN
        GRANT SELECT ON v_agents_doublons      TO nexus_analyst;
        GRANT SELECT ON v_agents_hmac_a_migrer TO nexus_analyst;
    END IF;
END $$;
