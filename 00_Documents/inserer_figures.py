#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Installe les figures exportées depuis draw.io dans le mémoire.

    python3 00_Documents/inserer_figures.py

À lancer depuis la racine du dépôt, après avoir exporté les PNG
(voir 00_Documents/figures/A_REEXPORTER.md).

POURQUOI CE SCRIPT EXISTE
-------------------------
Les figures d'architecture vivent dans des fichiers .drawio versionnés. Word,
lui, embarque une copie PNG. Les deux se désynchronisent en silence : c'est
arrivé le 11 août, quand le mémoire a gardé pendant une semaine une topologie
montrant un pare-feu qui n'était plus celui du projet.

Ce script remplace la copie embarquée par l'export à jour, et refuse de le
faire si l'export est plus ancien que sa source. Un PNG périmé installé sans
avertissement serait pire que pas de PNG du tout.
"""
import shutil
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOCX = RACINE / "00_Documents" / "NEXUS_SOC_Rapport_CENADI_OpenSource.docx"
FIG = RACINE / "00_Documents" / "figures"

# figure du mémoire -> (base des fichiers, image embarquée dans le .docx)
FIGURES = [
    ("Topologie réseau souveraine",     "topologie-reseau-souveraine",     "word/media/image10.png"),
    ("Air-gap de la zone sensible",     "airgap-zone-sensible",            "word/media/image20.png"),
    ("Défense en profondeur",           "defense-en-profondeur-7-couches", "word/media/image25.png"),
    ("Chaîne de réponse collaborative", "chaine-reponse-collaborative",    "word/media/image28.png"),
]


def etat_export(base):
    """Renvoie (chemin, etat). Un export plus ancien que sa source est périmé."""
    png, drawio = FIG / f"{base}.png", FIG / f"{base}.drawio"
    if not png.exists():
        return None, "export absent"
    if drawio.exists() and png.stat().st_mtime < drawio.stat().st_mtime:
        return None, "export PÉRIMÉ (antérieur au .drawio)"
    return png, "à jour"


def main():
    if not DOCX.exists():
        sys.exit(f"✗ mémoire introuvable : {DOCX}")

    remplacements, avertis = {}, []
    for titre, base, membre in FIGURES:
        chemin, etat = etat_export(base)
        if chemin is None:
            print(f"  ⚠ {titre:<34} {'—':<38} {etat} · image inchangée")
            avertis.append(titre)
            continue
        remplacements[membre] = chemin.read_bytes()
        print(f"  ✓ {titre:<34} {chemin.name:<38} {etat}")

    sauvegarde = DOCX.with_suffix(".avant-figures.docx")
    shutil.copy2(DOCX, sauvegarde)

    temporaire = DOCX.with_suffix(".tmp.docx")
    with zipfile.ZipFile(DOCX) as src, \
         zipfile.ZipFile(temporaire, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            donnees = remplacements.get(info.filename) or src.read(info.filename)
            dst.writestr(info, donnees)
    temporaire.replace(DOCX)

    print(f"\n  Sauvegarde : {sauvegarde.name}")
    if avertis:
        print("\n  Figures laissées en l'état, faute d'export à jour :")
        for t in avertis:
            print(f"    · {t}")
        print("\n  Voir 00_Documents/figures/A_REEXPORTER.md, puis relancer ce script.")
    else:
        print("\n  Les quatre figures sont à jour dans le mémoire.")
    print("\n  Ouvrir le document dans Word et accepter la mise à jour des champs")
    print("  (ou Ctrl+A puis F9) pour renuméroter figures, tableaux et sommaire.")


if __name__ == "__main__":
    main()
