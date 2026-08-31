#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exécute une commande sur OPNsense par SSH, mot de passe fourni au terminal.

    python3 lab-cenadi/scripts/opnsense-console.py "uname -a"
    echo "commande" | python3 lab-cenadi/scripts/opnsense-console.py -

OPNsense n'accepte l'authentification par clé qu'une fois configuré. Pendant
l'installation et la première mise en service, seul le mot de passe fonctionne.
Comme ni sshpass ni expect ne sont installés sur l'hôte, on ouvre un
pseudo-terminal : ssh y voit un vrai terminal et accepte que le mot de passe
lui soit transmis.

Le mot de passe vient de la variable d'environnement OPNSENSE_SSH_PASSWORD,
jamais d'un argument de ligne de commande : les arguments sont visibles de tous
les utilisateurs de la machine dans la table des processus.
"""
import os
import pty
import re
import select
import sys
import time

HOTE = os.environ.get("OPNSENSE_SSH_HOST", "192.168.1.1")
UTILISATEUR = os.environ.get("OPNSENSE_SSH_USER", "root")
MOTDEPASSE = os.environ.get("OPNSENSE_SSH_PASSWORD", "opnsense")
DELAI = float(os.environ.get("OPNSENSE_SSH_TIMEOUT", "60"))

INVITE_MDP = re.compile(rb"(?:[Pp]assword|[Mm]ot de passe)\s*:", re.M)


def executer(commande: str) -> tuple[int, str]:
    """Lance la commande et renvoie (code de sortie, sortie complète)."""
    argv = [
        "ssh", "-tt",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "PreferredAuthentications=password",
        "-o", "PubkeyAuthentication=no",
        "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=10",
        f"{UTILISATEUR}@{HOTE}", commande,
    ]
    pid, fd = pty.fork()
    if pid == 0:                       # processus fils : devient ssh
        os.execvp(argv[0], argv)
        os._exit(127)

    tampon = b""
    mdp_envoye = False
    limite = time.time() + DELAI
    while time.time() < limite:
        pret, _, _ = select.select([fd], [], [], 0.5)
        if pret:
            try:
                morceau = os.read(fd, 65536)
            except OSError:            # le terminal se ferme à la fin de ssh
                break
            if not morceau:
                break
            tampon += morceau
            if not mdp_envoye and INVITE_MDP.search(tampon):
                os.write(fd, MOTDEPASSE.encode() + b"\n")
                mdp_envoye = True
                # On retire l'invite du tampon pour ne pas la relire.
                tampon = INVITE_MDP.split(tampon)[-1]
        else:
            fini, statut = os.waitpid(pid, os.WNOHANG)
            if fini:
                code = os.waitstatus_to_exitcode(statut)
                # Vider ce qui reste dans le tampon du terminal.
                while True:
                    pret, _, _ = select.select([fd], [], [], 0.2)
                    if not pret:
                        break
                    try:
                        reste = os.read(fd, 65536)
                    except OSError:
                        break
                    if not reste:
                        break
                    tampon += reste
                os.close(fd)
                return code, tampon.decode("utf-8", "replace")
    try:
        os.close(fd)
    except OSError:
        pass
    return 124, tampon.decode("utf-8", "replace")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    commande = sys.stdin.read() if sys.argv[1] == "-" else " ".join(sys.argv[1:])
    code, sortie = executer(commande)
    # Le pseudo-terminal produit des retours chariot : on les retire pour que
    # la sortie reste exploitable par un autre programme.
    sys.stdout.write(sortie.replace("\r\n", "\n"))
    return code


if __name__ == "__main__":
    sys.exit(main())
