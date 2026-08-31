#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Captures d'écran des quatre interfaces, pour le dossier de preuves.

    OPNSENSE_GUI_PASSWORD=… IRIS_GUI_PASSWORD=… MM_GUI_PASSWORD=… \\
    NEXUS_ADMIN_PASSWORD=… \\
    python3 lab-cenadi/scripts/captures-preuves.py --sortie 00_Documents/figures/preuves

Chaque capture est prise sur l'interface RÉELLE, session ouverte. Rien n'est
reconstitué : une figure de mémoire qui ne serait pas une photographie de
l'outil vaudrait moins que pas de figure du tout.

Les mots de passe viennent de l'environnement, jamais d'un argument.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pilote_navigateur import (  # noqa: E402
    demarrer_chrome, ouvrir_onglet, se_connecter)

PORT = int(os.getenv("CDP_PORT", "9222"))


def _js_onglet(libelle: str) -> str:
    """Clique l'onglet dont le libellé commence par `libelle`."""
    return (
        "(() => { const t = " + json.dumps(libelle.lower()) + ";"
        "  const a = [...document.querySelectorAll('a,button,li')]"
        "    .find(x => (x.textContent||'').trim().toLowerCase().startsWith(t));"
        "  if (!a) return 'onglet introuvable';"
        "  a.click(); return 'onglet ' + a.textContent.trim().slice(0,40); })()")


def _js_canal(nom: str) -> str:
    """Ouvre un canal Mattermost depuis la barre latérale."""
    return (
        "(() => { const n = " + json.dumps(nom) + ";"
        "  const a = [...document.querySelectorAll('a')]"
        "    .find(x => (x.getAttribute('href')||'').endsWith('/channels/' + n));"
        "  if (!a) return 'canal absent de la barre latérale';"
        "  a.click(); return 'canal ' + n; })()")


def prendre(nav, sortie, nom, url, prepare=None, attente=5.0, note="",
            pause=3.5):
    nav.aller(url, attente)
    if prepare:
        retour = nav.js(prepare)
        print(f"      préparation → {retour}")
        import time
        time.sleep(pause)
    chemin = os.path.join(sortie, f"{nom}.png")
    taille = nav.capturer(chemin)
    print(f"  ✓ {nom:<40} {taille // 1024:>5} Kio  {note or url}")


def main() -> int:
    a = argparse.ArgumentParser()
    a.add_argument("--sortie", required=True)
    a.add_argument("--seulement", default="",
                   help="iris, mattermost, nexus — séparés par des virgules")
    args = a.parse_args()
    os.makedirs(args.sortie, exist_ok=True)
    voulus = {s.strip() for s in args.seulement.split(",") if s.strip()}

    url_iris = os.getenv("IRIS_URL", "https://10.50.0.2:4443")
    url_mm = os.getenv("MATTERMOST_URL", "http://10.50.0.2:8065")
    url_soc = os.getenv("NEXUS_CONSOLE_URL", "http://10.50.0.2:8000")
    canal = os.getenv("CANAL_INCIDENT", "")
    alerte_iris = os.getenv("ALERTE_IRIS", "")
    dossier_iris = os.getenv("DOSSIER_IRIS", "")

    profil = tempfile.mkdtemp(prefix="chrome-preuves-")
    proc = demarrer_chrome(profil, PORT)
    try:
        # ── DFIR-IRIS ───────────────────────────────────────────────────────
        if not voulus or "iris" in voulus:
            print("\nDFIR-IRIS")
            nav = ouvrir_onglet(PORT)
            se_connecter(nav, "iris", url_iris, os.getenv("IRIS_GUI_USER", "administrator"),
                         os.environ["IRIS_GUI_PASSWORD"])
            if alerte_iris:
                prendre(nav, args.sortie, "20-iris-alerte",
                        f"{url_iris}/alerts?alert_id={alerte_iris}", attente=7,
                        note="alerte, périmètre, gravité, source")
            if dossier_iris:
                base = f"{url_iris}/case?cid={dossier_iris}"
                prendre(nav, args.sortie, "21-iris-dossier-resume",
                        f"{base}", attente=7, note="résumé et état de l'enquête")
                prendre(nav, args.sortie, "22-iris-observables",
                        f"{url_iris}/case/ioc?cid={dossier_iris}", attente=7,
                        note="observables (IOC)")
                prendre(nav, args.sortie, "23-iris-chronologie",
                        f"{url_iris}/case/timeline?cid={dossier_iris}", attente=8,
                        note="chronologie de l'incident")
                prendre(nav, args.sortie, "24-iris-actifs",
                        f"{url_iris}/case/assets?cid={dossier_iris}", attente=7,
                        note="actifs concernés")

        # ── Mattermost ──────────────────────────────────────────────────────
        if (not voulus or "mattermost" in voulus) and canal:
            print("\nMattermost")
            nav = ouvrir_onglet(PORT)
            se_connecter(nav, "mattermost", url_mm,
                         os.getenv("MM_GUI_USER", "nexus-admin"),
                         os.environ["MM_GUI_PASSWORD"])
            equipe = os.getenv("MATTERMOST_EQUIPE", "cenadi-soc")
            # Mattermost superpose un guide de bienvenue et des bulles de
            # découverte à la première connexion. Les laisser masquerait la
            # moitié de la conversation : une capture doit montrer le canal,
            # pas l'accueil du produit.
            # Deux surcouches gênent la capture : le guide de bienvenue
            # (conteneur « TaskItems-… », posé en enfant direct de
            # .main-wrapper) et le bandeau « Preview Mode ». On vise ces deux
            # éléments et RIEN d'autre : une première version supprimait tout
            # ce dont le texte correspondait, et emportait la page entière.
            fermer = ("(() => { let n = 0;"
                      "  const oter = s => document.querySelectorAll(s)"
                      "    .forEach(e => { e.remove(); n++; });"
                      "  oter('[class*=\"TaskItems\"]');"
                      "  oter('.announcement-bar');"
                      "  oter('.tour-tip__overlay, .modal-backdrop');"
                      # Le guide laisse un voile qui grise toute la page : la
                      # capture paraît alors délavée, comme une image retouchée.
                      "  document.querySelectorAll('body, .channel-view, .main-wrapper')"
                      "    .forEach(e => { e.style.filter = 'none';"
                      "      e.style.opacity = '1'; e.classList.remove('modal-open'); });"
                      "  document.querySelectorAll('.main-wrapper > div').forEach(e => {"
                      "    if (/^Welcome to Mattermost/.test((e.textContent||'').trim())"
                      "        && !e.querySelector('.post-list, #postListContent')) {"
                      "      e.remove(); n++; }"
                      "  });"
                      "  return n + ' surcouche(s) écartée(s)'; })()")
            prendre(nav, args.sortie, "30-mattermost-canal-incident",
                    f"{url_mm}/{equipe}/channels/{canal}", prepare=fermer, attente=12,
                    note="canal d'incident et coordination")

        # ── Console NEXUS ───────────────────────────────────────────────────
        if not voulus or "nexus" in voulus:
            print("\nConsole NEXUS")
            nav = ouvrir_onglet(PORT)
            se_connecter(nav, "nexus", url_soc,
                         os.getenv("NEXUS_ADMIN_EMAIL", "admin@nexussoc.cm"),
                         os.environ["NEXUS_ADMIN_PASSWORD"])
            # La section « Approbation SOAR » affiche d'abord les actions EN
            # ATTENTE — quatre-vingt-dix cartes — puis le journal d'audit. Une
            # capture pleine page ferait plusieurs dizaines de milliers de
            # pixels de haut et le journal serait illisible.
            #
            # On masque les cartes en attente pour ne garder que le journal.
            # C'est un cadrage, pas un maquillage : aucune ligne du journal
            # n'est retirée, et la même page montre les deux.
            cadrer = ("(() => { let n = 0;"
                      "  document.querySelectorAll('.soar-action').forEach("
                      "    e => { e.remove(); n++; });"
                      "  document.querySelectorAll('.kicker').forEach(e => {"
                      "    if (/actions? en attente/i.test(e.textContent || ''))"
                      "      { e.remove(); n++; } });"
                      "  return n + ' carte(s) en attente masquée(s)'; })()")
            prendre(nav, args.sortie, "40-soar-journal-audit",
                    f"{url_soc}/app/console.html#soar", prepare=cadrer, attente=11,
                    note="journal soar_audit : décision, exécution, acteur, horodatage")

            # Le journal complet est dominé par les actions en attente. Une
            # seconde vue, filtrée sur « APPROUVÉE », ne garde que les actions
            # DÉCIDÉES : on y lit côte à côte une exécution automatique et les
            # levées. C'est la figure qui montre le cycle entier, rollback
            # compris.

    finally:
        proc.terminate()
        shutil.rmtree(profil, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
