# -*- coding: utf-8 -*-
"""Pilote de navigateur par le protocole CDP, en bibliothèque standard seule.

POURQUOI CE MODULE EXISTE
-------------------------
Les quatre interfaces du dispositif — OPNsense, DFIR-IRIS, Mattermost et la
console NEXUS — sont toutes derrière une authentification par formulaire. Une
capture prise sans session ne montrerait que l'écran de connexion.

Ni Playwright ni Selenium ne sont installés, et les installer ferait entrer une
dépendance externe dans un projet qui revendique de n'en avoir aucune au moment
de l'exécution. Chrome expose nativement CDP sur une prise WebSocket : ce
fichier en implémente le strict nécessaire — poignée de main, trames masquées,
longueurs 16 et 64 bits. Une centaine de lignes contre une dépendance.

LES MOTS DE PASSE VIENNENT DE L'ENVIRONNEMENT
---------------------------------------------
Jamais d'un argument : la table des processus est lisible par tous les
utilisateurs de la machine.
"""
from __future__ import annotations

import base64
import http.client
import json
import os
import shutil
import socket
import struct
import subprocess
import time
import urllib.request

CHROME = shutil.which("google-chrome") or shutil.which("chromium")


# ── WebSocket minimal ───────────────────────────────────────────────────────
class Prise:
    """Client WebSocket réduit à ce que CDP demande : du texte, dans les deux
    sens, sur une connexion locale et de confiance."""

    def __init__(self, url: str):
        _, reste = url.split("://", 1)
        hote_port, chemin = reste.split("/", 1)
        hote, port = hote_port.split(":")
        self.s = socket.create_connection((hote, int(port)), timeout=90)
        cle = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(
            f"GET /{chemin} HTTP/1.1\r\n"
            f"Host: {hote_port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {cle}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            .encode())
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
        self.s.sendall(entete + masque
                       + bytes(o ^ masque[i % 4] for i, o in enumerate(charge)))

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
            if code == 0x8:
                raise RuntimeError("le navigateur a fermé la session")
            if code == 0x9:
                self.s.sendall(b"\x8a" + bytes([0x80 | len(charge)])
                               + b"\x00\x00\x00\x00" + charge)
                continue
            if code in (0x1, 0x0):
                return charge.decode("utf-8", "replace")


class Navigateur:
    """Le peu de CDP dont on a besoin : naviguer, évaluer, capturer."""

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

    def attendre(self, selecteur: str, secondes: float = 25) -> bool:
        """Attend qu'un élément paraisse. Renvoie False plutôt que de lever :
        l'appelant décide si l'absence est une erreur."""
        fin = time.time() + secondes
        while time.time() < fin:
            if self.js(f"!!document.querySelector({json.dumps(selecteur)})"):
                return True
            time.sleep(0.5)
        return False

    def capturer(self, chemin: str, largeur: int = 1600,
                 hauteur_max: int = 4200) -> int:
        # Pleine hauteur : une capture tronquée ne prouve que la moitié.
        m = self.appeler("Page.getLayoutMetrics")
        h = min(int(m["cssContentSize"]["height"]), hauteur_max)
        self.appeler("Emulation.setDeviceMetricsOverride", width=largeur,
                     height=h, deviceScaleFactor=1, mobile=False)
        time.sleep(0.5)
        r = self.appeler("Page.captureScreenshot", format="png")
        octets = base64.b64decode(r["data"])
        open(chemin, "wb").write(octets)
        self.appeler("Emulation.clearDeviceMetricsOverride")
        return len(octets)


# ── Mise en route de Chrome ─────────────────────────────────────────────────
def demarrer_chrome(profil: str, port: int = 9222,
                    fenetre: str = "1600,1000") -> subprocess.Popen:
    if not CHROME:
        raise SystemExit("ni google-chrome ni chromium sur cette machine")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={port}",
         "--ignore-certificate-errors",      # les appliances signent elles-mêmes
         "--no-first-run", "--no-default-browser-check",
         "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
         f"--user-data-dir={profil}", f"--window-size={fenetre}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(80):
        try:
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version", timeout=1):
                return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("Chrome n'a pas ouvert son port de pilotage")


def ouvrir_onglet(port: int = 9222) -> Navigateur:
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    c.request("PUT", "/json/new?about:blank")
    cible = json.loads(c.getresponse().read())
    nav = Navigateur(Prise(cible["webSocketDebuggerUrl"]))
    nav.appeler("Page.enable")
    nav.appeler("Runtime.enable")
    return nav


# ── Recettes de connexion, une par interface ────────────────────────────────
# Chaque interface a ses propres sélecteurs. Les rassembler ici plutôt que de
# les répandre dans les scripts évite qu'une capture parte silencieusement sur
# un écran de connexion en croyant montrer un tableau de bord.
#
# `pret` est le marqueur d'une session RÉELLEMENT ouverte. On ne se fie jamais à
# l'absence du champ mot de passe : les pages d'OPNsense embarquent un
# formulaire de ré-authentification masqué, prêt pour l'expiration de session.
SITES = {
    "opnsense": {
        "connexion": "/",
        "utilisateur": "input[name=usernamefld]",
        "motdepasse": "input[name=passwordfld]",
        # CLIQUER le bouton : form.submit() n'envoie pas son couple nom/valeur,
        # et index.php n'entre dans la vérification que si « login » est là.
        "bouton": "button[name=login]",
        "pret": 'a[href*="logout"]',
    },
    "iris": {
        "connexion": "/login",
        "utilisateur": "#username",
        "motdepasse": "#password",
        "bouton": "button[type=submit]",
        "pret": '#user_menu_dropdown, a[href*="logout"], #dashboard',
    },
    "mattermost": {
        "connexion": "/login",
        "utilisateur": "#input_loginId",
        "motdepasse": "#input_password-input",
        "bouton": "#saveSetting, button[type=submit]",
        "pret": "#channel_view, .app__content, #sidebarItem_town-square",
        # Application React : les champs n'existent qu'après rendu.
        "attente_formulaire": 20,
        # Mattermost interpose un écran « application de bureau ou navigateur »
        # avant le formulaire. Sans ce clic, on cherche des champs de connexion
        # sur une page qui n'en contient aucun, et l'on conclut à tort que les
        # identifiants sont mauvais.
        "prealable": (
            "(() => { const b = [...document.querySelectorAll('a,button')]"
            "  .find(x => /view in browser|continuer dans le navigateur/i"
            "    .test(x.textContent || ''));"
            "  if (b) { b.click(); return 'écran de choix passé'; }"
            "  return 'aucun écran de choix'; })()"),
    },
    "nexus": {
        "connexion": "/app/login.html",
        "utilisateur": "#email",
        "motdepasse": "#password",
        "bouton": "#submit",
        # « main » existe AUSSI sur la page de connexion : le pilote croyait la
        # session ouverte et capturait l'écran de login. Le marqueur doit être
        # propre à la console — la navigation latérale n'existe qu'une fois
        # authentifié.
        "pret": "button[data-go], .nav-item[data-go]",
    },
}


def se_connecter(nav: Navigateur, site: str, base: str,
                 utilisateur: str, motdepasse: str) -> None:
    """Ouvre une session sur l'une des interfaces connues."""
    recette = SITES[site]
    nav.aller(base.rstrip("/") + recette["connexion"], 4)

    if recette.get("prealable"):
        retour = nav.js(recette["prealable"])
        if retour and "passé" in str(retour):
            time.sleep(4)

    if nav.attendre(recette["pret"], 3):
        return                                    # session déjà ouverte

    if not nav.attendre(recette["utilisateur"],
                        recette.get("attente_formulaire", 8)):
        raise SystemExit(f"[{site}] formulaire de connexion introuvable")

    nav.js(
        "(() => {"
        f"  const u = document.querySelector({json.dumps(recette['utilisateur'])});"
        f"  const p = document.querySelector({json.dumps(recette['motdepasse'])});"
        # Les cadriciels réactifs ignorent une écriture directe de `value` : il
        # faut passer par le setter natif puis déclencher « input », sinon le
        # champ paraît rempli à l'écran et vide pour l'application.
        "  const poser = (el, v) => {"
        "    const proto = Object.getPrototypeOf(el);"
        "    const set = Object.getOwnPropertyDescriptor(proto, 'value');"
        "    if (set && set.set) set.set.call(el, v); else el.value = v;"
        "    el.dispatchEvent(new Event('input', {bubbles: true}));"
        "    el.dispatchEvent(new Event('change', {bubbles: true}));"
        "  };"
        f"  poser(u, {json.dumps(utilisateur)}); poser(p, {json.dumps(motdepasse)});"
        f"  const b = document.querySelector({json.dumps(recette['bouton'])});"
        "  if (b) b.click(); else u.form && u.form.requestSubmit();"
        "  return true; })()")

    if not nav.attendre(recette["pret"], 30):
        raise SystemExit(f"[{site}] session refusée — vérifier les identifiants")
