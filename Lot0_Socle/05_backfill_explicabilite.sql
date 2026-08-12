-- =============================================================================
--  NEXUS SOC — Reprise de l'explicabilité sur les alertes existantes
--
--    docker exec -i nexus-postgres psql -U nexus -d nexus_soc -v ON_ERROR_STOP=1 \
--      < Lot0_Socle/05_backfill_explicabilite.sql
--
--  À exécuter APRÈS 04_schema_explicabilite.sql. Idempotent : relançable sans
--  effet de bord, les raisons déjà structurées sont ignorées.
--
--  CE QUE CE SCRIPT FAIT
--  ---------------------
--  Les modèles calculaient l'écart σ de chaque variable, puis le formataient
--  dans une phrase : « volume de données exportées anormalement élevé (13.1σ) ».
--  La valeur numérique existe donc déjà, sérialisée dans le texte. On la
--  récupère pour que la console puisse tracer la décomposition sur les alertes
--  antérieures à la refonte.
--
--  Chaque raison devient : {label, sigma, texte}
--    texte : la chaîne d'ORIGINE, inchangée. Rien n'est perdu, et les
--            consommateurs qui attendent une phrase (rapport HTML,
--            notifications) continuent de fonctionner à l'identique.
--    sigma : le nombre accolé à σ, quand il y en a un. NULL sinon.
--    label : le libellé seul pour le format des modèles ; la phrase entière
--            pour les raisons rédigées à la main (jeu de démonstration).
--
--  CE QUE CE SCRIPT NE FAIT PAS
--  ----------------------------
--  Il ne reconstitue AUCUNE chaîne d'attaque et ne remplit pas score_parts.
--  Les événements bruts qui produiraient une chronologie n'ont jamais été
--  stockés, et le score des modèles d'anomalie est une distance normalisée, pas
--  une somme de contributions. Fabriquer des horodatages ou des pondérations
--  serait inventer la donnée sur l'écran qui porte précisément l'argument
--  d'explicabilité du projet. Ces colonnes restent NULL, et l'interface le dit.
-- =============================================================================

BEGIN;

-- Trace du volume traité, pour contrôle après exécution
CREATE TEMP TABLE _avant AS
SELECT count(*) AS alertes_a_traiter
  FROM alerts
 WHERE jsonb_typeof(raisons) = 'array'
   AND jsonb_array_length(raisons) > 0
   AND jsonb_typeof(raisons -> 0) = 'string';

UPDATE alerts a
   SET raisons = sub.nouvelles
  FROM (
    SELECT al.id,
           jsonb_agg(
             jsonb_strip_nulls(jsonb_build_object(
               -- Libellé : on retire le suffixe « anormalement élevé (Nσ) »
               -- quand il est présent ; sinon on garde la phrase telle quelle.
               'label',
               CASE WHEN r ~ ' anormalement (élevé|faible) \(.*σ\s*\)\s*$'
                    THEN regexp_replace(r, '\s*anormalement (élevé|faible)\s*\(.*σ\s*\)\s*$', '')
                    ELSE r
               END,
               -- Écart-type : premier nombre accolé à σ, virgule décimale
               -- française acceptée. NULL si la raison n'en porte pas.
               'sigma',
               CASE WHEN r ~ '(-?[0-9]+(?:[.,][0-9]+)?)\s*σ'
                    THEN replace(substring(r from '(-?[0-9]+(?:[.,][0-9]+)?)\s*σ'), ',', '.')::numeric
                    ELSE NULL
               END,
               -- Phrase d'origine, systématiquement conservée
               'texte', r
             ))
             ORDER BY ord
           ) AS nouvelles
      FROM alerts al,
           LATERAL jsonb_array_elements_text(al.raisons) WITH ORDINALITY AS t(r, ord)
     WHERE jsonb_typeof(al.raisons) = 'array'
       AND jsonb_array_length(al.raisons) > 0
       AND jsonb_typeof(al.raisons -> 0) = 'string'
     GROUP BY al.id
  ) AS sub
 WHERE a.id = sub.id;

-- Contrôle : rien ne doit rester en chaîne, et les σ doivent être récupérés
DO $$
DECLARE
    restant  INTEGER;
    avec_sig INTEGER;
    total    INTEGER;
BEGIN
    SELECT count(*) INTO restant
      FROM alerts
     WHERE jsonb_typeof(raisons) = 'array'
       AND jsonb_array_length(raisons) > 0
       AND jsonb_typeof(raisons -> 0) = 'string';

    SELECT count(*) FILTER (WHERE r ? 'sigma'), count(*)
      INTO avec_sig, total
      FROM alerts a, jsonb_array_elements(a.raisons) r
     WHERE jsonb_typeof(a.raisons) = 'array';

    RAISE NOTICE 'Raisons structurées : % au total, % portent un écart σ.', total, avec_sig;

    IF restant > 0 THEN
        RAISE EXCEPTION 'Reprise incomplète : % alerte(s) encore en chaînes.', restant;
    END IF;
END $$;

COMMIT;
