#!/usr/bin/env python3
"""
NEXUS SOC — Tests de fumée de l'API REST
========================================
Valide le parcours de bout en bout contre une instance LANCÉE :

    # Terminal 1 — démarrer le serveur (depuis la racine du projet)
    uvicorn run:app --port 8000

    # Terminal 2 — lancer les tests
    pip install pytest httpx
    pytest Lot6_Tests/test_api.py -v

Prérequis : PostgreSQL accessible + schémas appliqués + 02_seed_demo.sql exécuté
(comptes admin@nexussoc.cm / soc@nexussoc.cm / dsi@minfi.cm, mot de passe « admin »).

Variables d'environnement optionnelles :
    NEXUS_BASE_URL   (défaut http://localhost:8000)
    NEXUS_TEST_PWD   (défaut « admin »)

Si le serveur n'est pas joignable, tous les tests sont ignorés (skip) plutôt
qu'en échec — utile en CI sans backend.
"""
import os
import pytest

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

BASE = os.getenv("NEXUS_BASE_URL", "http://localhost:8000")
PWD  = os.getenv("NEXUS_TEST_PWD", "admin")

ACCOUNTS = {
    "admin":   ("admin@nexussoc.cm", "admin_plateforme"),
    "analyst": ("soc@nexussoc.cm",   "analyste_soc"),
    "dsi":     ("dsi@minfi.cm",      "dsi_client"),
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _client():
    if httpx is None:
        pytest.skip("httpx non installé (pip install httpx)")
    try:
        c = httpx.Client(base_url=BASE, timeout=5.0)
        c.get("/health")  # ping
        return c
    except Exception:
        pytest.skip(f"Serveur NEXUS injoignable sur {BASE} — démarrez `uvicorn run:app`")


def _login(client, who):
    email, _ = ACCOUNTS[who]
    r = client.post("/auth/token", json={"email": email, "password": PWD})
    assert r.status_code == 200, f"login {who} → {r.status_code} {r.text}"
    data = r.json()
    assert "access_token" in data
    return data["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def client():
    c = _client()
    yield c
    c.close()


# ── Santé ──────────────────────────────────────────────────────────────────

def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ── Authentification ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("who", ["admin", "analyst", "dsi"])
def test_login_each_role(client, who):
    token = _login(client, who)
    r = client.get("/auth/me", headers=_auth(token))
    assert r.status_code == 200
    assert r.json().get("role") == ACCOUNTS[who][1]


def test_login_wrong_password(client):
    r = client.post("/auth/token", json={"email": ACCOUNTS["admin"][0], "password": "mauvais"})
    assert r.status_code == 401


def test_admin_endpoint_requires_auth(client):
    r = client.get("/admin/tenants")  # sans token
    assert r.status_code in (401, 403, 422)


def test_invalid_jwt_rejected(client):
    r = client.get("/admin/tenants", headers=_auth("ceci.nest.pas.un.jwt"))
    assert r.status_code in (401, 403)


# ── Routes admin ──────────────────────────────────────────────────────────────

def test_admin_list_tenants(client):
    token = _login(client, "admin")
    r = client.get("/admin/tenants", headers=_auth(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_list_agents(client):
    token = _login(client, "admin")
    r = client.get("/admin/agents", headers=_auth(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_dsi_cannot_access_admin(client):
    """Un dsi_client ne doit PAS accéder aux routes admin."""
    token = _login(client, "dsi")
    r = client.get("/admin/tenants", headers=_auth(token))
    assert r.status_code == 403


# ── Routes analyste ───────────────────────────────────────────────────────────

def test_analyst_alerts(client):
    token = _login(client, "analyst")
    r = client.get("/analyst/alerts", headers=_auth(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_analyst_pending_soar(client):
    token = _login(client, "analyst")
    r = client.get("/analyst/pending", headers=_auth(token))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_analyst_dashboard(client):
    token = _login(client, "analyst")
    r = client.get("/analyst/dashboard", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert "open_alerts" in body


# ── PLG ──────────────────────────────────────────────────────────────────────

def test_plg_plans_public(client):
    r = client.get("/plg/plans")
    assert r.status_code == 200


def test_plg_check_email_disposable_blocked(client):
    r = client.post("/plg/check-email", json={"email": "test@mailinator.com"})
    assert r.status_code == 422  # email jetable refusé


def test_plg_check_email_gov_redirect(client):
    r = client.post("/plg/check-email", json={"email": "agent@minfi.gov.cm"})
    assert r.status_code == 422  # domaine souverain → flux Hub & Spoke
    detail = r.json().get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("code") == "GOV_DOMAIN_REDIRECT"


def test_plg_check_email_valid(client):
    r = client.post("/plg/check-email", json={"email": "dsi@caisse-abc.com"})
    assert r.status_code == 200


# ── Cycle complet tenant (admin) ──────────────────────────────────────────────

def test_tenant_lifecycle(client):
    """Crée → suspend → réactive → supprime un tenant de test."""
    token = _login(client, "admin")
    h = _auth(token)

    # Création
    r = client.post("/admin/tenants", headers=h, json={
        "nom": "TEST PYTEST SA", "type": "microfinance",
        "offre": "starter", "email_admin": "test-pytest@example.com",
    })
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    try:
        # Suspension
        r = client.post(f"/admin/tenants/{tid}/suspend", headers=h)
        assert r.status_code == 200
        # Réactivation
        r = client.post(f"/admin/tenants/{tid}/activate", headers=h)
        assert r.status_code == 200
    finally:
        # Nettoyage
        r = client.delete(f"/admin/tenants/{tid}", headers=h)
        assert r.status_code in (200, 204)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
