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
--    dsi@afriland.cm     → dsi_client        → Portail (tenant Afriland - VLAN 10)
--    dsi@uba.cm          → dsi_client        → Portail (tenant UBA - VLAN 20)
--
--  Nota : MINFI n'est PAS dans ce seed — MINFI relève du canal souverain
--  (déploiement self-hosted) et n'est jamais un tenant SaaS.
--
--  Usage :
--    psql "postgresql://nexus:change_me@localhost:5432/nexus_soc" -f 02_seed_demo.sql
-- =============================================================================

-- pgcrypto requis pour crypt()/gen_salt() (déjà activé par 01_schema_patched.sql)
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 1. Tenants de démonstration (base : id, nom, type, offre)
-- ---------------------------------------------------------------------------
-- Tenants du SOC SaaS de NEXUS (clients hébergés chez le fournisseur)
--   • Afriland : client de test (VLAN 10 dans le lab)
--   • UBA      : client second (VLAN 20) pour prouver l'isolation cross-tenant
--   • Cabinet Audit : trial (démo PLG passage à un abonnement payant)
INSERT INTO tenants (id, nom, type, offre) VALUES
  ('11111111-1111-1111-1111-111111111111', 'Afriland First Bank Microfinance', 'microfinance',      'business'),
  ('22222222-2222-2222-2222-222222222222', 'UBA Cameroun Microfinance',        'microfinance',      'business'),
  ('33333333-3333-3333-3333-333333333333', 'Cabinet Audit & Co',                'cabinet_comptable', 'starter')
ON CONFLICT (id) DO UPDATE
  SET nom = EXCLUDED.nom, type = EXCLUDED.type, offre = EXCLUDED.offre;

-- Champs PLG (plan / quotas) — appliqués uniquement si la colonne existe
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_name = 'tenants' AND column_name = 'plan') THEN
    UPDATE tenants SET plan = 'business', max_agents = 50, max_daily_events = 200000
      WHERE id = '11111111-1111-1111-1111-111111111111';  -- Afriland
    UPDATE tenants SET plan = 'business', max_agents = 50, max_daily_events = 200000
      WHERE id = '22222222-2222-2222-2222-222222222222';  -- UBA
    UPDATE tenants SET plan = 'trial', max_agents = 5, max_daily_events = 10000,
                       trial_ends_at = now() + interval '21 days'
      WHERE id = '33333333-3333-3333-3333-333333333333';  -- Cabinet Audit (trial)
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 2. Comptes utilisateurs (RBAC) — mot de passe "admin"
-- ---------------------------------------------------------------------------
INSERT INTO users (tenant_id, email, mot_de_passe, role) VALUES
  (NULL,                                     'admin@nexussoc.cm', crypt('admin', gen_salt('bf')), 'admin_plateforme'),
  (NULL,                                     'soc@nexussoc.cm',   crypt('admin', gen_salt('bf')), 'analyste_soc'),
  ('11111111-1111-1111-1111-111111111111',   'dsi@afriland.cm',   crypt('admin', gen_salt('bf')), 'dsi_client'),
  ('22222222-2222-2222-2222-222222222222',   'dsi@uba.cm',        crypt('admin', gen_salt('bf')), 'dsi_client')
ON CONFLICT (email) DO UPDATE
  SET mot_de_passe = EXCLUDED.mot_de_passe,
      role         = EXCLUDED.role,
      tenant_id    = EXCLUDED.tenant_id,
      actif        = TRUE;

-- Nettoyer un éventuel ancien compte dsi@minfi.cm (au cas où le seed a été
-- appliqué avant cette refonte).
DELETE FROM users WHERE email = 'dsi@minfi.cm';

-- ---------------------------------------------------------------------------
-- 3. Agents de démonstration (idempotent par id fixe)
-- ---------------------------------------------------------------------------
-- Agents Afriland (VLAN 10 dans le lab, tenant testé)
--   POSTE-COMPTA-01 correspond au hostname de vm-cible dans le lab
INSERT INTO agents (id, tenant_id, hostname, os, statut, vu_le) VALUES
  ('a0000001-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111', 'SRV-BUDGET-01',    'linux',   'actif',      now() - interval '2 min'),
  ('a0000002-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111', 'POSTE-COMPTA-01',  'windows', 'actif',      now() - interval '5 min'),
  ('a0000003-0000-0000-0000-000000000003', '22222222-2222-2222-2222-222222222222', 'SRV-CORE-01',      'linux',   'actif',      now() - interval '1 min'),
  ('a0000004-0000-0000-0000-000000000004', '22222222-2222-2222-2222-222222222222', 'DESK-CAISSIER-01', 'windows', 'actif',      now() - interval '8 min'),
  ('a0000005-0000-0000-0000-000000000005', '33333333-3333-3333-3333-333333333333', 'WS-AUDITEUR-01',   'windows', 'hors_ligne', now() - interval '14 h')
ON CONFLICT (id) DO UPDATE
  SET tenant_id = EXCLUDED.tenant_id, hostname = EXCLUDED.hostname,
      statut = EXCLUDED.statut, vu_le = EXCLUDED.vu_le;

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
-- 6. Notifications push in-app pour les portails DSI
--    Génère une notification par alerte si la fonction d'émission existe
--    (créée par 03_schema_notifications.sql). Idempotent : on évite les doublons.
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    a_id UUID;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = 'notifications') THEN
        RAISE NOTICE 'Table notifications absente — appliquez 03_schema_notifications.sql.';
        RETURN;
    END IF;
    FOR a_id IN
        SELECT id FROM alerts
        WHERE id IN (
          'e0000001-0000-0000-0000-000000000001',
          'e0000002-0000-0000-0000-000000000002',
          'e0000003-0000-0000-0000-000000000003',
          'e0000004-0000-0000-0000-000000000004'
        )
    LOOP
        IF NOT EXISTS (SELECT 1 FROM notifications WHERE alert_id = a_id) THEN
            PERFORM emit_notification_from_alert(a_id);
        END IF;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- 7. Récapitulatif
-- ---------------------------------------------------------------------------
DO $$
DECLARE n_users INT; n_alerts INT; n_pending INT; n_notifs INT := 0;
BEGIN
  SELECT COUNT(*) INTO n_users  FROM users  WHERE email LIKE '%@nexussoc.cm' OR email = 'dsi@minfi.cm';
  SELECT COUNT(*) INTO n_alerts FROM alerts;
  SELECT COUNT(*) INTO n_pending FROM soar_audit WHERE statut = 'EN ATTENTE DE VALIDATION';
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='notifications') THEN
    SELECT COUNT(*) INTO n_notifs FROM notifications;
  END IF;
  RAISE NOTICE 'NEXUS SOC seed : % comptes démo, % alertes, % actions SOAR en attente, % notifications.',
               n_users, n_alerts, n_pending, n_notifs;
END $$;
