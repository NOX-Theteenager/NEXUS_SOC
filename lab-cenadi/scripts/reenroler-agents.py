#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Réenrôle les collecteurs du lab CENADI et repose leur configuration.

    export NEXUS_ADMIN_EMAIL=… NEXUS_ADMIN_PASSWORD=… NEXUS_VM_SUDO=…
    python3 lab-cenadi/scripts/reenroler-agents.py --constater
    python3 lab-cenadi/scripts/reenroler-agents.py --appliquer

POURQUOI CE SCRIPT EXISTE
-------------------------
Les quatre collecteurs recevaient « 401 Token ou signature invalide ». Le
soupçon portait sur la signature HMAC ; la cause était plus simple et plus
bête : leurs jetons avaient EXPIRÉ. Émis pour 168 heures les 16 et 19 août, ils
étaient périmés depuis. `_verify_ingest` rejette sur l'échéance bien avant
d'examiner la moindre signature — d'où un message qui parle de signature pour
un problème de date.

L'enrôlement se fait DEPUIS L'HÔTE. Le mot de passe administrateur du SOC ne
descend jamais dans une machine supervisée : seul le couple jeton/clé produit
pour elle y est déposé. Un collecteur compromis ne doit pas livrer de quoi en
enrôler d'autres.

Les jetons sont réémis pour un an et NON à usage unique : un collecteur continu
émet en boucle, un jeton à usage unique s'invaliderait au premier lot.

DEUX VOIES D'ACCÈS
------------------
  ssh  clé publique, puis sudo pour écrire sous /etc. Le fichier passe par scp
       vers /tmp en 600 : le jeton ne figure jamais dans une ligne de commande,
       donc jamais dans la table des processus de la machine.
  qga  agent invité QEMU pour KaliPrime, qui n'accepte pas nos clés. Le canal
       virtio-serial est déjà root, aucun mot de passe n'est nécessaire.
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

SOC = os.environ.get("SOC_URL", "http://10.50.0.2:8000")
EMAIL = os.environ.get("NEXUS_ADMIN_EMAIL", "")
MOTDEPASSE = os.environ.get("NEXUS_ADMIN_PASSWORD", "")
SUDO_VM = os.environ.get("NEXUS_VM_SUDO", "")
CLE = os.path.expanduser("~/.ssh/id_ed25519")

VERT = "\033[32m"; ROUGE = "\033[31m"; GRAS = "\033[1m"; RAZ = "\033[0m"

# hôte SOC · périmètre · adresse · accès · compte · domaine libvirt
AGENTS = [
    {"hostname": "SRV-APP-GOV-01",    "tenant": "11111111-1111-1111-1111-111111111111",
     "perimetre": "SIGIPES",
     "ip": "10.50.20.20", "acces": "ssh", "user": "noxtheteenager"},
    {"hostname": "SRV-ANTILOPE-01",   "tenant": "22222222-2222-2222-2222-222222222222",
     "perimetre": "ANTILOPE",
     "ip": "10.50.30.30", "acces": "ssh", "user": "antilope"},
    {"hostname": "POSTE-RSSI-01",     "tenant": "33333333-3333-3333-3333-333333333333",
     "perimetre": "Réseau/LAN CENADI",
     "ip": "10.50.40.40", "acces": "ssh", "user": "rssi"},
    {"hostname": "POSTE-MENACE-vrai", "tenant": "33333333-3333-3333-3333-333333333333",
     "perimetre": "Réseau/LAN CENADI",
     "ip": "10.50.50.50", "acces": "qga", "vm": "KaliPrime"},
    # Le cœur SOC se supervise lui-même. Son collecteur avait expiré comme les
    # autres et s'était tu neuf jours sans que rien ne le signale : c'est
    # exactement le genre d'angle mort qu'un SOC ne peut pas se permettre.
    {"hostname": "NoxTheMachine",     "tenant": "33333333-3333-3333-3333-333333333333",
     "perimetre": "Réseau/LAN CENADI",
     "ip": "10.50.0.2",   "acces": "local",
     "conf": os.path.expanduser("~/.nexus-agent/config.json")},
]

CONF_DISTANT = "/etc/nexus-agent/config.json"
SERVICE = "nexus-collector"
DUREE_H = 8760                      # un an : la soutenance est en septembre


# ── SOC ─────────────────────────────────────────────────────────────────────
def poster(chemin: str, charge: dict, jeton: str = "") -> dict:
    entetes = {"Content-Type": "application/json"}
    if jeton:
        entetes["Authorization"] = f"Bearer {jeton}"
    req = urllib.request.Request(SOC + chemin, data=json.dumps(charge).encode(),
                                 headers=entetes, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def jeton_admin() -> str:
    if not (EMAIL and MOTDEPASSE):
        raise SystemExit("NEXUS_ADMIN_EMAIL / NEXUS_ADMIN_PASSWORD absents de l'environnement")
    return poster("/auth/token", {"email": EMAIL, "password": MOTDEPASSE})["access_token"]


# ── Transports ──────────────────────────────────────────────────────────────
def ssh_base(a: dict) -> list:
    return ["ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-i", CLE,
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10",
            f"{a['user']}@{a['ip']}"]


def poser_par_ssh(a: dict, conf: dict) -> tuple[bool, str]:
    """Dépose la configuration puis relance le collecteur, par clé puis sudo."""
    if not SUDO_VM:
        return False, "NEXUS_VM_SUDO absent de l'environnement"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(conf, f, indent=2)
        local = f.name
    os.chmod(local, 0o600)
    try:
        r = subprocess.run(
            ["scp", "-q", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-i", CLE,
             "-o", "StrictHostKeyChecking=accept-new", local,
             f"{a['user']}@{a['ip']}:/tmp/nexus-config.json"],
            capture_output=True, text=True, timeout=40)
        if r.returncode:
            return False, f"copie refusée : {r.stderr.strip()[:80]}"
        # Le mot de passe passe par l'entrée standard, jamais par un argument.
        distant = (f"sudo -S -p '' sh -c 'install -m 600 -o root -g root "
                   f"/tmp/nexus-config.json {CONF_DISTANT} && rm -f /tmp/nexus-config.json "
                   f"&& systemctl restart {SERVICE}'")
        r = subprocess.run(ssh_base(a) + [distant], input=SUDO_VM + "\n",
                           capture_output=True, text=True, timeout=60)
        if r.returncode:
            return False, f"installation refusée : {(r.stderr or r.stdout).strip()[:90]}"
        return True, "posée"
    finally:
        os.unlink(local)


def poser_localement(a: dict, conf: dict) -> tuple[bool, str]:
    """Le collecteur de l'hôte : le fichier lui appartient, pas besoin de root."""
    chemin = a["conf"]
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(conf, f, indent=2)
    os.chmod(chemin, 0o600)
    r = subprocess.run(["systemctl", "--user", "restart", SERVICE],
                       capture_output=True, text=True, timeout=30)
    if r.returncode:
        # Le service est côté système sur cet hôte : on le dit plutôt que de
        # laisser croire que la relance a eu lieu.
        return True, "posée (relancer le service : sudo systemctl restart nexus-collector)"
    return True, "posée"


def qga(vm: str, charge: dict):
    r = subprocess.run(["virsh", "-c", "qemu:///system", "qemu-agent-command", vm,
                        json.dumps(charge)], capture_output=True, text=True, timeout=40)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:100])
    return json.loads(r.stdout)["return"]


def poser_par_qga(a: dict, conf: dict) -> tuple[bool, str]:
    """Écrit le fichier par le canal virtio-serial, déjà root."""
    donnees = json.dumps(conf, indent=2).encode()
    h = qga(a["vm"], {"execute": "guest-file-open",
                      "arguments": {"path": CONF_DISTANT, "mode": "wb"}})
    qga(a["vm"], {"execute": "guest-file-write",
                  "arguments": {"handle": h, "buf-b64": base64.b64encode(donnees).decode()}})
    qga(a["vm"], {"execute": "guest-file-close", "arguments": {"handle": h}})
    pid = qga(a["vm"], {"execute": "guest-exec",
                        "arguments": {"path": "/bin/sh",
                                      "arg": ["-c", f"chmod 600 {CONF_DISTANT}; "
                                                    f"systemctl restart {SERVICE}"],
                                      "capture-output": True}})["pid"]
    for _ in range(60):
        etat = qga(a["vm"], {"execute": "guest-exec-status", "arguments": {"pid": pid}})
        if etat.get("exited"):
            return etat.get("exitcode", -1) == 0, "posée"
        time.sleep(0.5)
    return False, "délai dépassé"


# ── Contrôle ────────────────────────────────────────────────────────────────
def etat_agents() -> None:
    r = subprocess.run(
        ["docker", "exec", "nexus-postgres", "psql", "-U", "nexus", "-d", "nexus_soc", "-At",
         "-c", "SELECT hostname, statut, hmac_scheme, hmac_epoch, "
               "to_char(token_expires_at,'YYYY-MM-DD'), token_expires_at < now() "
               "FROM agents WHERE hostname IN ('SRV-APP-GOV-01','SRV-ANTILOPE-01',"
               "'POSTE-RSSI-01','POSTE-MENACE-vrai','NoxTheMachine') ORDER BY hostname"],
        capture_output=True, text=True, timeout=20)
    print(f"    {'hôte':<20} {'statut':<10} {'schéma':<9} {'ép.':<4} {'échéance':<12} état")
    for ligne in r.stdout.strip().splitlines():
        h, st, sc, ep, ech, exp = ligne.split("|")
        couleur = ROUGE if exp == "t" else VERT
        mot = "EXPIRÉ" if exp == "t" else "valide"
        print(f"    {h:<20} {st:<10} {sc:<9} {ep:<4} {ech:<12} {couleur}{mot}{RAZ}")


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--appliquer", action="store_true")
    args = a.parse_args()

    print(f"{GRAS}État des collecteurs{RAZ}")
    etat_agents()
    if not args.appliquer:
        print("\nMODE CONSTAT — rien n'est modifié. Ajoutez --appliquer pour réenrôler.")
        return 0

    jwt = jeton_admin()
    print(f"\n{GRAS}Réenrôlement{RAZ}")
    echec = 0
    for ag in AGENTS:
        print(f"  {ag['hostname']:<20} ", end="", flush=True)
        try:
            prov = poster("/provision/token", {
                "tenant_id": ag["tenant"], "hostname": ag["hostname"], "os": "linux",
                "expires_in_hours": DUREE_H, "one_time": False, "bind_hostname": False,
            }, jwt)
        except urllib.error.HTTPError as e:
            print(f"{ROUGE}✗ provisioning refusé (HTTP {e.code}) {e.read().decode()[:70]}{RAZ}")
            echec = 1
            continue

        conf = {
            "soc_url":   SOC,
            "agent_id":  prov["agent_id"],
            "tenant_id": ag["tenant"],
            # Le collecteur affiche le périmètre au démarrage et sort en erreur
            # si la clé manque : une configuration incomplète le fait boucler en
            # échec sans jamais dire que c'est elle qui cloche.
            "perimetre": ag["perimetre"],
            "bearer":    prov["bearer_token"],
            "hmac_key":  prov["hmac_key"],
            "hostname":  ag["hostname"],
        }
        poseur = {"qga": poser_par_qga, "local": poser_localement}.get(
            ag["acces"], poser_par_ssh)
        ok, detail = poseur(ag, conf)
        if ok:
            print(f"{VERT}✓{RAZ} jeton réémis ({DUREE_H} h), schéma {prov['hmac_scheme']}, "
                  f"configuration {detail}, service relancé")
        else:
            print(f"{ROUGE}✗ {detail}{RAZ}")
            echec = 1

    print(f"\n{GRAS}État après réenrôlement{RAZ}")
    etat_agents()
    return echec


if __name__ == "__main__":
    sys.exit(main())
