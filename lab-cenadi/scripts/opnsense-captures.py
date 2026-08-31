#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture les écrans de l'interface OPNsense, pour la preuve du pilotage.

    OPNSENSE_GUI_PASSWORD=… python3 lab-cenadi/scripts/opnsense-captures.py \
        --sortie 00_Documents/figures/preuves \
        --page tableau-de-bord=/ui/core/dashboard

Pourquoi un pilote écrit à la main
----------------------------------
L'interface d'OPNsense est derrière une authentification par formulaire : une
capture faite sans session ne montrerait que l'écran de connexion. Il faut donc
un navigateur piloté. Ni Playwright ni Selenium ne sont installés, et les
installer ferait entrer une dépendance externe dans un projet qui revendique de
n'en avoir aucune au moment de l'exécution.

Chrome expose nativement le protocole CDP sur une prise WebSocket. Ce fichier
en implémente le strict nécessaire — poignée de main, trames masquées,
longueurs 16 et 64 bits — avec la seule bibliothèque standard. Une centaine de
lignes contre une dépendance : le compromis est vite tranché.

Le mot de passe vient de l'environnement, jamais d'un argument : la table des
processus est lisible par tous les utilisateurs de la machine.
"""
import argparse
import base64
import http.client
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

CHROME = shutil.which("google-chrome") or shutil.which("chromium")
PORT_CDP = int(os.environ.get("CDP_PORT", "9222"))
BASE = os.environ.get("OPNSENSE_GUI_URL", "https://10.50.0.1")
UTILISATEUR = os.environ.get("OPNSENSE_GUI_USER", "root")
MOTDEPASSE = os.environ.get("OPNSENSE_GUI_PASSWORD", "")


# ── WebSocket minimal ───────────────────────────────────────────────────────
class Prise:
    """Client WebSocket réduit à ce que CDP demande : du texte, dans les deux
    sens, sur une connexion locale et de confiance."""

    def __init__(self, url: str):
        _, reste = url.split("://", 1)
        hote_port, chemin = reste.split("/", 1)
        hote, port = hote_port.split(":")
        self.chemin = "/" + chemin
        self.s = socket.create_connection((hote, int(port)), timeout=60)
        cle = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(
            f"GET {self.chemin} HTTP/1.1\r\n"
            f"Host: {hote_port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {cle}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            .encode()
        )
        entete = b""
        while b"\r\n\r\n" not in entete:
            entete += self.s.recv(1)
        if b"101" not in entete.split(b"\r\n")[0]:
            raise RuntimeError(f"poignée de main refusée : {entete[:120]!r}")
        self.reste = b""

    def _lire(self, n: int) -> bytes:
        while len(self.reste) < n:
            morceau = self.s.recv(65536)
            if not morceau:
                raise RuntimeError("connexion fermée par le navigateur")
            self.reste += morceau
        sortie, self.reste = self.reste[:n], self.reste[n:]
        return sortie

    def envoyer(self, texte: str) -> None:
        charge = texte.encode()
        n = len(charge)
        entete = b"\x81"
        if n < 126:
            entete += bytes([0x80 | n])
        elif n < 65536:
            entete += b"\xfe" + struct.pack(">H", n)
        else:
            entete += b"\xff" + struct.pack(">Q", n)
        masque = os.urandom(4)
        masquee = bytes(o ^ masque[i % 4] for i, o in enumerate(charge))
        self.s.sendall(entete + masque + masquee)

    def recevoir(self) -> str:
        while True:
            o1, o2 = self._lire(2)
            code = o1 & 0x0F
            n = o2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._lire(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._lire(8))[0]
            charge = self._lire(n)
            if code == 0x8:                       # fermeture
                raise RuntimeError("le navigateur a fermé la session")
            if code == 0x9:                       # ping → pong
                self.s.sendall(b"\x8a" + bytes([0x80 | len(charge)])
                               + b"\x00\x00\x00\x00" + charge)
                continue
            if code in (0x1, 0x0):
                return charge.decode("utf-8", "replace")


class Navigateur:
    def __init__(self, prise: Prise):
        self.p = prise
        self.n = 0

    def appeler(self, methode: str, **params):
        self.n += 1
        self.p.envoyer(json.dumps({"id": self.n, "method": methode,
                                   "params": params}))
        while True:
            msg = json.loads(self.p.recevoir())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{methode} : {msg['error']}")
                return msg.get("result", {})

    def js(self, expression: str):
        r = self.appeler("Runtime.evaluate", expression=expression,
                         returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def aller(self, url: str, attente: float = 3.0) -> None:
        self.appeler("Page.navigate", url=url)
        time.sleep(attente)

    def capturer(self, chemin: str) -> int:
        # Pleine hauteur : une capture tronquée ne prouve que la moitié.
        m = self.appeler("Page.getLayoutMetrics")
        h = min(int(m["cssContentSize"]["height"]), 4000)
        self.appeler("Emulation.setDeviceMetricsOverride", width=1600,
                     height=h, deviceScaleFactor=1, mobile=False)
        time.sleep(0.4)
        r = self.appeler("Page.captureScreenshot", format="png")
        octets = base64.b64decode(r["data"])
        open(chemin, "wb").write(octets)
        self.appeler("Emulation.clearDeviceMetricsOverride")
        return len(octets)


# ── Mise en route ───────────────────────────────────────────────────────────
def demarrer_chrome(profil: str) -> subprocess.Popen:
    if not CHROME:
        raise SystemExit("ni google-chrome ni chromium sur cette machine")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={PORT_CDP}",
         "--ignore-certificate-errors",      # l'appliance signe elle-même
         "--no-first-run", "--no-default-browser-check",
         "--disable-gpu", "--hide-scrollbars",
         f"--user-data-dir={profil}", "--window-size=1600,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT_CDP}/json/version", timeout=1):
                return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("Chrome n'a pas ouvert son port de pilotage")


def ouvrir_onglet() -> Navigateur:
    c = http.client.HTTPConnection("127.0.0.1", PORT_CDP, timeout=10)
    c.request("PUT", "/json/new?about:blank")
    cible = json.loads(c.getresponse().read())
    nav = Navigateur(Prise(cible["webSocketDebuggerUrl"]))
    nav.appeler("Page.enable")
    nav.appeler("Runtime.enable")
    return nav


def se_connecter(nav: Navigateur) -> None:
    """Remplit le formulaire d'ouverture de session et le soumet."""
    nav.aller(f"{BASE}/", 4)
    if not nav.js("!!document.querySelector('input[name=usernamefld]')"):
        return                                    # session déjà ouverte
    # On CLIQUE le bouton, on n'appelle pas form.submit() : la soumission par
    # script n'envoie jamais le couple nom/valeur du bouton, or index.php
    # n'entre dans la vérification que si « login » est présent. Sans lui, la
    # page revient avec un message d'échec sans qu'aucune authentification
    # n'ait été tentée — et le journal d'audit reste muet, ce qui égare.
    nav.js(
        "(() => {"
        f"  document.querySelector('input[name=usernamefld]').value = {json.dumps(UTILISATEUR)};"
        f"  document.querySelector('input[name=passwordfld]').value = {json.dumps(MOTDEPASSE)};"
        "  document.querySelector('button[name=login]').click(); return true; })()"
    )
    # On ne peut pas conclure de la présence du champ mot de passe : les pages
    # d'OPNsense embarquent un formulaire de ré-authentification masqué, prêt
    # pour l'expiration de session. Le marqueur fiable est le lien de sortie,
    # que seule une session ouverte affiche.
    for _ in range(20):
        time.sleep(1)
        if nav.js("!!document.querySelector('a[href*=\"logout\"]')"):
            return
    raise SystemExit("session refusée — vérifier OPNSENSE_GUI_PASSWORD")


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--sortie", required=True)
    a.add_argument("--page", action="append", default=[],
                   metavar="nom=/chemin", help="peut être répété")
    a.add_argument("--prepare", action="append", default=[],
                   metavar="nom=JS",
                   help="expression évaluée sur la page avant la capture ; "
                        "sert à choisir une entrée de liste déroulante, à "
                        "poser un filtre, à déplier une section")
    a.add_argument("--attente", type=float, default=4.0)
    args = a.parse_args()

    if not MOTDEPASSE:
        raise SystemExit("OPNSENSE_GUI_PASSWORD n'est pas dans l'environnement")
    os.makedirs(args.sortie, exist_ok=True)

    profil = tempfile.mkdtemp(prefix="chrome-opnsense-")
    proc = demarrer_chrome(profil)
    try:
        nav = ouvrir_onglet()
        se_connecter(nav)
        preparations = dict(p.split("=", 1) for p in args.prepare)
        for entree in args.page:
            nom, chemin = entree.split("=", 1)
            nav.aller(f"{BASE}{chemin}", args.attente)
            if nom in preparations:
                retour = nav.js(preparations[nom])
                print(f"    préparation {nom} → {retour}")
                time.sleep(3)
            cible = os.path.join(args.sortie, f"{nom}.png")
            taille = nav.capturer(cible)
            print(f"  ✓ {nom:<34} {taille // 1024:>5} Kio  {chemin}")
    finally:
        proc.terminate()
        shutil.rmtree(profil, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
