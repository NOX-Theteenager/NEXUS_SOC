#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Moniteur de dérive des modèles IA
=============================================
Détecte la dégradation silencieuse des modèles en production (concept drift).
Sans monitoring, un modèle peut devenir inefficace sur des données qui ont évolué
sans que personne ne le remarque.

Méthodes implémentées :
  1. Dérive du score de risque (glissement de la distribution des scores)
  2. Évolution du taux de faux positifs (feedback analyste : marquages FP)
  3. Dérive des features (PSI — Population Stability Index)
  4. Surveillance du taux d'alertes (trop peu = modèle trop permissif ; trop = dérive)

Usage autonome :
  python model_monitor.py --db postgresql://... --days 30

Intégration FastAPI (dans scoring-service_app.py) :
  from model_monitor import monitor_router
  app.include_router(monitor_router)
"""
import json
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

# ────────────────────────────────────────────────────────────────────────────
# Seuils de dérive (configurables via env)
# ────────────────────────────────────────────────────────────────────────────
DRIFT_SCORE_SIGMA    = float(os.getenv("DRIFT_SCORE_SIGMA",    "2.0"))  # écart-type autorisé
DRIFT_FP_RATE_MAX    = float(os.getenv("DRIFT_FP_RATE_MAX",    "0.20")) # FP > 20 % → alerte
DRIFT_ALERT_RATE_MIN = float(os.getenv("DRIFT_ALERT_RATE_MIN", "0.005"))# < 0.5 % → modèle trop permissif
DRIFT_ALERT_RATE_MAX = float(os.getenv("DRIFT_ALERT_RATE_MAX", "0.15")) # > 15 % → modèle trop sévère
PSI_WARNING          = float(os.getenv("PSI_WARNING",          "0.10")) # PSI > 0.1 → surveillance
PSI_ALARM            = float(os.getenv("PSI_ALARM",            "0.25")) # PSI > 0.25 → retraining


# ────────────────────────────────────────────────────────────────────────────
# Population Stability Index (PSI)
# ────────────────────────────────────────────────────────────────────────────
def compute_psi(expected: list[float], actual: list[float], bins: int = 10) -> float:
    """
    PSI mesure combien la distribution des scores actuels s'est éloignée
    de la distribution de référence (entraînement).
    PSI < 0.10 : stable
    PSI 0.10–0.25 : surveillance recommandée
    PSI > 0.25 : retraining requis
    """
    if not expected or not actual:
        return 0.0
    min_val = min(min(expected), min(actual))
    max_val = max(max(expected), max(actual))
    if max_val == min_val:
        return 0.0

    step = (max_val - min_val) / bins
    eps  = 1e-6

    def bucket(values):
        counts = [0] * bins
        for v in values:
            b = min(int((v - min_val) / step), bins - 1)
            counts[b] += 1
        total = sum(counts) or 1
        return [c / total for c in counts]

    exp_pct = bucket(expected)
    act_pct = bucket(actual)
    psi = sum(
        (a - e) * math.log((a + eps) / (e + eps))
        for e, a in zip(exp_pct, act_pct)
    )
    return round(psi, 4)


# ────────────────────────────────────────────────────────────────────────────
# Rapport de dérive
# ────────────────────────────────────────────────────────────────────────────
def build_drift_report(
    reference_scores: list[float],
    current_scores:   list[float],
    fp_count:         int,
    total_alerts:     int,
    events_total:     int,
    model_name:       str,
    period_days:      int,
) -> dict:
    """Construit un rapport complet de dérive pour un modèle."""
    alerts = []
    severity = "ok"

    # 1. Dérive de la distribution des scores (glissement de la moyenne)
    if reference_scores and current_scores:
        ref_mean = statistics.mean(reference_scores)
        ref_std  = statistics.stdev(reference_scores) if len(reference_scores) > 1 else 1
        cur_mean = statistics.mean(current_scores)
        score_drift = abs(cur_mean - ref_mean) / (ref_std or 1)

        psi = compute_psi(reference_scores, current_scores)

        if score_drift > DRIFT_SCORE_SIGMA or psi > PSI_ALARM:
            severity = "alarm"
            alerts.append({
                "type":    "score_drift",
                "message": f"Distribution des scores dérivée : {score_drift:.1f}σ (PSI={psi:.3f})",
                "action":  "Retraining requis.",
            })
        elif psi > PSI_WARNING:
            severity = max(severity, "warning") if severity != "alarm" else severity
            alerts.append({
                "type":    "score_psi_warning",
                "message": f"PSI={psi:.3f} — distribution en cours de dérive",
                "action":  "Surveiller. Programmer un retraining si PSI > 0.25.",
            })
    else:
        psi = None
        score_drift = None
        cur_mean = None

    # 2. Taux de faux positifs
    fp_rate = fp_count / total_alerts if total_alerts > 0 else 0
    if fp_rate > DRIFT_FP_RATE_MAX:
        severity = "alarm"
        alerts.append({
            "type":    "high_fp_rate",
            "message": f"Taux de faux positifs : {fp_rate:.1%} (seuil : {DRIFT_FP_RATE_MAX:.0%})",
            "action":  "Réviser les seuils ou ré-entraîner sur des données récentes.",
        })

    # 3. Taux d'alertes global
    alert_rate = total_alerts / events_total if events_total > 0 else 0
    if alert_rate < DRIFT_ALERT_RATE_MIN and events_total > 100:
        severity = max(severity, "warning") if severity != "alarm" else severity
        alerts.append({
            "type":    "too_few_alerts",
            "message": f"Taux d'alertes très bas : {alert_rate:.3%} — modèle peut-être trop permissif",
            "action":  "Vérifier le seuil de risque et la qualité de la télémétrie.",
        })
    elif alert_rate > DRIFT_ALERT_RATE_MAX:
        severity = max(severity, "warning") if severity != "alarm" else severity
        alerts.append({
            "type":    "too_many_alerts",
            "message": f"Taux d'alertes élevé : {alert_rate:.2%} — possible sur-sensibilité",
            "action":  "Augmenter le seuil de risque ou filtrer avec une règle de suppression.",
        })

    return {
        "model":         model_name,
        "period_days":   period_days,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "severity":      severity,
        "summary": {
            "total_events":  events_total,
            "total_alerts":  total_alerts,
            "fp_count":      fp_count,
            "fp_rate":       round(fp_rate, 4),
            "alert_rate":    round(alert_rate, 4),
            "score_mean":    round(statistics.mean(current_scores), 2) if current_scores else None,
            "psi":           psi,
            "score_drift_sigma": round(score_drift, 2) if score_drift is not None else None,
        },
        "alerts":         alerts,
        "recommendation": _recommendation(severity, alerts),
    }


def _recommendation(severity: str, alerts: list) -> str:
    if severity == "ok":
        return "Modèle stable. Prochain contrôle recommandé dans 7 jours."
    if severity == "warning":
        return "Surveillance renforcée recommandée. Retraining à planifier si la tendance se confirme."
    types = {a["type"] for a in alerts}
    if "high_fp_rate" in types:
        return "Retraining urgent : trop de faux positifs signalés par les analystes."
    return "Retraining requis : distribution des scores trop éloignée de la référence d'entraînement."


# ────────────────────────────────────────────────────────────────────────────
# Interface base de données (requêtes sur TimescaleDB)
# ────────────────────────────────────────────────────────────────────────────
def _fetch_drift_data(db_conn, model_name: str, days: int) -> dict:
    """Récupère les métriques depuis la base pour calculer la dérive."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with db_conn.cursor() as cur:
        # Scores des alertes du modèle sur la période
        cur.execute(
            "SELECT risque FROM alerts WHERE source_modele LIKE %s AND cree_le >= %s",
            (f"%{model_name}%", since)
        )
        scores = [row[0] for row in cur.fetchall()]

        # Faux positifs marqués par les analystes
        cur.execute(
            "SELECT COUNT(*) FROM alerts WHERE source_modele LIKE %s AND statut = 'faux_positif' AND cree_le >= %s",
            (f"%{model_name}%", since)
        )
        fp_count = cur.fetchone()[0]

        # Volume d'événements total (approximé depuis soar_audit ou events)
        cur.execute(
            "SELECT COALESCE(SUM(valeur), 0) FROM metrics WHERE metrique = 'events_total' AND ts >= %s",
            (since,)
        )
        events_total = int(cur.fetchone()[0]) or max(len(scores) * 20, 1)

    return {
        "current_scores": scores,
        "fp_count":       fp_count,
        "total_alerts":   len(scores),
        "events_total":   events_total,
    }


# ────────────────────────────────────────────────────────────────────────────
# FastAPI router
# ────────────────────────────────────────────────────────────────────────────
try:
    from fastapi import APIRouter, Depends
    import psycopg2, psycopg2.extras
    from auth_middleware import require_analyst

    monitor_router = APIRouter(prefix="/monitor", tags=["Monitoring modèles"])

    def get_db():
        conn = psycopg2.connect(
            os.getenv("DB_DSN", "postgresql://nexus_app:nexus_pass@localhost:5432/nexus")
        )
        try:
            yield conn
        finally:
            conn.close()

    # Scores de référence stockés à l'entraînement (idéalement en base, ici en env)
    _REF_M1 = json.loads(os.getenv("REF_SCORES_M1", "[]"))
    _REF_M2 = json.loads(os.getenv("REF_SCORES_M2", "[]"))

    @monitor_router.get("/drift", summary="Rapport de dérive des modèles IA")
    def drift_report(days: int = 7, db=Depends(get_db), _=Depends(require_analyst)):
        reports = []
        for model_name, ref_scores in [("réseau", _REF_M1), ("UEBA", _REF_M2)]:
            data = _fetch_drift_data(db, model_name, days)
            report = build_drift_report(
                reference_scores = ref_scores,
                current_scores   = data["current_scores"],
                fp_count         = data["fp_count"],
                total_alerts     = data["total_alerts"],
                events_total     = data["events_total"],
                model_name       = f"Modèle 1 ({model_name})" if "réseau" in model_name else f"Modèle 2 ({model_name})",
                period_days      = days,
            )
            reports.append(report)
        global_severity = "alarm" if any(r["severity"] == "alarm" for r in reports) else \
                          "warning" if any(r["severity"] == "warning" for r in reports) else "ok"
        return {"global_severity": global_severity, "models": reports}

except ImportError:
    monitor_router = None


# ────────────────────────────────────────────────────────────────────────────
# Mode autonome (CLI)
# ────────────────────────────────────────────────────────────────────────────
def main():
    import argparse
    ap = argparse.ArgumentParser(description="NEXUS SOC — Moniteur de dérive des modèles")
    ap.add_argument("--db",   default=os.getenv("DB_DSN", ""), help="DSN PostgreSQL")
    ap.add_argument("--days", type=int, default=7, help="Fenêtre d'analyse (jours)")
    ap.add_argument("--demo", action="store_true", help="Rapport sur données synthétiques")
    args = ap.parse_args()

    if args.demo:
        # Simulation : scores de référence normaux vs scores driftés
        import random
        ref   = [random.gauss(35, 15) for _ in range(1000)]
        drift = [random.gauss(55, 20) for _ in range(200)]   # dérive visible
        report = build_drift_report(
            reference_scores = ref,
            current_scores   = drift,
            fp_count         = 42,
            total_alerts     = 200,
            events_total     = 50000,
            model_name       = "Modèle 1 (réseau) — DÉMO",
            period_days      = args.days,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    if not args.db:
        print("Usage : python model_monitor.py --demo")
        print("        python model_monitor.py --db postgresql://... [--days N]")
        return

    import psycopg2
    conn = psycopg2.connect(args.db)
    for model_name, ref_scores in [("réseau", []), ("UEBA", [])]:
        data   = _fetch_drift_data(conn, model_name, args.days)
        report = build_drift_report(
            reference_scores = ref_scores,
            current_scores   = data["current_scores"],
            fp_count         = data["fp_count"],
            total_alerts     = data["total_alerts"],
            events_total     = data["events_total"],
            model_name       = model_name,
            period_days      = args.days,
        )
        sev_color = {"ok": "\033[32m", "warning": "\033[33m", "alarm": "\033[31m"}
        reset = "\033[0m"
        print(f"\n{sev_color.get(report['severity'],'')}{'═'*60}")
        print(f"Modèle : {report['model']}  — Sévérité : {report['severity'].upper()}{reset}")
        s = report["summary"]
        print(f"  Alertes : {s['total_alerts']}  FP : {s['fp_count']}  FP-rate : {s['fp_rate']:.1%}")
        print(f"  PSI : {s['psi']}  Score moyen : {s['score_mean']}  Drift : {s['score_drift_sigma']}σ")
        for a in report["alerts"]:
            print(f"  ⚠ [{a['type']}] {a['message']}")
        print(f"  → {report['recommendation']}")
    conn.close()


if __name__ == "__main__":
    main()
