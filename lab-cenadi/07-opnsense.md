# OPNsense — installation et mise en service

Phase 1 du [plan](../00_Documents/Decision_Reponse_Collaborative.md).

> **État au 19 août 2026.** Installé, configuré, vérifié. Les sept interfaces
> portent leurs adresses, les trois alias existent comme tables pf, 119 règles
> sont chargées et le WAN a une route par défaut. Reste Suricata et la bascule
> des machines supervisées (§6).

---

## 1. Ce qui est déjà fait

```bash
bash lab-cenadi/01-network-setup.sh --appliquer      # six zones isolées
bash lab-cenadi/scripts/opnsense-creer-vm.sh --appliquer
```

Les réseaux libvirt sont devenus de purs commutateurs : ni passerelle, ni
service d'adressage. L'hôte ne garde une adresse que sur la zone du cœur SOC,
en **10.50.0.2**, posée par libvirt donc persistante. Les `.1` reviennent au
pare-feu.

La machine porte sept interfaces dans un ordre fixé par leurs adresses MAC :

| Vue OPNsense | Réseau libvirt | Rôle | Adresse |
|---|---|---|---|
| `vtnet0` | `default` | WAN, sortie filtrée | DHCP de l'hyperviseur |
| `vtnet1` | `nexus-cenadi-mgmt` | LAN_MGMT | 10.50.0.1/24 |
| `vtnet2` | `nexus-cenadi-dmz` | LAN_DMZ | 10.50.10.1/24 |
| `vtnet3` | `nexus-cenadi-app` | LAN_APP | 10.50.20.1/24 |
| `vtnet4` | `nexus-cenadi-sens` | LAN_SENS | 10.50.30.1/24 |
| `vtnet5` | `nexus-cenadi-adm` | LAN_ADM | 10.50.40.1/24 |
| `vtnet6` | `nexus-cenadi-men` | LAN_MEN | 10.50.50.1/24 |

---

## 2. Installer sur le disque

L'installateur d'OPNsense est une suite de boîtes de dialogue. L'automatiser
demanderait de détourner `bsddialog`, pour un gain de deux minutes et un risque
de partitionner le mauvais disque. Ces quelques touches se font à la main.

Ouvrir la console :

```bash
virt-viewer --connect qemu:///system OPNsense-CENADI
```

Puis :

1. `login:` **installer** — mot de passe **opnsense**
2. Disposition du clavier : **French** si le clavier est en AZERTY, sinon
   accepter
3. **Install (UFS)**
4. Choisir **vtbd1** (20 Go). *Surtout pas `vtbd0`, qui est l'image
   d'installation elle-même : 2,5 Go, en lecture seule.*
5. Confirmer la destruction du disque
6. Mot de passe root, deux fois, puis **Complete Install**

Au redémarrage, retirer l'image d'installation pour que la machine amorce
seule :

```bash
virsh -c qemu:///system shutdown OPNsense-CENADI
virsh -c qemu:///system detach-disk OPNsense-CENADI vda --config --persistent
virsh -c qemu:///system start OPNsense-CENADI
```

---

## 3. Appliquer la configuration CENADI

Après l'installation, OPNsense repart de sa configuration d'usine : `vtnet0` en
LAN à **192.168.1.1/24**, le reste inutilisé.

> **Ne pas se donner d'adresse dans 192.168.1.0/24 sur l'hôte.** Sur cette
> machine, c'est le réseau Wi-Fi réel, et 192.168.1.1 est la box. Poser
> `192.168.1.2/24` sur `virbr0` crée un sous-réseau en double et peut couper
> l'accès Internet de l'hôte. La version précédente de ce document le
> recommandait : c'était une erreur.

### 3.1 Déplacer l'adresse du LAN depuis la console

La console se pilote sans réseau, avec `virsh send-key`. Se connecter en
**root**, puis :

- option **2** (Set interface IP address) → interface **1** (LAN)
- DHCP : **n** · adresse : **192.168.122.240** · masque : **24** · passerelle :
  Entrée
- IPv6 par suivi WAN : **n** · DHCP6 : **n** · adresse IPv6 : Entrée
- serveur DHCP : **n** · passage en HTTP : **n** · nouveau certificat : **n** ·
  restauration des accès : **n**

`192.168.122.0/24` est le réseau `default` de libvirt, où l'hôte tient déjà
`192.168.122.1`. L'appliance devient donc joignable sans rien ajouter sur
l'hôte.

### 3.2 Ouvrir SSH

Le système installé démarre sans SSH. Depuis la console, option **8** (Shell) :

```sh
cp /conf/config.xml /conf/cfg.bak
sed -i "" -e "s|<ssh>|<ssh><enabled>enabled</enabled><interfaces>lan</interfaces><permitrootlogin>1</permitrootlogin><passwordauth>1</passwordauth>|" /conf/config.xml
reboot
```

### 3.3 Générer et pousser la configuration

Partir de la configuration **courante** de l'appliance, pas de celle du support
d'installation : elle porte l'empreinte du mot de passe root choisi pendant
l'installation.

```bash
export OPNSENSE_SSH_HOST=192.168.122.240 OPNSENSE_SSH_PASSWORD='<mot de passe root>'
python3 lab-cenadi/scripts/opnsense-console.py "sh -c 'cat /conf/config.xml'" \
    | sed -n '/<?xml/,/<\/opnsense>/p' > /tmp/config-usine.xml

python3 lab-cenadi/scripts/opnsense-generer-config.py \
    --usine /tmp/config-usine.xml --sortie /tmp/config-cenadi.xml
```

Le générateur affiche **une seule fois** la clé et le secret du compte d'API du
moteur SOAR. Les reporter aussitôt dans le `.env` du cœur SOC.

`opnsense-console.py` ne transmet pas l'entrée standard : le fichier voyage
compressé, dans la commande elle-même, et son empreinte est comparée des deux
côtés.

```bash
B64=$(gzip -9c /tmp/config-cenadi.xml | base64 -w0)
python3 lab-cenadi/scripts/opnsense-console.py \
    "sh -c \"echo $B64 | openssl base64 -d -A | gzip -d > /conf/config.new.xml\""
python3 lab-cenadi/scripts/opnsense-console.py "sh -c 'md5 -q /conf/config.new.xml'"
md5sum /tmp/config-cenadi.xml      # les deux empreintes doivent coïncider

python3 lab-cenadi/scripts/opnsense-console.py \
    "sh -c 'cp /conf/config.xml /conf/config.avant-cenadi.xml;
            cp /conf/config.new.xml /conf/config.xml;
            chown wwwonly:wheel /conf/config.xml'"
python3 lab-cenadi/scripts/opnsense-console.py "sh -c 'reboot'"
```

Au redémarrage, le LAN passe sur `vtnet1` et l'appliance répond sur
**10.50.0.1**, joignable depuis l'hôte qui tient `10.50.0.2`. En cas de
problème, `/conf/config.avant-cenadi.xml` reste sur l'appliance et la console
est toujours accessible.

### 3.4 Le secret d'API se saisit dans l'appliance

OPNsense stocke l'empreinte du secret, pas le secret. Le générateur ne peut donc
pas la calculer de l'extérieur. Dans **Système → Accès → Utilisateurs →
nexus-soar**, créer une clé d'API : OPNsense affiche alors le couple à reporter
dans le `.env`. C'est cette valeur qui fait foi.

---

## 4. Ce que la configuration contient

**Sept interfaces**, adressées comme au §1.

**Trois alias** : `nexus_block` et `nexus_quarantaine`, vides au départ, pilotés
par l'API du moteur SOAR ; `soc_sortie_autorisee`, la liste blanche de sortie
du cœur SOC, en noms d'hôtes plutôt qu'en adresses pour survivre aux
changements de miroir.

**Cinquante-neuf règles**, dans un ordre qui décide du comportement :

1. les cinq règles de réponse SOAR passent en premier sur chaque zone. La
   première autorise une machine en quarantaine à continuer d'émettre sa
   télémétrie vers le SOC. Si elle passait après la règle de rejet, la
   quarantaine couperait aussi l'observation, et la démonstration perdrait tout
   son intérêt ;
2. la matrice de flux, interface par interface ;
3. un refus par défaut, explicite et journalisé, sur chaque interface.

**Un compte d'API** `nexus-soar`, sans accès à l'interface web, limité à deux
privilèges : modifier un alias, et utiliser l'utilitaire d'alias. Rien d'autre.

---

## 5. Recette

À exécuter une fois les machines rebasculées sur le plan 10.50 :

```bash
bash lab-cenadi/scenarios/05-matrice-de-flux.sh
```

Trois preuves attendues :

- depuis vm-antilope, `ping 8.8.8.8` et `ping 10.50.20.20` échouent, mais
  `curl 10.50.0.2:8000/health` répond ;
- depuis le cœur SOC, un miroir de la liste blanche répond, un domaine absent
  de la liste est rejeté et journalisé ;
- une adresse ajoutée à `nexus_quarantaine` perd le contact latéral et
  **continue** d'émettre sa télémétrie.

---

## 6. Reste à faire dans cette phase

- **Clé d'API réelle** pour `nexus-soar` (§3.4), puis report dans le `.env`.
- **Suricata** sur les interfaces internes (Services → Détection d'intrusion).
- **Résolution de noms depuis le pare-feu** : `fetch` échoue encore avec
  « Address family for host not supported ». La liste blanche de sortie repose
  sur des noms d'hôtes : tant que la résolution ne fonctionne pas, l'alias
  `soc_sortie_autorisee` reste vide en pratique.
- **Adresses fixes dans chaque machine**, avec le `.1` de sa zone en passerelle,
  puis retrait de la carte sur `default`.
- **Bascule de l'URL du SOC** des collecteurs vers `10.50.0.2:8000`.

## 7. État constaté le 19 août 2026

```
vtnet0  192.168.122.173  WAN, bail DHCP, route par defaut vers 192.168.122.1
vtnet1  10.50.0.1        LAN_MGMT      vtnet4  10.50.30.1  LAN_SENS
vtnet2  10.50.10.1       LAN_DMZ       vtnet5  10.50.40.1  LAN_ADM
vtnet3  10.50.20.1       LAN_APP       vtnet6  10.50.50.1  LAN_MEN

tables pf : nexus_block · nexus_quarantaine · soc_sortie_autorisee
regles chargees : 119   compte de service : nexus-soar (uid 2000)
```
