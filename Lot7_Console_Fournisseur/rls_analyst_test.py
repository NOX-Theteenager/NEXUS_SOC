#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Lot 7 : Test d'isolation RLS étendu (rôle nexus_analyst)
======================================================================
Étend le test du Lot 6 (5 assertions nexus_app) avec 3 assertions supplémentaires
qui vérifient que le rôle nexus_analyst BYPASSRLS voit bien tous les tenants,
tandis que nexus_app reste filtré.

Résumé des assertions :
  Héritage du Lot 6 — nexus_app (soumis à la RLS)
  #1 Tenant A : COUNT(alerts) = 3
  #2 Tenant B : COUNT(alerts) = 2
  #3 Fuite : A interroge tenant_id = B → 0
  #4 Session sans tenant : COUNT = 0
  #5 Tenant A ne voit QUE des lignes de tenant_id = A

  Nouvelles — nexus_analyst (BYPASSRLS)
  #6 Analyst voit TOUTES les alertes (5 = 3 + 2), sans SET app.current_tenant
  #7 Analyst filtrant sur tenant A voit ses 3 alertes
  #8 Analyst voit 2 tenant_id distincts dans les alertes

Condition de succès : 8/8 assertions vérifiées.
"""
import json
import os
import psycopg2

DSN_ADMIN  = "host=/var/run/postgresql dbname=postgres user=postgres"
DSN_TEST   = "host=/var/run/postgresql dbname=nexus_rls_test_lot7 user=postgres"
DSN_APP    = "host=/var/run/postgresql dbname=nexus_rls_test_lot7 user=nexus_app"
DSN_ANALYST = "host=/var/run/postgresql dbname=nexus_rls_test_lot7 user=nexus_analyst"

SCHEMA = """
DROP TABLE IF EXISTS alerts CASCADE;
DROP TABLE IF EXISTS tenants CASCADE;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE tenants (
    id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nom TEXT NOT NULL
);

CREATE TABLE alerts (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    type      TEXT NOT NULL,
    entite    TEXT NOT NULL,
    risque    INT  NOT NULL,
    cree_le   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_alerts ON alerts
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);

-- ---- Rôle applicatif client (soumis à la RLS) ----
DROP ROLE IF EXISTS nexus_app;
CREATE ROLE nexus_app LOGIN;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nexus_app;

-- ---- Rôle analyste SOC (BYPASSRLS — cross-périmètre, read-only sur alerts) ----
DROP ROLE IF EXISTS nexus_analyst;
CREATE ROLE nexus_analyst LOGIN BYPASSRLS NOINHERIT NOSUPERUSER;
GRANT CONNECT ON DATABASE nexus_rls_test_lot7 TO nexus_analyst;
GRANT USAGE ON SCHEMA public TO nexus_analyst;
GRANT SELECT ON alerts, tenants TO nexus_analyst;
"""

A = "11111111-1111-1111-1111-111111111111"   # Périmètre SIGIPES
B = "22222222-2222-2222-2222-222222222222"   # Périmètre Réseau/LAN CENADI


def setup_db():
    conn = psycopg2.connect(DSN_ADMIN); conn.autocommit = True
    with conn.cursor() as c:
        c.execute("DROP DATABASE IF EXISTS nexus_rls_test_lot7")
        c.execute("CREATE DATABASE nexus_rls_test_lot7")
    conn.close()

    conn = psycopg2.connect(DSN_TEST); conn.autocommit = True
    with conn.cursor() as c:
        c.execute(SCHEMA)
        c.execute("INSERT INTO tenants (id, nom) VALUES (%s, %s), (%s, %s)",
                  (A, "SIGIPES", B, "Réseau/LAN CENADI"))
        rows = [
            (A, "Ransomware",       "POSTE-RH-07",       100),
            (A, "Fraude interne",   "agent_SIGIPES_0421", 86),
            (A, "Anomalie réseau",  "SRV-SIGIPES-01",     72),
            (B, "Phishing",         "POSTE-LAN-03",       65),
            (B, "Fraude interne",   "agent_LAN_017",      78),
        ]
        c.executemany("INSERT INTO alerts (tenant_id, type, entite, risque) VALUES (%s,%s,%s,%s)", rows)
    conn.close()


def run_nexus_app_assertions():
    """Rejoue les 5 assertions du Lot 6 avec nexus_app."""
    cases = []
    conn = psycopg2.connect(DSN_APP); conn.autocommit = False

    def q(tenant, sql_str, params=None):
        with conn.cursor() as c:
            if tenant:
                c.execute("SET app.current_tenant = %s", (tenant,))
            else:
                c.execute("RESET app.current_tenant")
            c.execute(sql_str, params or ())
            return c.fetchone()[0]

    n = q(A, "SELECT COUNT(*) FROM alerts")
    cases.append({"id": 1, "name": "nexus_app · Tenant A voit 3 alertes",
                  "got": n, "expect": 3, "ok": n == 3})

    n = q(B, "SELECT COUNT(*) FROM alerts")
    cases.append({"id": 2, "name": "nexus_app · Tenant B voit 2 alertes",
                  "got": n, "expect": 2, "ok": n == 2})

    n = q(A, "SELECT COUNT(*) FROM alerts WHERE tenant_id = %s", (B,))
    cases.append({"id": 3, "name": "nexus_app · Fuite A→B bloquée (→ 0)",
                  "got": n, "expect": 0, "ok": n == 0})

    n = q(None, "SELECT COUNT(*) FROM alerts")
    cases.append({"id": 4, "name": "nexus_app · Sans tenant : 0 alerte visible",
                  "got": n, "expect": 0, "ok": n == 0})

    with conn.cursor() as c:
        c.execute("SET app.current_tenant = %s", (A,))
        c.execute("SELECT DISTINCT tenant_id::text FROM alerts")
        ids = [r[0] for r in c.fetchall()]
    ok = ids == [A]
    cases.append({"id": 5, "name": "nexus_app · Tenant A voit UNIQUEMENT tenant_id=A",
                  "got": ids, "expect": [A], "ok": ok})

    conn.close()
    return cases


def run_analyst_assertions():
    """3 nouvelles assertions : nexus_analyst doit voir à travers les périmètres."""
    cases = []
    conn = psycopg2.connect(DSN_ANALYST); conn.autocommit = False

    # #6 : Analyst voit toutes les alertes (5 = 3 + 2), sans SET app.current_tenant
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) FROM alerts")
        n = c.fetchone()[0]
    cases.append({"id": 6, "name": "nexus_analyst · COUNT(alerts) global = 5 (sans SET tenant)",
                  "got": n, "expect": 5, "ok": n == 5})

    # #7 : Analyst filtre sur tenant A → voit uniquement les 3 alertes de A
    with conn.cursor() as c:
        c.execute("SELECT COUNT(*) FROM alerts WHERE tenant_id = %s", (A,))
        n = c.fetchone()[0]
    cases.append({"id": 7, "name": "nexus_analyst · Filtre sur tenant A → 3 alertes",
                  "got": n, "expect": 3, "ok": n == 3})

    # #8 : Analyst voit 2 tenant_id distincts dans alerts
    with conn.cursor() as c:
        c.execute("SELECT COUNT(DISTINCT tenant_id) FROM alerts")
        n = c.fetchone()[0]
    cases.append({"id": 8, "name": "nexus_analyst · 2 tenant_id distincts visibles",
                  "got": n, "expect": 2, "ok": n == 2})

    conn.close()
    return cases


def render_result(cases, output_dir="./out_lot7"):
    os.makedirs(output_dir, exist_ok=True)
    print("\nNEXUS SOC — Lot 7 : test RLS étendu (nexus_app + nexus_analyst)")
    print("=" * 70)

    # Groupe nexus_app (assertions 1-5)
    print("\n  ▸ Rôle nexus_app (soumis à la RLS — filtré par tenant)")
    for c in cases[:5]:
        flag = "✓" if c["ok"] else "✗"
        print(f"  {flag} #{c['id']} {c['name']:<60}  → {c['got']}")

    # Groupe nexus_analyst (assertions 6-8)
    print("\n  ▸ Rôle nexus_analyst (BYPASSRLS — cross-périmètre)")
    for c in cases[5:]:
        flag = "✓" if c["ok"] else "✗"
        print(f"  {flag} #{c['id']} {c['name']:<60}  → {c['got']}")

    passed = sum(c["ok"] for c in cases)
    total  = len(cases)
    print(f"\n{'─'*70}")
    print(f"  Résultat : {passed}/{total} assertions vérifiées\n")

    result = {"passed": passed, "total": total, "cases": cases}
    with open(f"{output_dir}/rls_analyst_results.json", "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if passed == total:
        print("  ✅ RLS ÉTENDU VÉRIFIÉ")
        print("     nexus_app  : isolation par tenant opérationnelle (5/5)")
        print("     nexus_analyst : vue cross-périmètre opérationnelle (3/3)")
    else:
        print(f"  ❌ {total - passed} assertion(s) en échec — vérifier la configuration RLS.")
    return result


def make_figure(cases, output_dir="./out_lot7"):
    """Génère une figure récapitulative dans la palette du projet."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        NAVY  = "#0B2545"; BLUE  = "#1C6DD0"; TEAL  = "#1B998B"
        RED   = "#C1432E"; AMBER = "#B7791F"

        fig, ax = plt.subplots(figsize=(10, 4.5), facecolor=NAVY)
        ax.set_facecolor(NAVY)

        labels    = [f"#{c['id']} {c['name'][:52]}" for c in cases]
        colors    = [TEAL if c["ok"] else RED for c in cases]
        y_pos     = range(len(labels))

        bars = ax.barh(list(y_pos), [1]*len(cases), color=colors, height=0.6, edgecolor="none")

        # Séparateur entre les deux groupes
        ax.axhline(y=4.5, color=BLUE, linewidth=1, linestyle="--", alpha=0.6)

        for i, c in enumerate(cases):
            mark = "✓" if c["ok"] else "✗"
            ax.text(0.02, i, f" {mark} {labels[i]}", va="center", ha="left",
                    color="white", fontsize=9, fontfamily="DejaVu Sans")

        ax.set_yticks([]); ax.set_xticks([])
        ax.set_xlim(0, 1); ax.set_ylim(-0.5, len(cases)-0.3)
        for spine in ax.spines.values(): spine.set_visible(False)

        passed = sum(c["ok"] for c in cases)
        title  = f"NEXUS SOC — Isolation RLS Lot 7 : {passed}/{len(cases)} assertions"
        ax.set_title(title, color="white", fontsize=12, pad=14, fontfamily="DejaVu Sans")

        # Légende
        patches = [
            mpatches.Patch(color=TEAL,  label=f"nexus_app (RLS)       5/{sum(c['ok'] for c in cases[:5])} assertions"),
            mpatches.Patch(color=BLUE,  label=f"nexus_analyst (BYPASS) {sum(c['ok'] for c in cases[5:])}/3 assertions"),
        ]
        ax.legend(handles=patches, loc="lower right", facecolor=NAVY, edgecolor=BLUE,
                  labelcolor="white", fontsize=8.5)

        # Annotations groupes
        ax.text(0.5, 2,   "nexus_app (RLS — filtré par tenant)",     ha="center", va="center", color=AMBER, fontsize=8, alpha=0.7)
        ax.text(0.5, 6.5, "nexus_analyst (BYPASSRLS — cross-périmètre)", ha="center", va="center", color=AMBER, fontsize=8, alpha=0.7)

        plt.tight_layout()
        out = f"{output_dir}/rls_analyst_result.png"
        plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=NAVY)
        print(f"\n  Figure enregistrée : {out}")
        plt.close()
    except ImportError:
        print("  (matplotlib absent — figure ignorée)")


def main():
    print("Initialisation de la base de test…")
    setup_db()
    app_cases     = run_nexus_app_assertions()
    analyst_cases = run_analyst_assertions()
    all_cases     = app_cases + analyst_cases
    result = render_result(all_cases)
    make_figure(all_cases)
    return result["passed"] == result["total"]


if __name__ == "__main__":
    import sys
    ok = main()
    sys.exit(0 if ok else 1)
