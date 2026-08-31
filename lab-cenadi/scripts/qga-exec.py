#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exécute une commande dans une machine du lab par l'agent invité QEMU.

    python3 lab-cenadi/scripts/qga-exec.py KaliPrime "ip -4 -o addr show"

Le canal virtio-serial passe par l'hyperviseur : aucun identifiant, aucun port
réseau. C'est la seule voie qui reste ouverte quand la machine est en
quarantaine — et c'est précisément ce qu'on veut pour constater l'effet d'une
mise en quarantaine sans en dépendre.

Le code de sortie du programme distant devient celui de cet outil, afin que la
recette puisse conclure sur un code plutôt que sur du texte : une sortie lue de
travers a déjà fait conclure l'inverse de la réalité dans ce projet.
"""
import base64
import json
import subprocess
import sys
import time

DELAI = 120


def qga(vm: str, charge: dict):
    r = subprocess.run(
        ["virsh", "-c", "qemu:///system", "qemu-agent-command", vm,
         json.dumps(charge)],
        capture_output=True, text=True, timeout=40)
    if r.returncode:
        raise SystemExit(f"agent invité injoignable sur {vm} : {r.stderr.strip()}")
    return json.loads(r.stdout)["return"]


def executer(vm: str, commande: str) -> tuple[int, str, str]:
    pid = qga(vm, {"execute": "guest-exec",
                   "arguments": {"path": "/bin/sh",
                                 "arg": ["-c", commande],
                                 "capture-output": True}})["pid"]
    for _ in range(DELAI * 2):
        etat = qga(vm, {"execute": "guest-exec-status", "arguments": {"pid": pid}})
        if etat.get("exited"):
            lire = lambda c: (base64.b64decode(etat[c]).decode("utf-8", "replace")
                              if etat.get(c) else "")
            return etat.get("exitcode", -1), lire("out-data"), lire("err-data")
        time.sleep(0.5)
    raise SystemExit(f"délai dépassé sur {vm}")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    code, sortie, erreur = executer(sys.argv[1], " ".join(sys.argv[2:]))
    sys.stdout.write(sortie)
    sys.stderr.write(erreur)
    return code


if __name__ == "__main__":
    sys.exit(main())
