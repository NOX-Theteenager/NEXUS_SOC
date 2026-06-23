-- =============================================================================
-- NEXUS SOC — Schéma des notifications push (in-app) destinées au DSI
-- À appliquer APRÈS : 01_schema_patched.sql, 02_seed_demo.sql
--
-- Remplace les notifications SMS / WhatsApp simulées par un canal in-app
-- consultable et téléchargeable depuis le portail DSI (Lot 9).
-- =============================================================================

CREATE TABLE IF NOT EXISTS notifications (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID         NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert_id    UUID         REFERENCES alerts(id) ON DELETE SET NULL,
    type        VARCHAR(30)  NOT NULL DEFAULT 'alert',  -- alert | soar_action | system | report
    severity    VARCHAR(20)  NOT NULL DEFAULT 'info',   -- info | warning | critical
    title       TEXT         NOT NULL,
    body        TEXT,
    report_html TEXT,                                   -- rapport HTML enrichi (téléchargeable)
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    read_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notif_tenant_unread
    ON notifications(tenant_id, created_at DESC)
    WHERE read_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_notif_tenant_all
    ON notifications(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notif_alert
    ON notifications(alert_id)
    WHERE alert_id IS NOT NULL;

-- RLS : la notification appartient à un tenant ; même politique que les alertes
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_notifications_tenant ON notifications;
CREATE POLICY p_notifications_tenant ON notifications
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

-- Droits applicatifs
GRANT SELECT, UPDATE (read_at) ON notifications TO nexus_app;
GRANT SELECT, INSERT, UPDATE ON notifications TO nexus_analyst;

-- =============================================================================
-- Fonction utilitaire : créer une notification depuis une alerte
-- =============================================================================
CREATE OR REPLACE FUNCTION emit_notification_from_alert(p_alert_id UUID)
RETURNS UUID
LANGUAGE plpgsql AS $$
DECLARE
    rec          RECORD;
    notif_id     UUID;
    sev          VARCHAR(20);
    report       TEXT;
BEGIN
    SELECT al.id, al.tenant_id, al.source_modele, al.type, al.entite,
           al.risque, al.raisons, al.mitre, al.statut, al.cree_le,
           t.nom AS tenant_nom
      INTO rec
      FROM alerts al
      JOIN tenants t ON t.id = al.tenant_id
     WHERE al.id = p_alert_id;
    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    sev := CASE
        WHEN rec.risque >= 80 THEN 'critical'
        WHEN rec.risque >= 60 THEN 'warning'
        ELSE 'info'
    END;

    -- Rapport HTML synthétique attaché à la notification
    report :=
      '<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">' ||
      '<title>Rapport d''incident — ' || COALESCE(rec.entite, 'incident') || '</title>' ||
      '<style>body{font-family:Manrope,system-ui,sans-serif;background:#0A0F1C;color:#E2E8F0;padding:40px;max-width:780px;margin:auto;line-height:1.65}' ||
      'h1{font-family:Fraunces,Georgia,serif;font-style:italic;color:#5EAAFF;border-bottom:2px solid #1E293B;padding-bottom:10px}' ||
      '.meta{font-family:monospace;font-size:12px;color:#64748B;margin-bottom:24px}' ||
      '.risk{display:inline-block;padding:6px 14px;border-radius:999px;font-weight:700;font-family:monospace}' ||
      '.risk.critical{background:rgba(239,68,68,.15);color:#EF4444;border:1px solid #EF4444}' ||
      '.risk.warning{background:rgba(245,165,36,.15);color:#F5A524;border:1px solid #F5A524}' ||
      '.risk.info{background:rgba(94,170,255,.15);color:#5EAAFF;border:1px solid #5EAAFF}' ||
      'section{margin:24px 0;padding:20px;background:#0F1729;border:1px solid #1E293B;border-radius:12px}' ||
      'section h2{font-size:16px;margin-top:0;color:#94A3B8;letter-spacing:.04em;text-transform:uppercase}' ||
      'ul{padding-left:22px}</style></head><body>' ||
      '<h1>Rapport d''incident</h1>' ||
      '<div class="meta">Réf. ' || rec.id::text || ' &middot; tenant ' || COALESCE(rec.tenant_nom, '—') ||
      ' &middot; généré le ' || to_char(now(), 'YYYY-MM-DD HH24:MI:SS TZ') || '</div>' ||
      '<div class="risk ' || sev || '">Risque ' || rec.risque || '/100 &middot; ' || COALESCE(rec.type, 'Incident') || '</div>' ||
      '<section><h2>Synthèse</h2>' ||
      '<p><strong>Type :</strong> ' || COALESCE(rec.type, '—') || '</p>' ||
      '<p><strong>Entité touchée :</strong> ' || COALESCE(rec.entite, '—') || '</p>' ||
      '<p><strong>Source modèle :</strong> ' || COALESCE(rec.source_modele, '—') || '</p>' ||
      '<p><strong>Tactique MITRE :</strong> ' || COALESCE(rec.mitre, '—') || '</p>' ||
      '<p><strong>Détecté le :</strong> ' || to_char(rec.cree_le, 'YYYY-MM-DD HH24:MI:SS TZ') || '</p>' ||
      '</section>' ||
      '<section><h2>Indicateurs</h2><ul>' ||
      COALESCE(
        (SELECT string_agg('<li>' || value || '</li>', '')
           FROM jsonb_array_elements_text(COALESCE(rec.raisons, '[]'::jsonb))),
        '<li>Aucun indicateur structuré disponible.</li>'
      ) ||
      '</ul></section>' ||
      '<section><h2>Recommandations</h2><p>' ||
      CASE
        WHEN rec.risque >= 80 THEN 'Incident <strong>critique</strong>. Validez immédiatement les actions SOAR à fort impact en attente (isolation, gel de compte). Préservez la chaîne de preuves.'
        WHEN rec.risque >= 60 THEN 'Incident <strong>élevé</strong>. Vérifiez le contexte, lancez une investigation manuelle et confirmez les actions SOAR proposées.'
        ELSE 'Incident <strong>informatif</strong>. Surveillez la récurrence du pattern et ajustez les seuils si nécessaire.'
      END ||
      '</p></section>' ||
      '<p style="font-size:11px;color:#64748B;margin-top:32px">Document généré automatiquement par NEXUS SOC. À conserver pour audit.</p>' ||
      '</body></html>';

    INSERT INTO notifications (tenant_id, alert_id, type, severity, title, body, report_html)
    VALUES (
        rec.tenant_id,
        rec.id,
        'alert',
        sev,
        COALESCE(rec.type, 'Incident') || ' — ' || COALESCE(rec.entite, '?'),
        'Score de risque ' || rec.risque || '/100. Cliquez pour consulter le rapport complet.',
        report
    )
    RETURNING id INTO notif_id;

    RETURN notif_id;
END;
$$;
