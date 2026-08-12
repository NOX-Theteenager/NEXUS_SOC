-- =============================================================================
--  NEXUS SOC — Cible d'action SOAR et honnêteté du statut d'exécution
--
--    docker exec -i nexus-postgres psql -U nexus -d nexus_soc -v ON_ERROR_STOP=1 \
--      < Lot0_Socle/06_schema_soar_cible.sql
--
--  Idempotent : relançable sans effet de bord.
--
--  CE QUE CE SCRIPT CORRIGE
--  ------------------------
--  1. Une action de réponse n'avait pas de CIBLE. « Bloquer l'IP » sans savoir
--     laquelle, « geler le compte » sans savoir lequel : même raccordé à un vrai
--     pare-feu ou à un vrai annuaire, le connecteur serait resté aveugle.
--
--  2. Le statut passait à « EXÉCUTÉE » alors que RIEN n'était exécuté — l'API se
--     contentait d'un UPDATE. La plateforme affirmait un acte qu'elle n'avait pas
--     commis. On sépare désormais la DÉCISION (approuvée / refusée), qui est
--     réelle et tracée, de l'EXÉCUTION, qui ne l'est pas encore.
--
--  CE QUE CE SCRIPT NE FAIT PAS
--  ----------------------------
--  Il ne réécrit AUCUNE action déjà proposée. Douze propositions en attente
--  portent une action incohérente avec leur cible (gel de compte sur un hôte) —
--  elles sont enrichies et signalées par la vue `v_soar_incoherent`, pas
--  modifiées. Requalifier une décision de sécurité en attente d'arbitrage
--  relève de l'analyste, pas d'une migration.
-- =============================================================================

BEGIN;

-- ── 1. Cible de l'action ────────────────────────────────────────────────────
ALTER TABLE soar_audit ADD COLUMN IF NOT EXISTS cible      TEXT;
ALTER TABLE soar_audit ADD COLUMN IF NOT EXISTS cible_type TEXT;

COMMENT ON COLUMN soar_audit.cible IS
  'Identifiant sur lequel porte l''action : IP à bloquer, compte à geler, '
  'hôte à mettre en quarantaine. NULL = action sans cible exploitable.';
COMMENT ON COLUMN soar_audit.cible_type IS
  'Nature de la cible : ip | compte | hote | inconnu. Détermine quel '
  'connecteur est compétent.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'soar_audit_cible_type_check') THEN
        ALTER TABLE soar_audit ADD CONSTRAINT soar_audit_cible_type_check
            CHECK (cible_type IS NULL OR cible_type IN ('ip','compte','hote','inconnu'));
    END IF;
END $$;

-- ── 2. Exécution réelle, distincte de la décision ───────────────────────────
ALTER TABLE soar_audit ADD COLUMN IF NOT EXISTS execution     TEXT
    NOT NULL DEFAULT 'non_executee';
ALTER TABLE soar_audit ADD COLUMN IF NOT EXISTS execute_le    TIMESTAMPTZ;
ALTER TABLE soar_audit ADD COLUMN IF NOT EXISTS execute_par   TEXT;
ALTER TABLE soar_audit ADD COLUMN IF NOT EXISTS execution_note TEXT;

COMMENT ON COLUMN soar_audit.execution IS
  'non_executee : approuvée mais aucun connecteur ne l''a appliquée. '
  'manuelle : un opérateur déclare l''avoir exécutée à la main. '
  'automatique : un connecteur raccordé l''a réellement appliquée. '
  'annulee : action réversible qui a été levée.';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'soar_audit_execution_check') THEN
        ALTER TABLE soar_audit ADD CONSTRAINT soar_audit_execution_check
            CHECK (execution IN ('non_executee','manuelle','automatique','annulee'));
    END IF;
END $$;

-- ── 3. Reprise de l'existant : déduire la cible depuis l'entité de l'alerte ──
-- Enrichissement pur. Aucune action, aucun statut n'est touché.
UPDATE soar_audit s
   SET cible = CASE
                 WHEN a.entite LIKE 'hote\_%'  THEN substring(a.entite from 6)
                 ELSE a.entite
               END,
       cible_type = CASE
                 WHEN a.entite LIKE 'agent\_%' THEN 'compte'
                 WHEN a.entite IS NULL OR a.entite = '' OR a.entite = '?' THEN 'inconnu'
                 ELSE 'hote'
               END
  FROM alerts a
 WHERE a.id = s.alert_id
   AND s.cible IS NULL;

-- Les lignes historiques marquées « EXÉCUTÉE » ne l'ont jamais été par un
-- connecteur : aucun n'existait. On le dit, au lieu de le laisser croire.
UPDATE soar_audit
   SET execution      = 'non_executee',
       execution_note = 'Statut historique : approuvée avant la mise en place du '
                        'suivi d''exécution. Aucun connecteur n''était raccordé.'
 WHERE statut = 'EXÉCUTÉE'
   AND execution = 'non_executee'
   AND execution_note IS NULL;

-- ── 4. Vue d'arbitrage : propositions dont l'action ne colle pas à la cible ──
CREATE OR REPLACE VIEW v_soar_incoherent AS
SELECT s.id, s.action, s.cible, s.cible_type, s.statut, s.horodatage,
       a.type AS type_alerte, a.entite, t.nom AS perimetre,
       CASE
         WHEN s.action = 'freeze_account' AND s.cible_type <> 'compte'
           THEN 'Gel de compte demandé sur ' || s.cible_type || ' : aucun compte de ce nom.'
         WHEN s.action = 'block_ip' AND s.cible_type <> 'ip'
           THEN 'Blocage IP sans destination observée : rien à bloquer.'
         ELSE NULL
       END AS motif
  FROM soar_audit s
  JOIN tenants t ON t.id = s.tenant_id
  LEFT JOIN alerts a ON a.id = s.alert_id
 WHERE (s.action = 'freeze_account' AND s.cible_type IS DISTINCT FROM 'compte')
    OR (s.action = 'block_ip'       AND s.cible_type IS DISTINCT FROM 'ip');

COMMENT ON VIEW v_soar_incoherent IS
  'Actions dont la cible ne correspond pas au connecteur compétent. À arbitrer '
  'par un analyste : requalifier l''action ou refuser la proposition.';

CREATE INDEX IF NOT EXISTS idx_soar_cible ON soar_audit (cible_type, cible)
    WHERE cible IS NOT NULL;

-- ── Contrôle ────────────────────────────────────────────────────────────────
DO $$
DECLARE
    sans_cible INTEGER;
    incoherent INTEGER;
BEGIN
    SELECT count(*) INTO sans_cible
      FROM soar_audit s JOIN alerts a ON a.id = s.alert_id WHERE s.cible IS NULL;
    SELECT count(*) INTO incoherent FROM v_soar_incoherent;

    RAISE NOTICE 'Actions sans cible résolue : %.', sans_cible;
    RAISE NOTICE 'Actions incohérentes à arbitrer : % (voir v_soar_incoherent).', incoherent;
END $$;

COMMIT;
