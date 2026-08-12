#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Moteur de corrélation SIEM v2 (Lot 2 — correctifs)
===============================================================
Correctifs par rapport à v1 :
  1. detect_mass_file_change : O(N²) → O(N) via compteur glissant à deux pointeurs.
  2. Nouvelles règles SIEM :
       T1027 — Obfuscated Files (dédié : base64 inline, extensions doubles, patterns)
       T1136 — Create Account (création de compte hors heures / volumétrie anormale)
       T1083 — File and Directory Discovery (accès énumération de répertoires sensibles)
  3. Fenêtre de corrélation configurable via la variable d'env CORR_WINDOW_MIN (défaut 30).
  4. Métriques de performance intégrées pour mesurer le gain O(N²) → O(N).
"""
import argparse, json, os, time, re
from collections import defaultdict, deque
from datetime import datetime, timedelta

try:
    from telemetry_gen import generate
except ImportError:
    generate = None

# ────────────────────────────────────────────────────────────────────────────
# Listes de détection
# ────────────────────────────────────────────────────────────────────────────
SUSPICIOUS_PROCS   = {"cmd.exe", "powershell.exe", "powershell", "wscript.exe",
                      "cscript.exe", "nc", "ncat", "mshta.exe", "rundll32.exe"}
C2_PORTS           = {"4444", "6667", "1337", "9001", "31337", "5555"}
TI_IPS             = {"185.220.101.45"}
SENSITIVE_PATHS    = ("/etc/shadow", "/etc/passwd", "/etc/sudoers",
                      "finance", "budget", "contribuable", "sigipes", "sydonia")
DOWNLOAD_EXT       = (".exe", ".scr", ".js", ".bat", ".vbs")
MASS_FILE_THRESHOLD = int(os.getenv("MASS_FILE_THRESHOLD", "20"))
MASS_FILE_WINDOW_S  = int(os.getenv("MASS_FILE_WINDOW_S",  "300"))  # 5 min
CORR_WINDOW_MIN     = int(os.getenv("CORR_WINDOW_MIN",     "30"))   # fenêtre corrélation

# Patterns T1027 — obfuscation dans les noms de processus / chemins
_OBFUSC_PATTERNS = re.compile(
    r'([A-Za-z0-9+/]{40,}={0,2})'           # base64 inline dans un argument
    r'|(\.(ps1|js|vbs)\.(exe|bat|cmd)$)'     # double extension
    r'|(chr\(|frombase64|invoke-expression'   # PowerShell obfuscation classique
    r'|iex\s*\(|\.invoke\()',
    re.IGNORECASE
)
# Répertoires sensibles pour T1083
_DISCOVERY_DIRS = re.compile(
    r'(/etc/|/proc/|/var/log/|C:\\Windows\\System32|HKLM|HKCU|SAM|SECURITY)',
    re.IGNORECASE
)
# Volume de création de comptes sur 10 min → T1136
ACCOUNT_CREATE_THRESHOLD = int(os.getenv("ACCOUNT_CREATE_THRESHOLD", "5"))


# ────────────────────────────────────────────────────────────────────────────
# Règles de détection individuelles
# ────────────────────────────────────────────────────────────────────────────
def detect(ev: dict):
    """Retourne (tactique, technique_id, technique_nom, détail[, ioc]) ou None.

    Le 5e élément est facultatif : c'est l'indicateur de compromission
    exploitable par une action de réponse (aujourd'hui l'IP distante d'un canal
    C2). Sans lui, un blocage au pare-feu n'a aucune cible et l'action de
    réponse ne peut pas être proposée honnêtement.
    """
    d = ev.get("data", {})
    k = ev["kind"]

    if k == "process":
        name = (d.get("name") or "").lower()
        exe  = (d.get("exe")  or "")
        args = " ".join(d.get("args") or [])

        if name in SUSPICIOUS_PROCS:
            return ("Execution", "T1059", "Command and Scripting Interpreter",
                    f"processus {name}")
        if exe.startswith("/tmp") or ("temp" in exe.lower() and exe):
            # T1059 via répertoire temporaire — mais on distingue maintenant T1027
            if _OBFUSC_PATTERNS.search(exe) or _OBFUSC_PATTERNS.search(args):
                return ("Defense Evasion", "T1027", "Obfuscated Files or Information",
                        f"exécution obfusquée depuis répertoire temporaire : {exe[:80]}")
            return ("Execution", "T1059", "Exécution depuis répertoire temporaire", exe)

        # T1027 — obfuscation dans les arguments
        if _OBFUSC_PATTERNS.search(args):
            return ("Defense Evasion", "T1027", "Obfuscated Files or Information",
                    f"arguments obfusqués : {args[:80]}")

        # T1136 — création de compte (commandes typiques)
        if name in ("net.exe", "useradd", "adduser", "dsadd") or \
           ("net" in name and "user" in args.lower() and "/add" in args.lower()):
            return ("Persistence", "T1136", "Create Account",
                    f"création de compte : {name} {args[:60]}")

    elif k == "connection":
        remote = d.get("remote", ":")
        ip     = remote.rsplit(":", 1)[0].strip("[]")
        port   = remote.rsplit(":", 1)[-1]
        if port in C2_PORTS or ip in TI_IPS:
            # L'IP est remontée telle quelle, pas seulement noyée dans le texte :
            # c'est elle que le pare-feu devra bloquer.
            return ("Command and Control", "T1071", "Application Layer Protocol",
                    f"connexion vers {remote}", ip)

    elif k == "file_change":
        path = (d.get("path") or "").lower()
        if any(s in path for s in SENSITIVE_PATHS):
            return ("Collection", "T1005", "Data from Local System", d.get("path"))
        if "download" in path and path.lower().endswith(DOWNLOAD_EXT):
            return ("Initial Access", "T1204", "User Execution: Malicious File", d.get("path"))
        # T1083 — accès fichier dans répertoire d'énumération
        if _DISCOVERY_DIRS.search(d.get("path") or ""):
            return ("Discovery", "T1083", "File and Directory Discovery", d.get("path"))

    return None


# ────────────────────────────────────────────────────────────────────────────
# CORRECTIF O(N) — detect_mass_file_change
# ────────────────────────────────────────────────────────────────────────────
def detect_mass_file_change(events: list):
    """
    Détecte une modification massive de fichiers dans une fenêtre glissante.

    Complexité : O(N) avec deux pointeurs (left/right).
    Version précédente : O(N²) — pour chaque événement i, on re-scannait
    tous les événements pour trouver ceux dans la fenêtre de i.
    Correction : on avance `left` uniquement vers l'avant, ce qui garantit
    que chaque événement n'est visité qu'une seule fois.
    """
    files = sorted(
        [e for e in events if e["kind"] == "file_change"],
        key=lambda e: e["time"]
    )
    if len(files) < MASS_FILE_THRESHOLD:
        return None

    left = 0
    for right in range(len(files)):
        t_right = datetime.fromisoformat(files[right]["time"])
        # Avancer left tant que la fenêtre dépasse MASS_FILE_WINDOW_S
        while (t_right - datetime.fromisoformat(files[left]["time"])).total_seconds() > MASS_FILE_WINDOW_S:
            left += 1
        count = right - left + 1
        if count >= MASS_FILE_THRESHOLD:
            ts_seuil = files[right]["time"]
            return ("Impact", "T1486", "Data Encrypted for Impact",
                    f"{count} fichiers modifiés en moins de {MASS_FILE_WINDOW_S // 60} min",
                    ts_seuil)
    return None


# ────────────────────────────────────────────────────────────────────────────
# Détection de création de comptes en masse — T1136
# ────────────────────────────────────────────────────────────────────────────
def detect_mass_account_creation(events: list):
    """
    Détecte une création anormale de comptes sur une fenêtre de 10 min.
    Utilise également un compteur glissant O(N).
    """
    creates = sorted(
        [e for e in events
         if e["kind"] == "process"
         and detect(e) is not None
         and detect(e)[1] == "T1136"],
        key=lambda e: e["time"]
    )
    if len(creates) < ACCOUNT_CREATE_THRESHOLD:
        return None
    left = 0
    for right in range(len(creates)):
        t_right = datetime.fromisoformat(creates[right]["time"])
        while (t_right - datetime.fromisoformat(creates[left]["time"])).total_seconds() > 600:
            left += 1
        if right - left + 1 >= ACCOUNT_CREATE_THRESHOLD:
            return ("Persistence", "T1136", "Create Account — mass creation",
                    f"{right - left + 1} comptes créés en 10 min",
                    creates[right]["time"])
    return None


# ────────────────────────────────────────────────────────────────────────────
# Corrélation principale
# ────────────────────────────────────────────────────────────────────────────
def correlate(events: list) -> list:
    """Regroupe par hôte, applique les règles, reconstitue les chaînes d'attaque."""
    by_host: dict = defaultdict(list)
    for ev in events:
        by_host[ev["host"]].append(ev)

    incidents = []
    corr_window = timedelta(minutes=CORR_WINDOW_MIN)

    for host, evs in by_host.items():
        # Chaque détection est normalisée à 6 champs :
        # (horodatage, tactique, technique_id, technique_nom, détail, ioc|None)
        dets = []

        def _ajouter(ts, hit):
            tactic, tid, tname, detail = hit[:4]
            ioc = hit[4] if len(hit) > 4 else None
            dets.append((ts, tactic, tid, tname, detail, ioc))

        for ev in sorted(evs, key=lambda e: e["time"]):
            hit = detect(ev)
            if hit:
                _ajouter(ev["time"], hit)

        # Règles volumétriques (ne dépendent pas d'un seul événement)
        mass_file = detect_mass_file_change(evs)
        if mass_file:
            tactic, tid, tname, detail, ts = mass_file
            _ajouter(ts, (tactic, tid, tname, detail))

        mass_account = detect_mass_account_creation(evs)
        if mass_account:
            tactic, tid, tname, detail, ts = mass_account
            _ajouter(ts, (tactic, tid, tname, detail))

        if not dets:
            continue

        dets.sort(key=lambda x: x[0])

        # Filtrer sur la fenêtre de corrélation (configurable)
        t_last = datetime.fromisoformat(dets[-1][0])
        dets = [d for d in dets
                if (t_last - datetime.fromisoformat(d[0])) <= corr_window]

        tactics = list(dict.fromkeys(d[1] for d in dets))  # préserve l'ordre, déduplique
        has = lambda t: t in tactics

        # Critère de levée d'incident
        if not (
            len(tactics) >= 3
            or (has("Execution") and has("Command and Control"))
            or has("Impact")
            or (has("Defense Evasion") and has("Persistence"))  # nouveau : T1027 + T1136
        ):
            continue

        after_hours = any(
            datetime.fromisoformat(d[0]).hour >= 19 or datetime.fromisoformat(d[0]).hour < 6
            for d in dets
        )
        risk = min(100,
                   45 + 12 * len(tactics)
                   + (10 if has("Command and Control") else 0)
                   + (12 if has("Impact") else 0)
                   + (8  if has("Defense Evasion") else 0)
                   + (6  if after_hours else 0))

        itype = (
            "Ransomware"         if has("Impact")                       else
            "Fonctionnaire fantôme" if has("Persistence") and has("Defense Evasion") else
            "Anomalie réseau / C2"  if has("Command and Control")      else
            "Compromission probable"
        )

        chaine = [
            {"heure": d[0][11:19], "tactique": d[1],
             "technique": f"{d[2]} {d[3]}", "detail": d[4], "ioc": d[5]}
            for d in dets
        ]
        # Indicateurs exploitables par une action de réponse, dédupliqués en
        # conservant l'ordre d'apparition dans la chaîne.
        iocs = list(dict.fromkeys(d[5] for d in dets if d[5]))
        incidents.append({
            "type": itype, "entity": host, "entity_kind": "poste", "risque": risk,
            "source": "Corrélation SIEM v2", "activite_hors_heures": after_hours,
            "mitre": sorted({d[2] for d in dets}), "tactiques": tactics, "chaine": chaine,
            "iocs": iocs,
        })
    return incidents


# ────────────────────────────────────────────────────────────────────────────
# Point d'entrée + mesure de performance
# ────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="NEXUS SOC — Corrélation SIEM v2")
    ap.add_argument("--out",      default="./out_lot2")
    ap.add_argument("--benchmark", action="store_true",
                    help="Mesurer le gain O(N²)→O(N) sur detect_mass_file_change")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    if args.benchmark:
        _run_benchmark()
        return

    if generate is None:
        print("telemetry_gen.py introuvable — utilisez : python correlation_engine_v2.py < events.json")
        return

    events = generate()
    t0 = time.perf_counter()
    incidents = correlate(events)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"NEXUS SOC v2 — {len(events)} événements → {len(incidents)} incident(s) en {elapsed:.1f} ms\n")
    for inc in incidents:
        print(f"┌─ {inc['type']} · risque {inc['risque']}/100 · {inc['entity']}")
        print(f"│  Tactiques : {' → '.join(inc['tactiques'])}")
        print(f"│  MITRE : {', '.join(inc['mitre'])}")
        for s in inc["chaine"][:6]:
            print(f"│    {s['heure']}  [{s['tactique']:<22}] {s['technique'][:50]}")
        print(f"└─ → SOAR (type « {inc['type']} »)\n")

    json.dump(incidents, open(f"{args.out}/correlated_incidents_v2.json", "w"),
              ensure_ascii=False, indent=2)
    print(f"Résultats écrits dans {args.out}/correlated_incidents_v2.json")


def _run_benchmark():
    """Compare la performance O(N²) vs O(N) sur detect_mass_file_change."""
    import random
    print("Benchmark detect_mass_file_change : O(N²) vs O(N)\n")

    def make_events(n):
        base = datetime(2026, 5, 28, 9, 0, 0)
        return [{"kind": "file_change", "time": (base + timedelta(seconds=i*2)).isoformat(),
                 "data": {"path": f"/home/user/doc_{i}.xlsx"}}
                for i in range(n)]

    def detect_v1_slow(events):
        """Version O(N²) originale."""
        files = sorted([e for e in events if e["kind"] == "file_change"], key=lambda e: e["time"])
        for i, e in enumerate(files):
            t0 = datetime.fromisoformat(e["time"])
            window = [f for f in files if 0 <= (datetime.fromisoformat(f["time"]) - t0).total_seconds() <= 300]
            if len(window) >= MASS_FILE_THRESHOLD:
                return True
        return False

    sizes = [100, 1_000, 10_000, 50_000]
    print(f"{'N':>8}  {'v1 O(N²) ms':>14}  {'v2 O(N) ms':>12}  {'Gain':>8}")
    print("-" * 50)
    for n in sizes:
        evs = make_events(n)
        t = time.perf_counter()
        detect_v1_slow(evs)
        ms_v1 = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        detect_mass_file_change(evs)
        ms_v2 = (time.perf_counter() - t) * 1000

        gain = f"{ms_v1/ms_v2:.0f}×" if ms_v2 > 0 else "∞"
        print(f"{n:>8}  {ms_v1:>14.1f}  {ms_v2:>12.2f}  {gain:>8}")
    print("\n→ La correction O(N) reste stable quelle que soit la taille N.")


if __name__ == "__main__":
    main()
