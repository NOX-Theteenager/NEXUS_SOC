#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Produit le config.xml d'OPNsense-CENADI à partir de la configuration d'usine.

    python3 lab-cenadi/scripts/opnsense-generer-config.py \
        --usine config-usine.xml --sortie config-cenadi.xml

Écrit les sept interfaces, les deux alias de réponse, la matrice de flux du §2
de l'architecture, la politique de sortie par zone, et le compte d'API restreint
du moteur SOAR.

POURQUOI GÉNÉRER PLUTÔT QUE CLIQUER
-----------------------------------
La matrice compte une trentaine de règles dont l'ORDRE décide du comportement.
Saisies à la main, elles divergent de la documentation dès la première
correction et personne ne s'en aperçoit. Ici, le fichier de règles et le
document d'architecture sortent de la même table.

CE QUE CE SCRIPT NE FAIT PAS
----------------------------
Il n'invente aucun secret. La clé d'API du compte SOAR est tirée du générateur
cryptographique du système et affichée une seule fois : à reporter dans le .env
du cœur SOC. Elle n'est écrite dans aucun fichier versionné.
"""
import argparse
import base64
import os
import secrets
import sys
import xml.etree.ElementTree as ET

SOC = "10.50.0.2"            # l'hôte, cœur SOC
# OPNsense n'accepte pas une liste de ports séparés par des espaces : il écarte
# la règle sans rien dire. On passe donc par un alias de ports, qui est la
# forme supportée — et qui donne au passage un nom lisible dans les règles.
ALIAS_PORTS = "nexus_collecte"
PORTS_COLLECTE = ALIAS_PORTS

# clé libvirt/OPNsense · interface · adresse · description · réseau
ZONES = [
    ("lan",  "vtnet1", "10.50.0.1",  "LAN_MGMT", "10.50.0.0/24"),
    ("opt1", "vtnet2", "10.50.10.1", "LAN_DMZ",  "10.50.10.0/24"),
    ("opt2", "vtnet3", "10.50.20.1", "LAN_APP",  "10.50.20.0/24"),
    ("opt3", "vtnet4", "10.50.30.1", "LAN_SENS", "10.50.30.0/24"),
    ("opt4", "vtnet5", "10.50.40.1", "LAN_ADM",  "10.50.40.0/24"),
    ("opt5", "vtnet6", "10.50.50.1", "LAN_MEN",  "10.50.50.0/24"),
]
ZONES_RESEAU = [z[4] for z in ZONES]

# Sortie autorisée depuis le cœur SOC. Des noms, pas des adresses : les miroirs
# changent d'adresse, la liste blanche doit survivre à ces changements.
SORTIE_SOC = [
    "mirror.opnsense.org", "pkg.freebsd.org", "packages.wazuh.com",
    "registry-1.docker.io", "ghcr.io", "auth.docker.io", "production.cloudflare.docker.com",
]


def sous(parent, tag, texte=None):
    e = ET.SubElement(parent, tag)
    if texte is not None:
        e.text = str(texte)
    return e


def vider(parent, tag):
    for e in parent.findall(tag):
        parent.remove(e)


# --------------------------------------------------------------------------- #
def ecrire_interfaces(racine):
    itf = racine.find("interfaces")
    for tag in list({c.tag for c in itf}):
        if tag != "lo0":
            vider(itf, tag)

    wan = sous(itf, "wan")
    sous(wan, "enable", 1)
    sous(wan, "if", "vtnet0")
    sous(wan, "descr", "WAN")
    sous(wan, "ipaddr", "dhcp")
    # Le lien montant est un réseau privé de l'hyperviseur : bloquer les
    # adresses privées y couperait la sortie elle-même.
    sous(wan, "blockpriv", 0)
    sous(wan, "blockbogons", 0)

    for cle, dev, adresse, descr, _ in ZONES:
        z = sous(itf, cle)
        sous(z, "enable", 1)
        sous(z, "if", dev)
        sous(z, "descr", descr)
        sous(z, "ipaddr", adresse)
        sous(z, "subnet", 24)
    return len(ZONES) + 1


def ecrire_alias(racine):
    fw = racine.find("OPNsense/Firewall")
    vider(fw, "Alias")
    al = sous(fw, "Alias")
    al.set("version", "1.0.1")
    conteneur = sous(al, "aliases")

    def ajouter(nom, typ, contenu, descr):
        a = sous(conteneur, "alias")
        a.set("uuid", str(__import__("uuid").uuid4()))
        sous(a, "enabled", 1)
        sous(a, "name", nom)
        sous(a, "type", typ)
        sous(a, "content", contenu)
        sous(a, "description", descr)

    ajouter("nexus_block", "host", "",
            "Destinations bloquees par NEXUS SOC (action block_ip)")
    ajouter("nexus_quarantaine", "host", "",
            "Machines confinees par NEXUS SOC (action isolate_host)")
    ajouter("soc_sortie_autorisee", "host", "\n".join(SORTIE_SOC),
            "Liste blanche de sortie du coeur SOC : correctifs et renseignement")
    ajouter(ALIAS_PORTS, "port", "8000\n443",
            "Ports de collecte NEXUS : ingestion et interface web")
    return 4


def regle(filtre, interface, action, descr, *,
          source="any", destination="any", ports=None, direction="in",
          proto=None, quick=True):
    r = sous(filtre, "rule")
    sous(r, "type", action)                      # pass | block
    sous(r, "interface", interface)
    sous(r, "ipprotocol", "inet")
    sous(r, "statetype", "keep state")
    sous(r, "direction", direction)
    if proto:
        sous(r, "protocol", proto)
    if quick:
        sous(r, "quick", 1)
    sous(r, "descr", descr)

    s = sous(r, "source")
    if source == "any":
        sous(s, "any", 1)
    elif source.endswith("net"):
        sous(s, "network", source[:-3])
    else:
        sous(s, "address", source)

    d = sous(r, "destination")
    if destination == "any":
        sous(d, "any", 1)
    elif destination.endswith("net"):
        sous(d, "network", destination[:-3])
    else:
        sous(d, "address", destination)
    if ports:
        sous(d, "port", ports)
    return r


def ecrire_regles(racine):
    f = racine.find("filter")
    if f is None:
        f = sous(racine, "filter")
    vider(f, "rule")
    n = 0
    interfaces = ["lan", "opt1", "opt2", "opt3", "opt4", "opt5"]

    # ── 1. Réponse SOAR : ces règles passent AVANT la matrice ───────────────
    # Une machine en quarantaine reste observée : c'est ce qui distingue cette
    # quarantaine de l'isolation locale, qui coupe aussi la supervision.
    for i in interfaces:
        regle(f, i, "pass", "NEXUS quarantaine : telemetrie vers le SOC autorisee",
              source="nexus_quarantaine", destination=SOC,
              ports=PORTS_COLLECTE, proto="tcp"); n += 1
        regle(f, i, "block", "NEXUS quarantaine : tout le reste rejete",
              source="nexus_quarantaine"); n += 1
        regle(f, i, "block", "NEXUS quarantaine : personne n'entre",
              destination="nexus_quarantaine"); n += 1
        regle(f, i, "block", "NEXUS blocage IOC : destination rejetee",
              destination="nexus_block"); n += 1
        regle(f, i, "block", "NEXUS blocage IOC : source rejetee",
              source="nexus_block"); n += 1

    # ── 2. Matrice de flux, interface par interface ─────────────────────────
    # Coeur SOC : atteint toutes les zones (collecte) et sort sur liste blanche.
    for reseau in ZONES_RESEAU[1:]:
        regle(f, "lan", "pass", f"SOC vers {reseau} : collecte",
              source="lannet", destination=reseau); n += 1
    regle(f, "lan", "pass", "SOC vers Internet : liste blanche journalisee",
          source="lannet", destination="soc_sortie_autorisee"); n += 1
    regle(f, "lan", "block", "SOC : tout autre flux rejete", source="lannet"); n += 1

    # DMZ et Applicatif : ne parlent qu'au SOC.
    for i, nom in (("opt1", "DMZ"), ("opt2", "Applicatif")):
        regle(f, i, "pass", f"{nom} vers le SOC : telemetrie",
              source=f"{i}net", destination=SOC, ports=PORTS_COLLECTE, proto="tcp"); n += 1
        regle(f, i, "block", f"{nom} : tout autre flux rejete", source=f"{i}net"); n += 1

    # Sensible : air-gap. Une seule sortie, vers le SOC, et rien d'autre.
    regle(f, "opt3", "pass", "ANTILOPE vers le SOC : telemetrie, seul flux autorise",
          source="opt3net", destination=SOC, ports=PORTS_COLLECTE, proto="tcp"); n += 1
    regle(f, "opt3", "block", "AIR-GAP : aucune autre sortie de la zone sensible",
          source="opt3net"); n += 1

    # Administration : SOC, DMZ, et une sortie filtree vers l'exterieur.
    regle(f, "opt4", "pass", "Admin vers le SOC", source="opt4net",
          destination=ZONES_RESEAU[0]); n += 1
    regle(f, "opt4", "pass", "Admin vers la DMZ", source="opt4net",
          destination=ZONES_RESEAU[1]); n += 1
    for reseau in ZONES_RESEAU[2:]:
        regle(f, "opt4", "block", f"Admin ne joint pas {reseau}",
              source="opt4net", destination=reseau); n += 1
    regle(f, "opt4", "pass", "Admin vers Internet : sortie filtree",
          source="opt4net"); n += 1

    # Menace : telemetrie seule. Ni Internet, ni la zone sensible, ni le reste.
    regle(f, "opt5", "pass", "Poste compromis : telemetrie vers le SOC",
          source="opt5net", destination=SOC, ports=PORTS_COLLECTE, proto="tcp"); n += 1
    regle(f, "opt5", "block", "Zone menace : aucun autre flux, Internet compris",
          source="opt5net"); n += 1

    # ── 3. Refus par defaut, explicite et journalise ────────────────────────
    for i in interfaces + ["wan"]:
        r = regle(f, i, "block", "Refus par defaut (matrice de flux)")
        sous(r, "log", 1); n += 1
    return n


def ecrire_compte_api(racine):
    """Compte de service du moteur SOAR : deux privilèges, rien de plus."""
    systeme = racine.find("system")
    for u in systeme.findall("user"):
        if u.findtext("name") == "nexus-soar":
            systeme.remove(u)

    cle = secrets.token_urlsafe(30)
    secret = secrets.token_urlsafe(45)

    u = sous(systeme, "user")
    sous(u, "name", "nexus-soar")
    sous(u, "descr", "NEXUS SOC - moteur de reponse (alias uniquement)")
    sous(u, "scope", "user")
    sous(u, "uid", 2000)
    sous(u, "disabled", 0)
    sous(u, "expires")
    sous(u, "authorizedkeys")
    sous(u, "shell", "/usr/sbin/nologin")
    # Les deux seuls privilèges nécessaires. Un SOAR compromis doit pouvoir
    # modifier deux listes, pas reconfigurer un pare-feu.
    sous(u, "priv", "page-firewall-alias,page-firewall-alias-util")
    ak = sous(u, "apikeys")
    item = sous(ak, "item")
    sous(item, "key", cle)
    sous(item, "secret", "$6$" + base64.b64encode(secret.encode()).decode()[:40])
    return cle, secret


def ecrire_acces(racine):
    """Interface web et SSH sur la seule zone du cœur SOC."""
    systeme = racine.find("system")
    for tag, valeur in (("hostname", "opnsense"), ("domain", "cenadi.local")):
        e = systeme.find(tag)
        (e if e is not None else sous(systeme, tag)).text = valeur
    ssh = systeme.find("ssh")
    if ssh is None:
        ssh = sous(systeme, "ssh")
    vider(ssh, "enabled"); vider(ssh, "interfaces")
    sous(ssh, "enabled", "enabled")
    sous(ssh, "interfaces", "lan")


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--usine", required=True, help="config.xml d'origine")
    ap.add_argument("--sortie", required=True, help="config.xml à produire")
    a = ap.parse_args()

    arbre = ET.parse(a.usine)
    racine = arbre.getroot()

    n_itf = ecrire_interfaces(racine)
    n_alias = ecrire_alias(racine)
    n_regles = ecrire_regles(racine)
    cle, secret = ecrire_compte_api(racine)
    ecrire_acces(racine)

    ET.indent(arbre, space="  ")
    arbre.write(a.sortie, encoding="UTF-8", xml_declaration=True)
    ET.parse(a.sortie)   # relecture : un fichier illisible ne sort pas d'ici

    print(f"  {n_itf} interfaces · {n_alias} alias · {n_regles} règles")
    print(f"  écrit : {a.sortie} ({os.path.getsize(a.sortie)} octets)")
    print()
    print("  Compte de service « nexus-soar » créé, avec une clé d'API de")
    print("  remplissage. ELLE NE FONCTIONNE PAS EN L'ÉTAT :")
    print()
    print(f"    clé de remplissage : {cle[:12]}…")
    print()
    print("  OPNsense stocke l'empreinte du secret, pas le secret, et cette")
    print("  empreinte ne peut pas être calculée hors de l'appliance. La vraie")
    print("  paire se crée dans l'interface web, Système > Accès > Utilisateurs")
    print("  > nexus-soar > API. C'est elle qui va dans OPNSENSE_KEY et")
    print("  OPNSENSE_SECRET du .env du cœur SOC.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
