# Quarantaine et blocage — rendre les actions SOAR exécutables

Comment OPNsense applique réellement `block_ip` et `isolate_host`, et comment
NEXUS le pilote.

> **État au 17 août 2026.** OPNsense n'est pas encore déployé. Ce document décrit
> ce que la phase 1 installe et ce que la phase 2 branche. Voir la
> [décision](../00_Documents/Decision_Reponse_Collaborative.md).

---

## 0. Un seul point d'application

La version précédente de ce document répartissait les rôles entre pfSense en
périmètre et MikroTik en routage inter-zone, et devait ouvrir sur un
avertissement : le trafic latéral ne remontait jamais jusqu'à pfSense, donc
bloquer une adresse sur le pare-feu de périmètre coupait la machine du cœur SOC
sans la couper de ses voisines. Les listes de réponse devaient vivre sur
MikroTik.

Cet avertissement disparaît. OPNsense route entre les zones **et** filtre le
périmètre. Une adresse ajoutée à un alias est bloquée sur tous les chemins, y
compris entre deux zones internes.

Deux limites subsistent, et elles tiennent à la topologie, pas au produit :

- **Deux machines d'une même zone se parlent en couche 2**, sans traverser la
  passerelle. La quarantaine ne les sépare pas. Pour isoler une machine de ses
  voisines immédiates, il faut l'isolation de port sur le commutateur, ou placer
  la machine seule dans son segment.
- **La quarantaine laisse volontairement passer la télémétrie vers le SOC.** Une
  machine mise en quarantaine reste observée. C'est le point qui distingue cette
  quarantaine de l'isolation locale que l'agent sait faire, laquelle coupe la
  machine du réseau et donc aussi de la supervision.

---

## 1. Interfaces d'OPNsense

Sept interfaces : le WAN, et une par zone.

| Interface | Zone | Adresse |
|---|---|---|
| WAN | sortie filtrée | selon le lien montant |
| LAN_MGMT | cœur SOC | 10.50.0.1/24 |
| LAN_DMZ | DMZ interne | 10.50.10.1/24 |
| LAN_APP | applicatif | 10.50.20.1/24 |
| LAN_SENS | sensible | 10.50.30.1/24 |
| LAN_ADM | administration | 10.50.40.1/24 |
| LAN_MEN | menace | 10.50.50.1/24 |

Les réseaux libvirt correspondants ne doivent plus porter d'adresse de
passerelle : `01-network-setup.sh` les crée en mode isolé, sans DHCP ni
routage, et OPNsense fournit les deux.

---

## 2. Les deux alias de réponse

Un alias est une liste nommée d'adresses, modifiable sans toucher aux règles.
C'est ce qui rend l'action réversible sans réécrire de configuration.

| Alias | Type | Usage |
|---|---|---|
| `nexus_block` | Host(s) | destinations bloquées, action `block_ip` |
| `nexus_quarantaine` | Host(s) | machines confinées, action `isolate_host` |

Les règles qui s'appuient sur ces alias se placent **au-dessus** de la matrice
de flux, dans l'ordre suivant :

1. `nexus_quarantaine` vers `10.50.0.2` port 8000 et 443 : **autoriser**
   (la machine confinée continue d'émettre sa télémétrie)
2. source `nexus_quarantaine` : **rejeter**
3. destination `nexus_quarantaine` : **rejeter**
4. destination `nexus_block` : **rejeter**
5. source `nexus_block` : **rejeter**

L'ordre compte. Si la règle 1 passait après la règle 2, la mise en quarantaine
couperait aussi l'observation, et la démonstration perdrait tout son intérêt.

---

## 3. Le compte d'API pour NEXUS

OPNsense authentifie l'API par une paire clé/secret, en HTTP Basic. Créer un
utilisateur `nexus-soar`, sans accès à l'interface web, et lui accorder les
seuls privilèges nécessaires :

- `Firewall: Alias: Edit`
- `Firewall: Alias: Util`

Rien d'autre. Un moteur SOAR compromis doit pouvoir modifier deux listes, pas
reconfigurer un pare-feu.

Restreindre également l'accès à l'interface d'administration à `10.50.0.2/32`,
et conserver l'empreinte du certificat pour l'épingler côté connecteur. Un SOAR
qui accepte n'importe quel certificat se fait détourner par la première attaque
active sur le lien.

```bash
# Sur l'hôte, après création de la clé dans OPNsense
sudo install -d -m 0700 -o nexus /etc/nexus
sudo openssl s_client -connect 10.50.0.1:443 </dev/null 2>/dev/null \
  | openssl x509 > /etc/nexus/opnsense-ca.pem
sudo chown nexus:nexus /etc/nexus/opnsense-ca.pem
```

---

## 4. Les appels que NEXUS produit

La console affiche exactement ces appels, avec l'identifiant d'audit, pour que
chaque entrée d'alias remonte à la décision qui l'a motivée.

**Blocage d'un indicateur**

```bash
curl -sS -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" --cacert /etc/nexus/opnsense-ca.pem \
  -X POST https://10.50.0.1/api/firewall/alias_util/add/nexus_block \
  -H 'Content-Type: application/json' \
  -d '{"address": "185.220.101.45"}'
```

**Mise en quarantaine d'une machine**

```bash
curl -sS -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" --cacert /etc/nexus/opnsense-ca.pem \
  -X POST https://10.50.0.1/api/firewall/alias_util/add/nexus_quarantaine \
  -H 'Content-Type: application/json' \
  -d '{"address": "10.50.20.20"}'
```

**Levée**, ce qui rend l'action réellement réversible comme la console l'annonce :

```bash
curl -sS -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" --cacert /etc/nexus/opnsense-ca.pem \
  -X POST https://10.50.0.1/api/firewall/alias_util/delete/nexus_quarantaine \
  -H 'Content-Type: application/json' \
  -d '{"address": "10.50.20.20"}'
```

**Relecture**, qui sert à la vérification et à la réconciliation :

```bash
curl -sS -u "$OPNSENSE_KEY:$OPNSENSE_SECRET" --cacert /etc/nexus/opnsense-ca.pem \
  https://10.50.0.1/api/firewall/alias_util/list/nexus_quarantaine
```

Les modifications d'alias par `alias_util` prennent effet immédiatement. Un
`POST /api/firewall/alias/reconfigure` n'est nécessaire qu'après une
modification de la définition d'un alias, pas de son contenu.

---

## 5. Vérifier

Depuis la machine mise en quarantaine :

```bash
ping -c2 10.50.30.30      # zone sensible → doit échouer
ping -c2 10.50.20.20      # zone applicative → doit échouer
curl -s 10.50.0.2:8000/health   # cœur SOC → doit répondre
```

Ce triplet est la démonstration : la machine est coupée de ses voisines, et
reste observée. C'est exactement ce que l'isolation locale de l'agent ne fait
pas, puisqu'elle coupe l'observation en laissant la machine libre de ses
mouvements.

Côté pare-feu, les compteurs de la règle de rejet doivent progresser dès que la
machine tente de sortir de sa zone.

---

## 6. Le connecteur (phase 2)

Tant qu'aucun connecteur n'est raccordé, la console affiche l'appel et
enregistre qui déclare l'avoir passé, avec le bouton **Attester**, horodaté et
nominatif. Le connecteur `Lot4_SOAR/connecteurs/opnsense.py` remplace cette
étape manuelle.

Trois précautions au moment de le brancher :

1. **Empreinte du certificat épinglée.** Le connecteur refuse une autorité
   inconnue plutôt que de faire confiance au réseau.
2. **Réconciliation au démarrage.** NEXUS est la source de vérité : au
   lancement, il relit les alias et repousse ce qui manque. Un redémarrage du
   pare-feu ne doit pas lever une quarantaine en silence.
3. **`execution` ne passe à `automatique` qu'après relecture vérifiée.** Un code
   HTTP 200 ne prouve pas que l'adresse figure dans l'alias. Le connecteur relit
   `alias_util/list` et compare. Un connecteur qui journalise un succès qu'il n'a
   pas obtenu reproduit exactement le défaut que la migration
   `06_schema_soar_cible.sql` a corrigé.

Variables d'environnement correspondantes :

```
OPNSENSE_URL=https://10.50.0.1
OPNSENSE_KEY=…
OPNSENSE_SECRET=…
OPNSENSE_CA=/etc/nexus/opnsense-ca.pem
OPNSENSE_ALIAS_BLOCK=nexus_block
OPNSENSE_ALIAS_QUARANTAINE=nexus_quarantaine
SOAR_CONNECTEURS_ACTIFS=0     # 0 conserve le comportement actuel
```

---

## 7. Ce que cela ne règle pas

Le gel de compte. Aucune topologie réseau ne suspend une identité : un routeur
transporte, un annuaire authentifie. Voir
[04-annuaire-vm-app-gov.md](04-annuaire-vm-app-gov.md).
