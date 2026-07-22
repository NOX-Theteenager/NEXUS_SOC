#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEXUS SOC — Collecteur de télémétrie RÉELLE (agent hôte)
=========================================================
Contrairement aux scripts de démonstration qui émettent du JSON fabriqué, ce
collecteur ne produit QUE des valeurs mesurées sur la machine :

  • Modèle 1 (réseau)  : compteurs TCP du noyau lus via `ss -tin`
      (bytes_sent / bytes_received / segs_out / segs_in / rtt / durée du flux)
  • Modèle 2 (UEBA)    : activité réellement observable sur l'hôte
      (sessions ouvertes, actions hors heures ouvrables, comptes créés,
       volume sortant, accès aux fichiers sensibles)

HONNÊTETÉ DES DONNÉES — principe directeur
------------------------------------------
Les features du Modèle 2 qui décrivent une activité APPLICATIVE métier
(nb_transactions, montant_total_modifie, nb_modifs_montant) n'ont AUCUNE source
réelle sur un hôte Linux : elles proviennent des journaux d'audit de SIGIPES /
ANTILOPE. Elles sont donc laissées à 0 — c'est une absence de mesure, pas une
valeur inventée. Elles se rempliront le jour où l'on branche les vrais journaux.

Usage
-----
    # 1. Enrôler l'agent (une seule fois) — crée le couple token/HMAC en base
    python3 nexus_collector.py --enroll --hostname "$(hostname)"

    # 2. Collecter en continu (toutes les 30 s par défaut)
    python3 nexus_collector.py --loop

    # Envoi unique (test)
    python3 nexus_collector.py --once
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

SOC_URL   = os.getenv("SOC_URL", "http://127.0.0.1:8000")
CONF_DIR  = os.getenv("NEXUS_AGENT_DIR", os.path.expanduser("~/.nexus-agent"))
CONF_FILE = os.path.join(CONF_DIR, "config.json")

HEURE_DEBUT_BUREAU, HEURE_FIN_BUREAU = 8, 18
FICHIERS_SENSIBLES = ["/etc/shadow", "/etc/passwd", "/etc/sudoers", "/etc/gshadow"]


# --------------------------------------------------------------------------- #
# Configuration locale
# --------------------------------------------------------------------------- #
def charger_conf():
    if not os.path.exists(CONF_FILE):
        sys.exit(f"✗ Agent non enrôlé. Lancez d'abord : {sys.argv[0]} --enroll")
    with open(CONF_FILE) as f:
        return json.load(f)


def sauver_conf(conf):
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(CONF_FILE, "w") as f:
        json.dump(conf, f, indent=2)
    os.chmod(CONF_FILE, 0o600)


def _post(path, payload, token=None):
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(SOC_URL + path, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


# --------------------------------------------------------------------------- #
# Enrôlement : obtient un vrai Bearer + une vraie clé HMAC depuis l'API
# --------------------------------------------------------------------------- #
def enroler(hostname, email, mot_de_passe, perimetre=None):
    jwt = _post("/auth/token", {"email": email, "password": mot_de_passe})["access_token"]

    req = urllib.request.Request(f"{SOC_URL}/admin/tenants",
                                 headers={"Authorization": f"Bearer {jwt}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        perimetres = json.loads(r.read().decode())
    if not perimetres:
        sys.exit("✗ Aucun périmètre supervisé en base.")

    cible = None
    if perimetre:
        cible = next((p for p in perimetres if p["nom"].lower() == perimetre.lower()), None)
        if not cible:
            sys.exit(f"✗ Périmètre '{perimetre}' introuvable. Disponibles : "
                     + ", ".join(p["nom"] for p in perimetres))
    else:
        cible = perimetres[0]

    # Token longue durée, réutilisable : un collecteur continu émet en boucle
    # (one_time invaliderait le jeton dès le premier lot envoyé).
    prov = _post("/provision/token", {
        "tenant_id":        str(cible["id"]),
        "hostname":         hostname,
        "os":               "linux",
        "expires_in_hours": 168,
        "one_time":         False,
        "bind_hostname":    False,
    }, token=jwt)

    conf = {
        "soc_url":   SOC_URL,
        "agent_id":  prov.get("agent_id") or prov.get("id"),
        "tenant_id": str(cible["id"]),
        "perimetre": cible["nom"],
        "bearer":    prov.get("bearer_token") or prov.get("token"),
        "hmac_key":  prov.get("hmac_key"),
        "hostname":  hostname,
    }
    if not conf["bearer"] or not conf["hmac_key"]:
        sys.exit(f"✗ Réponse de provisioning inattendue : {prov}")
    sauver_conf(conf)
    print(f"✓ Agent enrôlé sur le périmètre « {cible['nom']} »  (agent_id={conf['agent_id']})")
    print(f"  Configuration : {CONF_FILE}")


# --------------------------------------------------------------------------- #
# MESURES RÉELLES — Modèle 1 : flux réseau (compteurs TCP du noyau)
# --------------------------------------------------------------------------- #
INTERVALLE_ECHANTILLON_S = 2.0   # écart entre les deux relevés de compteurs


def _ss_flux():
    """
    Relevé instantané des flux TCP établis avec leurs compteurs noyau réels.
    Indexé par (adresse:port distant) afin de pouvoir calculer des différences
    entre deux relevés successifs.
    """
    try:
        out = subprocess.run(["ss", "-tin"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return {}
    flux, cle = {}, None
    for ligne in out.splitlines():
        m = re.match(r"^\S+\s+\d+\s+\d+\s+(\S+)\s+(\S+)", ligne)
        if m and ":" in m.group(2):
            pair = m.group(2)
            port = pair.rsplit(":", 1)[-1]
            cle = pair
            flux[cle] = {"port": int(port) if port.isdigit() else 0}
        elif cle is not None and ligne.strip():
            def num(c, defaut=0.0):
                mm = re.search(rf"\b{c}:(\d+(?:\.\d+)?)", ligne)
                return float(mm.group(1)) if mm else defaut
            flux[cle].update({
                "bytes_sent":     num("bytes_sent"),
                "bytes_received": num("bytes_received"),
                "segs_out":       num("segs_out"),
                "segs_in":        num("segs_in"),
            })
            cle = None
    return {k: v for k, v in flux.items() if "bytes_sent" in v}


def features_reseau(intervalle=INTERVALLE_ECHANTILLON_S):
    """
    Construit les 12 features du Modèle 1 à partir d'un DÉBIT RÉELLEMENT MESURÉ.

    Méthode : deux relevés des compteurs noyau espacés de `intervalle` secondes.
    On travaille sur la DIFFÉRENCE (octets et segments transmis pendant la
    fenêtre), et non sur les compteurs cumulés depuis l'ouverture du socket —
    sinon les débits seraient faux de plusieurs ordres de grandeur.
    """
    avant = _ss_flux()
    if not avant:
        return None, {}
    time.sleep(intervalle)
    apres = _ss_flux()

    # Flux actifs pendant la fenêtre : on ne garde que ceux ayant réellement bougé
    deltas = []
    for cle, a in apres.items():
        b = avant.get(cle)
        if not b:
            continue
        d_sent = a["bytes_sent"]     - b["bytes_sent"]
        d_recv = a["bytes_received"] - b["bytes_received"]
        d_out  = a["segs_out"]       - b["segs_out"]
        d_in   = a["segs_in"]        - b["segs_in"]
        if d_out + d_in > 0 and d_sent >= 0 and d_recv >= 0:
            deltas.append({"port": a["port"], "sent": d_sent, "recv": d_recv,
                           "out": d_out, "in": d_in})

    if not deltas:
        return None, {"flux_observes": len(apres), "flux_actifs": 0}

    # Flux le plus volumineux de la fenêtre
    f = max(deltas, key=lambda x: x["sent"] + x["recv"])

    duree_s   = intervalle
    duree_us  = duree_s * 1_000_000
    fwd_pkts  = f["out"]
    bwd_pkts  = f["in"]
    tot_pkts  = max(fwd_pkts + bwd_pkts, 1)
    tot_bytes = f["sent"] + f["recv"]

    fwd_len = f["sent"] / fwd_pkts if fwd_pkts else 0.0
    bwd_len = f["recv"] / bwd_pkts if bwd_pkts else 0.0
    tailles = [t for t in (fwd_len, bwd_len) if t > 0] or [0.0]

    feats = {
        "Destination Port":         float(f["port"]),
        "Flow Duration":            duree_us,
        "Total Fwd Packets":        float(fwd_pkts),
        "Total Backward Packets":   float(bwd_pkts),
        "Flow Bytes/s":             tot_bytes / duree_s,
        "Flow Packets/s":           tot_pkts / duree_s,
        "Fwd Packet Length Mean":   fwd_len,
        "Bwd Packet Length Mean":   bwd_len,
        "Flow IAT Mean":            duree_us / tot_pkts,
        "Min Packet Length":        float(min(tailles)),
        "Max Packet Length":        float(max(tailles)),
        "Average Packet Size":      tot_bytes / tot_pkts,
    }
    contexte = {"flux_observes": len(apres), "flux_actifs": len(deltas),
                "port_distant": f["port"], "octets_fenetre": tot_bytes,
                "fenetre_s": duree_s}
    return feats, contexte


# --------------------------------------------------------------------------- #
# MESURES RÉELLES — Modèle 2 : comportement observable sur l'hôte
# --------------------------------------------------------------------------- #
def _cmd(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ""


def features_comportement():
    """
    Features du Modèle 2 mesurées sur l'hôte.
    Les champs applicatifs métier (transactions / montants) restent à 0 :
    ils proviennent des journaux SIGIPES-ANTILOPE, non disponibles ici.
    """
    maintenant = datetime.now()
    hors_bureau = not (HEURE_DEBUT_BUREAU <= maintenant.hour < HEURE_FIN_BUREAU)

    sessions = len([l for l in _cmd(["who"]).splitlines() if l.strip()])

    flux = list(_ss_flux().values())
    nb_connexions = len(flux)
    volume_sortant = sum(f.get("bytes_sent", 0) for f in flux)
    # « export » = flux dont l'envoi cumulé dépasse 1 Mo (transfert sortant notable)
    nb_exports = len([f for f in flux if f.get("bytes_sent", 0) > 1_048_576])

    # Comptes créés : lignes de /etc/passwd avec UID >= 1000 (comptes humains)
    nb_comptes = 0
    try:
        with open("/etc/passwd") as fh:
            for l in fh:
                p = l.split(":")
                if len(p) > 2 and p[2].isdigit() and int(p[2]) >= 1000 and int(p[2]) < 65534:
                    nb_comptes += 1
    except Exception:
        pass

    # Accès récents (< 1 h) à des fichiers système sensibles — mesure réelle
    nb_acces_sensibles = 0
    for chemin in FICHIERS_SENSIBLES:
        try:
            if time.time() - os.stat(chemin).st_atime < 3600:
                nb_acces_sensibles += 1
        except Exception:
            pass

    actions_total = sessions + nb_connexions + nb_exports + nb_acces_sensibles

    feats = {
        "nb_connexions":               float(nb_connexions),
        "nb_actions_hors_heures":      float(actions_total if hors_bureau else 0),
        "nb_transactions":             0.0,   # source applicative absente
        "montant_total_modifie":       0.0,   # source applicative absente
        "nb_modifs_montant":           0.0,   # source applicative absente
        "nb_creations_compte":         float(nb_comptes),
        "nb_exports":                  float(nb_exports),
        "volume_donnees_exportees":    float(volume_sortant),
        "nb_acces_dossiers_sensibles": float(nb_acces_sensibles),
        "nb_actions_total":            float(actions_total),
    }
    contexte = {"sessions_ouvertes": sessions, "hors_heures": hors_bureau}
    return feats, contexte


# --------------------------------------------------------------------------- #
# Envoi signé vers /ingest
# --------------------------------------------------------------------------- #
def envoyer(conf, evenements):
    batch = {"agent_id": conf["agent_id"], "tenant_id": conf["tenant_id"],
             "host": conf["hostname"], "events": evenements}
    corps = json.dumps(batch).encode()
    signature = hmac.new(conf["hmac_key"].encode(), corps, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        conf["soc_url"] + "/ingest", data=corps, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {conf['bearer']}",
                 "X-Signature": signature})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"erreur": f"HTTP {e.code}", "detail": e.read().decode()[:200]}
    except Exception as e:
        return {"erreur": str(e)}


def collecter_et_envoyer(conf, verbeux=True):
    evenements = []

    f_res, ctx_res = features_reseau()
    if f_res:
        evenements.append({
            "kind": "network", "features": f_res,
            "entite": conf["hostname"],
            "type": "Anomalie réseau / C2",
            "mitre": "T1071 · C2",
            "contexte": ctx_res,
        })

    f_cmp, ctx_cmp = features_comportement()
    evenements.append({
        "kind": "user-day", "features": f_cmp,
        "entite": f"hote_{conf['hostname']}",
        "type": "Fraude interne",
        "mitre": "T1078 · Credential Access",
        "contexte": ctx_cmp,
    })

    rep = envoyer(conf, evenements)
    if verbeux:
        ts = datetime.now().strftime("%H:%M:%S")
        if "erreur" in rep:
            print(f"[{ts}] ✗ {rep['erreur']} {rep.get('detail','')}")
        else:
            print(f"[{ts}] ✓ {rep.get('recus',0)} évt envoyés · "
                  f"{rep.get('alertes',0)} alerte(s) · "
                  f"flux réseau observés: {ctx_res.get('flux_observes',0)} · "
                  f"sessions: {ctx_cmp.get('sessions_ouvertes',0)}")
    return rep


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description="Collecteur de télémétrie réelle NEXUS SOC")
    ap.add_argument("--enroll", action="store_true", help="enrôler cet hôte comme agent")
    ap.add_argument("--hostname", default=os.uname().nodename)
    ap.add_argument("--email", default="admin@nexussoc.cm")
    ap.add_argument("--password", default="admin")
    ap.add_argument("--perimetre", default=None, help="nom du périmètre supervisé cible")
    ap.add_argument("--once", action="store_true", help="une seule collecte")
    ap.add_argument("--loop", action="store_true", help="collecte en continu")
    ap.add_argument("--interval", type=int, default=30, help="secondes entre deux collectes")
    a = ap.parse_args()

    if a.enroll:
        enroler(a.hostname, a.email, a.password, a.perimetre)
        return

    conf = charger_conf()
    if a.loop:
        print(f"▶ Collecte réelle toutes les {a.interval}s — périmètre « {conf['perimetre']} » "
              f"(Ctrl+C pour arrêter)")
        while True:
            try:
                collecter_et_envoyer(conf)
                time.sleep(a.interval)
            except KeyboardInterrupt:
                print("\n■ Arrêt du collecteur.")
                break
    else:
        collecter_et_envoyer(conf)


if __name__ == "__main__":
    main()
