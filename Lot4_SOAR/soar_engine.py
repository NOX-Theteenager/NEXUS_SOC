#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Moteur SOAR (réponse automatisée encadrée)
======================================================
Transforme une ALERTE produite par les modèles d'IA (Modèle 1 réseau / Modèle 2 fraude)
en une RÉPONSE automatisée, exécutée via des PLAYBOOKS et protégée par des GARDE-FOUS :

  • Seuil de confiance      → une action ne s'exécute que si le risque est suffisant.
  • Validation humaine      → les actions à FORT IMPACT sont mises en attente d'approbation.
  • Mode simulation (dry-run) → rien n'est exécuté, on visualise ce qui SERAIT fait.
  • Réversibilité (rollback) → toute action réversible peut être annulée.
  • Journal d'audit         → chaque décision et action est tracée (qui, quoi, quand, statut).

Les "connecteurs" d'action sont ici SIMULÉS (pas de vrai pare-feu / annuaire), mais exposent
l'interface réelle d'intégration de la plateforme.

Usage :
    python soar_engine.py                       # démo (connecte le Modèle 2 si dispo)
    python soar_engine.py --execute             # exécution réelle (sinon : dry-run)

Auteur : NGUETSA Junior Stéphane Céleste — Projet NEXUS SOC
"""

import argparse, csv, datetime, json, os, sys, uuid
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Niveaux d'impact des actions
# --------------------------------------------------------------------------- #
INFO, LOW, MEDIUM, HIGH = "info", "faible", "moyen", "fort"
IMPACT_RANK = {INFO: 0, LOW: 1, MEDIUM: 2, HIGH: 3}


# --------------------------------------------------------------------------- #
# Modèle d'alerte (format standard émis par les modèles d'IA)
# --------------------------------------------------------------------------- #
@dataclass
class Alert:
    type: str                       # ex. "Fraude interne", "Ransomware", "Anomalie réseau / C2"
    entity: str                     # ex. "agent_DGI_0421" ou "DESKTOP-COMPTA-01"
    entity_kind: str                # "compte" | "poste"
    risk: int                       # score de risque 0-100 (issu du modèle)
    reasons: list                   # raisons (explicabilité du modèle)
    source: str                     # ex. "Modèle 2 (UEBA)"
    mitre: str = ""                 # technique MITRE ATT&CK le cas échéant
    id: str = field(default_factory=lambda: "ALT-" + uuid.uuid4().hex[:6].upper())
    ts: str = field(default_factory=lambda: datetime.datetime.now().isoformat(timespec="seconds"))


# --------------------------------------------------------------------------- #
# Connecteurs d'action (SIMULÉS). Chacun renvoie (détail, réversible, annulation)
# --------------------------------------------------------------------------- #
def _freeze_account(a):   return (f"Compte « {a.entity} » gelé (accès suspendus)", True,  f"Réactiver le compte « {a.entity} »")
def _isolate_host(a):     return (f"Poste « {a.entity} » isolé du réseau", True,  f"Reconnecter le poste « {a.entity} »")
def _block_ip(a):         return ("IP/destination malveillante bloquée au pare-feu", True, "Débloquer l'IP au pare-feu")
def _reset_password(a):   return (f"Mot de passe de « {a.entity} » réinitialisé", False, None)
def _snapshot(a):         return (f"Capture mémoire/état de « {a.entity} » réalisée", False, None)
def _journal(a):          return (f"Activité de « {a.entity} » figée et journalisée (preuve conservée pour enquête)", False, None)
def _preserve_logs(a):    return ("Journaux d'audit liés archivés (chaîne de preuve)", False, None)

# Notification push in-app vers le portail DSI : remplace les anciens
# connecteurs notify_sms / notify_whatsapp. La persistance réelle (table
# `notifications` + rapport HTML enrichi) est effectuée par la fonction
# Postgres `emit_notification_from_alert(alert_id)` appelée par le pipeline,
# ou par le caller qui dispose d'une connexion DB. Le connecteur SOAR
# se contente ici d'enregistrer l'action et son intention.
def _notify_dsi(a):
    return (f"Notification poussée au portail DSI (rapport téléchargeable, alerte « {a.entity} »)", False, None)


# Enrichissement IOC via VirusTotal : ajoute aux raisons de l'alerte le verdict
# multi-AV pour les IP / hash / domaines extraits. Bascule en no-op si
# VIRUSTOTAL_ENABLED=false (mode dégradé silencieux).
def _enrich_ioc(a):
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from virustotal_client import lookup_alert_iocs
        verdicts = lookup_alert_iocs(a)
    except Exception as e:
        return (f"Enrichissement VirusTotal indisponible ({e})", False, None)

    if not verdicts:
        return ("Aucun IOC exploitable extrait de l'alerte (ou VirusTotal désactivé)", False, None)

    # On enrichit l'alerte elle-même pour que la suite du playbook (notification
    # DSI) intègre les verdicts dans le rapport.
    parts = []
    for v in verdicts:
        tag = v["verdict"].upper()
        parts.append(f"VirusTotal[{tag}] {v['kind']}={v['ioc']} (malv={v['malicious']}, susp={v['suspicious']})")
        if isinstance(a.reasons, list):
            a.reasons.append(parts[-1])
    return (" ; ".join(parts), False, None)


ACTIONS = {
    "journal_investigation": dict(label="Journaliser pour enquête",                  impact=LOW,    fn=_journal),
    "preserve_logs":         dict(label="Archiver les journaux",                      impact=LOW,    fn=_preserve_logs),
    "enrich_ioc":            dict(label="Enrichir l'IOC (VirusTotal)",                impact=INFO,   fn=_enrich_ioc),
    "notify_dsi":            dict(label="Notifier le DSI (push in-app + rapport)",    impact=LOW,    fn=_notify_dsi),
    "snapshot_memory":       dict(label="Capturer la mémoire",                        impact=MEDIUM, fn=_snapshot),
    "block_ip":              dict(label="Bloquer l'IP malveillante",                  impact=MEDIUM, fn=_block_ip),
    "reset_password":        dict(label="Réinitialiser le mot de passe",              impact=MEDIUM, fn=_reset_password),
    "freeze_account":        dict(label="Geler le compte",                            impact=HIGH,   fn=_freeze_account),
    "isolate_host":          dict(label="Isoler le poste",                            impact=HIGH,   fn=_isolate_host),
}

# Playbooks : séquence d'actions par type d'incident
# enrich_ioc en tête : aucun impact, juste de la collecte, mais peut changer
# le contenu du rapport DSI envoyé ensuite.
PLAYBOOKS = {
    "Fraude interne":        ["enrich_ioc", "journal_investigation", "notify_dsi", "freeze_account", "preserve_logs"],
    "Exfiltration":          ["enrich_ioc", "journal_investigation", "freeze_account", "block_ip", "notify_dsi"],
    "Ransomware":            ["enrich_ioc", "snapshot_memory", "isolate_host", "block_ip", "notify_dsi"],
    "Anomalie réseau / C2":  ["enrich_ioc", "journal_investigation", "block_ip", "notify_dsi"],
}


# --------------------------------------------------------------------------- #
# Moteur SOAR
# --------------------------------------------------------------------------- #
class SOAREngine:
    def __init__(self, dry_run=True, auto_threshold=70,
                 auto_exec_max_impact=MEDIUM, high_override=None, audit_path="audit_log.csv"):
        self.dry_run = dry_run
        self.auto_threshold = auto_threshold          # risque min pour exécution auto
        self.auto_max = IMPACT_RANK[auto_exec_max_impact]  # impact max exécuté sans validation
        self.high_override = high_override            # risque au-delà duquel le fort impact s'auto-exécute (None = jamais)
        self.audit = []
        self.audit_path = audit_path
        self.incidents = {}                           # id -> {alert, actions[]}

    # --- règle de décision : auto / validation / ignorée ---
    def _decide(self, impact, risk):
        rank = IMPACT_RANK[impact]
        if rank <= IMPACT_RANK[LOW]:
            return "auto"                             # info/faible : toujours (sûr et souhaitable)
        if rank <= self.auto_max:
            return "auto" if risk >= self.auto_threshold else "validation"
        # impact FORT
        if self.high_override is not None and risk >= self.high_override:
            return "auto"
        return "validation"                           # human-in-the-loop par défaut

    def _log(self, alert, action_key, impact, decision, status, detail):
        row = {"horodatage": datetime.datetime.now().isoformat(timespec="seconds"),
               "incident": alert.id, "type": alert.type, "entite": alert.entity,
               "risque": alert.risk, "action": ACTIONS[action_key]["label"],
               "impact": impact, "decision": decision, "statut": status,
               "detail": detail, "acteur": "SOAR (auto)" if "auto" in decision else "—"}
        self.audit.append(row)

    def handle(self, alert):
        playbook = PLAYBOOKS.get(alert.type)
        inc = {"alert": alert, "actions": []}
        self.incidents[alert.id] = inc
        print(f"\n┌─ INCIDENT {alert.id} · {alert.type} · risque {alert.risk}/100 "
              f"· {alert.source}")
        print(f"│  Entité : {alert.entity} ({alert.entity_kind})"
              + (f" · MITRE {alert.mitre}" if alert.mitre else ""))
        if alert.reasons:
            print(f"│  Raisons : {alert.reasons[0]}")
        if not playbook:
            print("│  Aucun playbook pour ce type — escalade manuelle.")
            return inc
        for key in playbook:
            meta = ACTIONS[key]; impact = meta["impact"]
            decision = self._decide(impact, alert.risk)

            if self.dry_run:
                detail = f"[SIMULATION] {meta['fn'](alert)[0]}"
                status = "SIMULÉE" if decision == "auto" else "SIMULÉE (validation requise)"
            elif decision == "validation":
                detail = "Action à fort impact mise en file d'attente d'approbation"
                status = "EN ATTENTE DE VALIDATION"
                inc["actions"].append({"key": key, "status": status, "rollback": None})
            elif decision == "auto":
                d, reversible, undo = meta["fn"](alert)
                detail, status = d, "EXÉCUTÉE"
                inc["actions"].append({"key": key, "status": status,
                                       "rollback": undo if reversible else None})
            else:
                detail, status = "Risque insuffisant — non exécutée", "IGNORÉE"

            self._log(alert, key, impact, decision, status, detail)
            tag = {"EXÉCUTÉE": "✓", "EN ATTENTE DE VALIDATION": "⏸", "IGNORÉE": "✗"}.get(
                status.split(" (")[0], "·")
            print(f"│   {tag} [{impact:^6}] {meta['label']:<28} → {status}")
        print("└─ fin du playbook")
        return inc

    # --- validation humaine d'une action en attente ---
    def approve(self, incident_id, action_key, approver="DSI"):
        inc = self.incidents[incident_id]; alert = inc["alert"]
        for act in inc["actions"]:
            if act["key"] == action_key and act["status"] == "EN ATTENTE DE VALIDATION":
                d, reversible, undo = ACTIONS[action_key]["fn"](alert)
                act["status"] = "EXÉCUTÉE"; act["rollback"] = undo if reversible else None
                self._log(alert, action_key, ACTIONS[action_key]["impact"],
                          f"validation ({approver})", "EXÉCUTÉE (après validation)", d)
                print(f"  ✓ {approver} a validé « {ACTIONS[action_key]['label']} » "
                      f"sur l'incident {incident_id} → EXÉCUTÉE")
                return True
        return False

    # --- annulation (rollback) des actions réversibles d'un incident ---
    def rollback(self, incident_id, by="DSI"):
        inc = self.incidents[incident_id]; alert = inc["alert"]
        print(f"\n  ↩ ROLLBACK de l'incident {incident_id} (faux positif confirmé par {by})")
        for act in reversed(inc["actions"]):
            if act.get("rollback"):
                self._log(alert, act["key"], ACTIONS[act["key"]]["impact"],
                          f"rollback ({by})", "ANNULÉE", act["rollback"])
                print(f"     ↩ {act['rollback']}")
                act["status"] = "ANNULÉE"

    def save_audit(self):
        if not self.audit:
            return
        cols = list(self.audit[0].keys())
        with open(self.audit_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(self.audit)
        print(f"\n  Journal d'audit ({len(self.audit)} lignes) → {self.audit_path}")


# --------------------------------------------------------------------------- #
# Connexion aux modèles : construire des alertes à partir de leur sortie
# --------------------------------------------------------------------------- #
def alerts_from_model2(n_alertes=3):
    """Charge le Modèle 2, score un échantillon, et convertit les fraudes détectées
    en alertes au format standard. Fallback sur des alertes types si indisponible."""
    try:
        import numpy as np, joblib
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model2"))
        sys.path.insert(0, "/home/claude/nexus/model2")
        from model2_fraud_detection import make_synthetic, FEATURES, reasons
        bundle = None
        for p in ["/home/claude/nexus/model2/outputs_m2/model2_isoforest.joblib",
                  "./model2_isoforest.joblib"]:
            if os.path.exists(p):
                bundle = joblib.load(p); break
        if bundle is None:
            raise FileNotFoundError("modèle non trouvé")
        df = make_synthetic(6000).reset_index(drop=True)
        X = df[FEATURES].values
        s = -bundle["model"].score_samples(bundle["scaler"].transform(X))
        risk = np.clip((s - bundle["risk_lo"]) / (bundle["risk_hi"] - bundle["risk_lo"]) * 100, 0, 100)
        flagged = np.where((s >= bundle["threshold"]) & (df["type"].values != "Normal"))[0]
        mitre = {"Exfiltration": "T1048 (Exfiltration)", "Fonctionnaire fantôme": "T1136 (Création de compte)",
                 "Faux mandatement": "T1565 (Manipulation de données)"}
        out, seen = [], set()
        for i in flagged[np.argsort(risk[flagged])[::-1]]:
            t = df["type"].values[i]
            if t in seen:      # un exemple par type de fraude
                continue
            seen.add(t)
            out.append(Alert(type="Exfiltration" if t == "Exfiltration" else "Fraude interne",
                             entity=f"agent_DGI_{i:04d}", entity_kind="compte",
                             risk=int(risk[i]), reasons=reasons(X[i], bundle["normal_mean"], bundle["normal_std"]),
                             source="Modèle 2 (UEBA)", mitre=mitre.get(t, "")))
            if len(out) >= n_alertes:
                break
        if out:
            print(f"  → {len(out)} alerte(s) construite(s) à partir du Modèle 2.")
            return out
    except Exception as e:
        print(f"  (Modèle 2 indisponible : {e} — alertes types utilisées)")
    # fallback
    return [
        Alert("Fraude interne", "agent_DGI_0421", "compte", 86,
              ["montant total modifié anormalement élevé (9.2σ)", "actions hors heures (5.9σ)"],
              "Modèle 2 (UEBA)", "T1565 (Manipulation de données)"),
        Alert("Exfiltration", "agent_DGI_1187", "compte", 91,
              ["volume de données exportées anormalement élevé (13σ)", "accès dossiers sensibles (12σ)"],
              "Modèle 2 (UEBA)", "T1048 (Exfiltration)"),
    ]


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="NEXUS SOC — Moteur SOAR")
    ap.add_argument("--execute", action="store_true", help="exécution réelle (sinon dry-run)")
    ap.add_argument("--audit", default="audit_log.csv")
    args = ap.parse_args()

    print("NEXUS SOC — Moteur SOAR (réponse automatisée encadrée)\n" + "=" * 54)
    print(f"Mode : {'EXÉCUTION RÉELLE' if args.execute else 'SIMULATION (dry-run)'} · "
          f"seuil auto = 70/100 · fort impact = validation humaine")

    eng = SOAREngine(dry_run=not args.execute, auto_threshold=70,
                     auto_exec_max_impact=MEDIUM, high_override=None, audit_path=args.audit)

    # 1) Connexion aux modèles : alertes issues du Modèle 2
    print("\n[Connexion aux modèles d'IA → génération des alertes]")
    alerts = alerts_from_model2(3)
    # + une alerte réseau (Modèle 1) pour illustrer la généralité
    alerts.append(Alert("Ransomware", "DESKTOP-COMPTA-01", "poste", 96,
                        ["débit sortant anormal vers IP suspecte", "processus inconnu"],
                        "Modèle 1 (réseau)", "T1486 (Chiffrement) / T1071 (C2)"))

    # 2) Traitement par le SOAR
    incidents = [eng.handle(a) for a in alerts]

    # 3) Démonstration des garde-fous (uniquement en mode exécution réelle)
    if args.execute:
        fraude = next((i for i in incidents if i["alert"].type in ("Fraude interne", "Exfiltration")), None)
        if fraude:
            aid = fraude["alert"].id
            print("\n[Garde-fou 1 — validation humaine d'une action à fort impact]")
            eng.approve(aid, "freeze_account", approver="DSI")
            print("\n[Garde-fou 2 — rollback après confirmation d'un faux positif]")
            eng.rollback(aid, by="DSI")

    eng.save_audit()
    print("\nTerminé.")


if __name__ == "__main__":
    main()
