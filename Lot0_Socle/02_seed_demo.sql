-- =============================================================================
--  NEXUS SOC — Seed de démonstration (Lot 0)
--  À appliquer APRÈS : 01_schema_patched.sql, 01_schema_analyst.sql,
--                      01_schema_provisioning.sql, 01_schema_plg.sql
--
--  Idempotent : peut être ré-exécuté sans erreur ni doublon.
--
--  Comptes créés (mot de passe = "admin" pour tous, à changer en prod) :
--    admin@nexussoc.cm   → admin_plateforme  → Console (tous modules)
--    soc@nexussoc.cm     → analyste_soc      → Console (alertes + SOAR)
--    dsi@minfi.cm        → dsi_client        → Portail DSI (tenant MINFI)
--
--  Usage :
--    psql "postgresql://nexus:change_me@localhost:5432/nexus_soc" -f 02_seed_demo.sql
-- =============================================================================

-- pgcrypto requis pour crypt()/gen_salt() (déjà activé par 01_schema_patched.sql)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 1. Tenants de démonstration (base : id, nom, type, offre)
-- ---------------------------------------------------------------------------
INSERT INTO tenants (id, nom, type, offre) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Ministère des Finances',  'administration',    'contrat_public'),
  ('22222222-2222-2222-2222-222222222222', 'Microfinance Exemple SA', 'microfinance',      'business'),
  ('33333333-3333-3333-3333-333333333333', 'Cabinet Audit & Co',      'cabinet_comptable', 'starter')
ON CONFLICT (id) DO UPDATE
  SET nom = EXCLUDED.nom, type = EXCLUDED.type, offre = EXCLUDED.offre;

-- Champs PLG (plan / quotas) — appliqués uniquement si la colonne existe
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'tenants' AND column_name = 'plan') THEN
    UPDATE tenants SET plan = 'contrat_public', max_agents = 999, max_daily_events = 1000000
      WHERE id = '11111111-1111-1111-1111-111111111111';
    UPDATE tenants SET plan = 'business', max_agents = 50, max_daily_events = 200000
      WHERE id = '22222222-2222-2222-2222-222222222222';
    UPDATE tenants SET plan = 'trial', max_agents = 5, max_daily_events = 10000,
                       trial_ends_at = now() + interval '21 days'
      WHERE id = '33333333-3333-3333-3333-333333333333';
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. Comptes utilisateurs (RBAC) — mot de passe "admin"
-- ---------------------------------------------------------------------------
INSERT INTO users (tenant_id, email, mot_de_passe, role) VALUES
  (NULL,                                     'admin@nexussoc.cm', crypt('admin', gen_salt('bf')), 'admin_plateforme'),
  (NULL,                                     'soc@nexussoc.cm',   crypt('admin', gen_salt('bf')), 'analyste_soc'),
  ('11111111-1111-1111-1111-111111111111',   'dsi@minfi.cm',      crypt('admin', gen_salt('bf')), 'dsi_client')
ON CONFLICT (email) DO UPDATE
  SET mot_de_passe = EXCLUDED.mot_de_passe,
      role         = EXCLUDED.role,
      tenant_id    = EXCLUDED.tenant_id,
      actif        = TRUE;

-- ---------------------------------------------------------------------------
-- 3. Agents de démonstration (idempotent par id fixe)
-- ---------------------------------------------------------------------------
INSERT INTO agents (id, tenant_id, hostname, os, statut, vu_le) VALUES
  ('a0000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'SRV-BUDGET-01',    'linux',   'actif',      now() - interval '2 min'),
  ('a0000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'POSTE-COMPTA-07',  'windows', 'actif',      now() - interval '5 min'),
  ('a0000003-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222', 'SRV-CORE-01',      'linux',   'actif',      now() - interval '1 min'),
  ('a0000004-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'DESK-CAISSIER-01', 'windows', 'actif',      now() - interval '8 min'),
  ('a0000005-0000-0000-0000-000000000005', '33333333-3333-3333-3333-333333333333', 'WS-AUDITEUR-01',   'windows', 'hors_ligne', now() - interval '14 h')
ON CONFLICT (id) DO UPDATE
  SET statut = EXCLUDED.statut, vu_le = EXCLUDED.vu_le;

-- ---------------------------------------------------------------------------
-- 4. Alertes de démonstration (idempotent par id fixe)
-- ---------------------------------------------------------------------------
INSERT INTO alerts (id, tenant_id, source_modele, type, entite, risque, raisons, mitre, statut, cree_le) VALUES
  ('e0000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
   'Corrélation SIEM', 'Ransomware', 'POSTE-COMPTA-07', 100,
   '["5 tactiques MITRE en chaîne sur 22 min","32 fichiers chiffrés (.nexcrypt)","Activité hors heures (03h17)"]'::jsonb,
   'T1486 · Impact', 'ouverte', now() - interval '12 min'),

  ('e0000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
   'Modèle 2 (UEBA)', 'Fraude interne', 'agent_DGI_0421', 86,
   '["Montant total modifié : 12σ au-dessus du profil","Accès dossiers sensibles : +8σ","47 transactions en 90 min"]'::jsonb,
   'T1078 · Credential Access', 'en_cours', now() - interval '1 h'),

  ('e0000003-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222',
   'Modèle 1 (réseau)', 'Anomalie réseau / C2', 'SRV-CORE-01', 72,
   '["Flux sortant vers IP non répertoriée (3,2 Go / 4 h)","Beacon toutes les 300 s","Port 443 vers AS inconnu"]'::jsonb,
   'T1071 · C2', 'ouverte', now() - interval '3 h'),

  ('e0000004-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222',
   'Corrélation SIEM', 'Exécution suspecte', 'DESK-CAISSIER-01', 58,
   '["Script PowerShell encodé base64","Exécution depuis %TEMP%"]'::jsonb,
   'T1059 · Execution', 'ouverte', now() - interval '6 h')
ON CONFLICT (id) DO UPDATE
  SET risque = EXCLUDED.risque, statut = EXCLUDED.statut, cree_le = EXCLUDED.cree_le;

-- ---------------------------------------------------------------------------
-- 5. Actions SOAR en attente de validation humaine (idempotent par garde)
--    Alimente l'écran "Approbation SOAR" de la console analyste.
-- ---------------------------------------------------------------------------
INSERT INTO soar_audit (alert_id, tenant_id, action, impact, decision, statut, detail)
SELECT 'e0000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
       'isolate_host', 'fort', NULL, 'EN ATTENTE DE VALIDATION',
       'Isolation réseau complète de POSTE-COMPTA-07 (ransomware actif)'
WHERE NOT EXISTS (
  SELECT 1 FROM soar_audit
  WHERE alert_id = 'e0000001-0000-0000-0000-000000000001' AND action = 'isolate_host'
);

INSERT INTO soar_audit (alert_id, tenant_id, action, impact, decision, statut, detail)
SELECT 'e0000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
       'freeze_account', 'fort', NULL, 'EN ATTENTE DE VALIDATION',
       'Gel du compte AD/LDAP agent_DGI_0421 (faux mandatements suspectés)'
WHERE NOT EXISTS (
  SELECT 1 FROM soar_audit
  WHERE alert_id = 'e0000002-0000-0000-0000-000000000002' AND action = 'freeze_account'
);

INSERT INTO soar_audit (alert_id, tenant_id, action, impact, decision, statut, detail)
SELECT 'e0000003-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222',
       'block_ip', 'moyen', NULL, 'EN ATTENTE DE VALIDATION',
       'Blocage IP périmétrique du C2 contacté par SRV-CORE-01'
WHERE NOT EXISTS (
  SELECT 1 FROM soar_audit
  WHERE alert_id = 'e0000003-0000-0000-0000-000000000003' AND action = 'block_ip'
);

-- ---------------------------------------------------------------------------
-- 6. Récapitulatif
-- ---------------------------------------------------------------------------
DO $$
DECLARE n_users INT; n_alerts INT; n_pending INT;
BEGIN
  SELECT COUNT(*) INTO n_users  FROM users  WHERE email LIKE '%@nexussoc.cm' OR email = 'dsi@minfi.cm';
  SELECT COUNT(*) INTO n_alerts FROM alerts;
  SELECT COUNT(*) INTO n_pending FROM soar_audit WHERE statut = 'EN ATTENTE DE VALIDATION';
  RAISE NOTICE 'NEXUS SOC seed : % comptes démo, % alertes, % actions SOAR en attente.',
               n_users, n_alerts, n_pending;
END $$;
