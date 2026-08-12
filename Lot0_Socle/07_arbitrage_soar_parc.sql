-- =============================================================================
--  NEXUS SOC — Arbitrage : propositions SOAR inexécutables et doublons du parc
--
--    docker exec -i nexus-postgres psql -U nexus -d nexus_soc -v ON_ERROR_STOP=1 \
--      < Lot0_Socle/07_arbitrage_soar_parc.sql
--
--  Idempotent. Applique trois décisions prises par l'opérateur le 12/08/2026.
--
--  1. REFUS des 14 propositions dont la cible ne correspond pas au connecteur
--     compétent (13 gels de compte visant un hôte, 1 blocage IP sans IP).
--     Elles sont refusées, pas réécrites : requalifier a posteriori une décision
--     de sécurité effacerait du journal la trace du défaut qui l'a produite.
--
--  2. AGRÉGATION des alertes répétées. Le collecteur produit une alerte toutes
--     les 15 min 30 s sur une condition persistante, alors que la fenêtre
--     anti-doublon vaut 15 min : elle rate de 30 secondes à chaque cycle. La
--     plus récente reste ouverte, les précédentes passent en `agregee`.
--
--     Ni « resolue » ni « faux_positif » ne conviennent : rien n'a été résolu et
--     la détection était juste. Le statut est donc ajouté plutôt que détourné.
--
--  3. SUPPRESSION de deux lignes d'agent en doublon. Aucune table d'alertes ni
--     de métriques ne référence `agents` : seul `enrollment_log` est en cascade,
--     pour une unique ligne. Vérifié avant exécution.
-- =============================================================================

BEGIN;

-- ── 1. Nouveau statut d'alerte : agrégée ────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'alerts_statut_check') THEN
        ALTER TABLE alerts DROP CONSTRAINT alerts_statut_check;
    END IF;
    ALTER TABLE alerts ADD CONSTRAINT alerts_statut_check
        CHECK (statut IN ('ouverte','en_cours','resolue','faux_positif','agregee'));
END $$;

COMMENT ON COLUMN alerts.statut IS
  'ouverte · en_cours · resolue · faux_positif · agregee. « agregee » : détection '
  'juste mais redondante avec une alerte plus récente portant la même condition. '
  'Ni résolue, ni fausse — rattachée.';

-- ── 2. Refus des propositions inexécutables ─────────────────────────────────
UPDATE soar_audit s
   SET statut   = 'IGNORÉE',
       decision = 'REFUSÉE',
       acteur   = COALESCE(s.acteur, 'arbitrage_operateur'),
       detail   = 'Refusée à l''arbitrage : ' || v.motif
                  || ' Action d''origine : ' || s.action || ' sur ' || s.cible
                  || ' (' || s.cible_type || ').'
  FROM v_soar_incoherent v
 WHERE v.id = s.id
   AND s.statut = 'EN ATTENTE DE VALIDATION';

-- ── 3. Agrégation des alertes redondantes ───────────────────────────────────
-- Groupe = (périmètre, type, entité). La plus récente de chaque groupe reste
-- ouverte : la condition est réelle et doit continuer d'être suivie.
--
-- Les entités sont listées explicitement, jamais déduites d'une heuristique :
-- chacune a été examinée et arbitrée. Les quatre groupes présentent la même
-- répétition, issue du même défaut de fenêtre corrigé au §5.
--
--   hote_SRV-APP-GOV-01  13 alertes  09–12 août
--   NoxTheMachine        15 alertes  22–29 juillet
--   hote_NoxTheMachine   14 alertes  23–27 juillet
--   agent_SIGIPES_SIM     3 alertes  09 août
WITH classees AS (
    SELECT id,
           row_number() OVER (PARTITION BY tenant_id, type, entite
                              ORDER BY cree_le DESC) AS rang
      FROM alerts
     WHERE statut = 'ouverte'
       AND entite IN ('hote_SRV-APP-GOV-01', 'NoxTheMachine',
                      'hote_NoxTheMachine',  'agent_SIGIPES_SIM')
)
UPDATE alerts a
   SET statut = 'agregee'
  FROM classees c
 WHERE c.id = a.id
   AND c.rang > 1;

-- ── 4. Suppression des doublons d'agent ─────────────────────────────────────
-- Garde la ligne qui porte l'activité réelle (jeton, métriques) ou, à défaut,
-- le journal d'enrôlement le plus fourni. Les cibles sont nommées
-- explicitement : aucune suppression déduite d'une heuristique.
DELETE FROM agents
 WHERE id IN ('a0000003-0000-0000-0000-000000000003',   -- SRV-ANTILOPE-01, ligne de démo
              'a0000001-0000-0000-0000-000000000001');  -- SRV-SIGIPES-01,  ligne de démo

-- ── Contrôle ────────────────────────────────────────────────────────────────
DO $$
DECLARE
    incoherent INTEGER;
    doublons   INTEGER;
    agregees   INTEGER;
    ouvertes   INTEGER;
BEGIN
    SELECT count(*) INTO incoherent FROM v_soar_incoherent
     WHERE statut = 'EN ATTENTE DE VALIDATION';
    SELECT count(*) INTO doublons FROM (
        SELECT 1 FROM agents GROUP BY tenant_id, hostname HAVING count(*) > 1) d;
    SELECT count(*) INTO agregees FROM alerts WHERE statut = 'agregee';
    SELECT count(*) INTO ouvertes FROM alerts WHERE statut = 'ouverte';

    RAISE NOTICE 'Propositions incohérentes encore en attente : %.', incoherent;
    RAISE NOTICE 'Hôtes encore en doublon : %.', doublons;
    RAISE NOTICE 'Alertes agrégées : % · alertes ouvertes : %.', agregees, ouvertes;

    IF incoherent > 0 THEN
        RAISE EXCEPTION 'Arbitrage incomplet : % proposition(s) toujours en attente.', incoherent;
    END IF;
    IF doublons > 0 THEN
        RAISE EXCEPTION 'Doublons subsistants : % hôte(s). Contrainte d''unicité impossible.', doublons;
    END IF;
END $$;

COMMIT;
