-- =============================================================================
-- NEXUS SOC — Lot 8 : Migration OTP
-- À appliquer APRÈS : 01_schema_plg.sql
--
-- Ajoute le code OTP 6 chiffres à plg_registrations + une table générique
-- otp_codes réutilisable pour la 2FA des comptes existants (login,
-- réinitialisation de mot de passe, etc.).
-- =============================================================================

-- ── 1. Code OTP pour la vérification PLG ────────────────────────────────────
ALTER TABLE plg_registrations
    ADD COLUMN IF NOT EXISTS verification_otp        VARCHAR(6),
    ADD COLUMN IF NOT EXISTS verification_expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_plg_reg_email_otp
    ON plg_registrations(email)
    WHERE email_verified = FALSE AND verification_otp IS NOT NULL;

-- ── 2. Table générique pour les autres OTP (login 2FA, reset mdp…) ──────────
CREATE TABLE IF NOT EXISTS otp_codes (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    purpose     VARCHAR(30)  NOT NULL,          -- 'login_2fa' | 'pwd_reset' | ...
    email       VARCHAR(255) NOT NULL,
    code        VARCHAR(6)   NOT NULL,
    expires_at  TIMESTAMPTZ  NOT NULL,
    consumed_at TIMESTAMPTZ,
    attempts    SMALLINT     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_otp_codes_lookup
    ON otp_codes(email, purpose, expires_at DESC)
    WHERE consumed_at IS NULL;

-- Anti-bruteforce : un seul OTP actif par (email, purpose). À chaque nouvelle
-- demande, on consomme les précédents (via UPDATE consumed_at = now()).
COMMENT ON TABLE otp_codes IS
'OTP à usage unique. Insertion : invalider les précédents par UPDATE consumed_at=now() WHERE email=$ AND purpose=$ AND consumed_at IS NULL.';

GRANT SELECT, INSERT, UPDATE ON otp_codes TO nexus_app;
