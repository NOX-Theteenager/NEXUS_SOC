# Quarantaine et blocage — mise en œuvre GNS3

Comment rendre exécutables les actions `isolate_host` et `block_ip` proposées par
NEXUS SOC. Complète [00-architecture-cenadi.md](00-architecture-cenadi.md).

---

## 0. Le point d'application est MikroTik, pas pfSense

C'est le point le plus important du document, et il est contre-intuitif.

Dans la topologie prévue, l'ordre est :

```
HÔTE (cœur SOC 10.50.0.1) → pfSense → MikroTik → VLAN 10/20/30/40/50
```

pfSense est **en amont** de MikroTik. Le trafic latéral — menace → app,
app → sensible — transite par MikroTik et **ne remonte jamais** jusqu'à pfSense.

Conséquence directe : bloquer une adresse sur pfSense coupe la machine **du
SOC**, pas de ses voisines. C'est exactement l'erreur que corrige la refonte —
se rendre aveugle en croyant confiner. **Les listes de blocage et de quarantaine
vivent sur MikroTik.**

pfSense garde son rôle : filtrage périmétrique entre le cœur SOC et le reste,
WAN désactivé.

### Limite à connaître avant de commencer

Un routeur ne voit que le trafic qu'il **route**. Deux machines d'un même VLAN se
parlent en couche 2 sans passer par MikroTik : la quarantaine ne les sépare pas.

Deux façons de traiter ce cas, si votre démonstration en a besoin :

- une machine par VLAN (chaque poste dans son propre segment) — simple, réaliste
  pour un lab, verbeux au-delà de cinq machines ;
- isolation de ports sur le bridge GNS3.

Pour la soutenance, l'annoncer explicitement vaut mieux que de le découvrir sous
une question du jury. La quarantaine coupe le nord-sud, pas l'est-ouest
intra-segment.

---

## 1. Libérer les adresses `.1` pour MikroTik

Aujourd'hui vos réseaux libvirt portent l'adresse de passerelle sur **l'hôte** :

```
virbr-cen-app    10.50.20.1
virbr-cen-sens   10.50.30.1
virbr-cen-adm    10.50.40.1
```

Or l'architecture attribue ces mêmes `.1` à MikroTik. Tant que l'hôte les
occupe, MikroTik ne peut pas les prendre et rien ne le traverse.

Les réseaux doivent devenir de **purs bridges de couche 2** : ni adresse IP, ni
DHCP côté libvirt.

```bash
# Pour chaque zone : app, sens, adm, dmz, men
virsh -c qemu:///system net-destroy  nexus-cenadi-app
virsh -c qemu:///system net-edit     nexus-cenadi-app
```

Supprimer **tout le bloc `<ip>`** (il emporte le `<dhcp>`) :

```xml
<!-- À SUPPRIMER intégralement -->
<ip address='10.50.20.1' netmask='255.255.255.0'>
  <dhcp>
    <range start='10.50.20.100' end='10.50.20.200'/>
  </dhcp>
</ip>
```

Le réseau conserve son `<bridge name='virbr-cen-app'/>` et reste sans
`<forward>` : un commutateur virtuel, rien de plus.

```bash
virsh -c qemu:///system net-start nexus-cenadi-app
ip -br a show virbr-cen-app        # ne doit plus afficher d'adresse IPv4
```

> **Conserver `nexus-cenadi-mgmt` tel quel.** L'hôte y garde 10.50.0.1 : c'est le
> cœur SOC, il doit rester joignable indépendamment de l'état du lab.

---

## 2. Câbler GNS3

Dans GNS3, chaque réseau libvirt s'atteint par un nœud **Cloud** lié au bridge.

| Nœud | Type | Rattachement |
|---|---|---|
| `soc-core` | Cloud | `virbr-cen-mgmt` |
| `pfSense-CENADI` | VM QEMU (la vôtre) | em0 → `soc-core`, em1 → MikroTik |
| `MikroTik-CENADI` | CHR | ether1 → pfSense, ether2..6 → zones |
| `z-dmz` … `z-men` | Cloud | `virbr-cen-dmz` … `virbr-cen-men` |

Correspondance des interfaces MikroTik :

| Interface | Zone | Adresse |
|---|---|---|
| ether1 | liaison pfSense | 10.50.1.2/30 |
| ether2 | DMZ | 10.50.10.1/24 |
| ether3 | Applicatif | 10.50.20.1/24 |
| ether4 | Sensible | 10.50.30.1/24 |
| ether5 | Admin | 10.50.40.1/24 |
| ether6 | Menace | 10.50.50.1/24 |

Votre VM pfSense n'a **qu'une carte réseau** aujourd'hui. Il faut lui en ajouter
une seconde avant de la câbler :

```bash
virsh -c qemu:///system shutdown Pfsense
virsh -c qemu:///system attach-interface Pfsense network nexus-cenadi-mgmt \
      --model e1000e --config
virsh -c qemu:///system start Pfsense
```

Adresses fixes sur les VM (plus de DHCP), conformément au plan d'adressage :
`vm-app-gov` 10.50.20.20/24 gw 10.50.20.1, `vm-antilope` 10.50.30.30/24 gw
10.50.30.1, `vm-rssi` 10.50.40.40/24 gw 10.50.40.1.

---

## 3. Configurer MikroTik

### 3.1 Les deux listes pilotées par NEXUS

Rien à créer : sur RouterOS, une liste d'adresses naît de son premier membre.
Ce sont les règles qui doivent préexister.

### 3.2 Les règles de filtrage

L'ordre est déterminant. Les autorisations SOC passent **avant** les rejets,
sinon la quarantaine coupe aussi la télémétrie et vous perdez la visibilité sur
la machine que vous vouliez observer.

```
/ip firewall filter

# ── Quarantaine : la machine ne parle plus qu'au SOC ──────────────────────
add chain=forward src-address-list=NEXUS_QUARANTAINE dst-address=10.50.0.1 \
    action=accept comment="NEXUS quarantaine — telemetrie vers le SOC"
add chain=forward dst-address-list=NEXUS_QUARANTAINE src-address=10.50.0.1 \
    action=accept comment="NEXUS quarantaine — retour du SOC"
add chain=forward src-address-list=NEXUS_QUARANTAINE \
    action=drop comment="NEXUS quarantaine — tout le reste"
add chain=forward dst-address-list=NEXUS_QUARANTAINE \
    action=drop comment="NEXUS quarantaine — trafic entrant"

# ── Blocage d'indicateur ──────────────────────────────────────────────────
add chain=forward dst-address-list=NEXUS_BLOCK \
    action=drop comment="NEXUS blocage IOC — sortant"
add chain=forward src-address-list=NEXUS_BLOCK \
    action=drop comment="NEXUS blocage IOC — entrant"
```

Ces six règles doivent se trouver **en tête** de la chaîne `forward`, avant la
matrice de flux inter-zones du §2 de l'architecture :

```
/ip firewall filter print                    # relever les numéros
/ip firewall filter move [find comment~"NEXUS"] destination=0
```

### 3.3 Le compte de service pour NEXUS

Un compte dédié, restreint à l'adresse du SOC, par clé uniquement :

```
/user group add name=soar policy=ssh,read,write,test \
    comment="NEXUS SOC — pilotage des listes de reponse"
/user add name=nexus-soar group=soar address=10.50.0.1/32
/user ssh-keys import public-key-file=nexus-soar.pub user=nexus-soar
/ip service set ssh address=10.50.0.1/32
/ip service disable telnet,ftp,www,api
```

Côté hôte SOC :

```bash
sudo -u nexus ssh-keygen -t ed25519 -N '' -f /etc/nexus/mikrotik_ed25519
```

`policy=write` est nécessaire pour modifier les listes. Le garde-fou n'est pas le
niveau de privilège mais `address=10.50.0.1/32` : la clé ne sert que depuis le
cœur SOC.

---

## 4. Les commandes que NEXUS affiche

La console produit exactement ces commandes, avec l'identifiant d'audit en
commentaire pour que chaque règle soit traçable jusqu'à la décision qui l'a
motivée.

**Blocage d'un indicateur**

```
/ip firewall address-list add list=NEXUS_BLOCK address=185.220.101.45 \
    comment="NEXUS 42"
```

**Mise en quarantaine d'un hôte**

```
/ip firewall address-list add list=NEXUS_QUARANTAINE address=10.50.20.20 \
    comment="NEXUS 43"
```

**Levée** — c'est ce qui rend l'action réellement réversible, comme la console
l'annonce :

```
/ip firewall address-list remove [find list=NEXUS_QUARANTAINE address=10.50.20.20]
```

---

## 5. Vérifier

```
/ip firewall address-list print where list=NEXUS_QUARANTAINE
/ip firewall filter print stats where comment~"NEXUS"
```

La colonne des compteurs doit progresser dès que la machine tente de sortir.
Depuis la machine mise en quarantaine :

```bash
ping -c2 10.50.30.30      # zone sensible  → doit échouer
ping -c2 10.50.0.1        # cœur SOC       → doit répondre
```

Ce couple est votre démonstration : la machine est coupée, **et reste observée**.
C'est précisément ce que l'isolation actuelle ne fait pas — elle coupe
l'observation en laissant la machine libre de ses mouvements.

---

## 6. Une fois le connecteur raccordé

Tant qu'aucun connecteur n'existe, la console affiche la commande et enregistre
qui déclare l'avoir passée (bouton **Attester**, horodaté et nominatif). Le
connecteur remplacera cette étape manuelle :

```python
subprocess.run(
    ["ssh", "-i", "/etc/nexus/mikrotik_ed25519",
     "-o", "StrictHostKeyChecking=yes",
     f"nexus-soar@{MIKROTIK_HOST}", commande],
    timeout=10, check=True)
```

Trois précautions au moment de le brancher :

1. **`StrictHostKeyChecking=yes`** avec l'empreinte du routeur pré-enregistrée.
   Un SOAR qui accepte n'importe quelle clé d'hôte se fait détourner par la
   première attaque active sur le lien.
2. **Réconciliation au démarrage** — NEXUS est la source de vérité. Au lancement,
   il repousse l'intégralité de ses listes : un redémarrage du routeur ne doit
   pas lever silencieusement une quarantaine.
3. **Le statut d'exécution ne passe à `automatique` que si la commande a rendu
   un code 0.** Un connecteur qui journalise un succès qu'il n'a pas obtenu
   reproduit exactement le défaut qu'on vient de corriger.

---

## 7. Ce que cela ne règle pas

Le gel de compte. Aucune topologie réseau ne suspend une identité — c'est un
autre plan. Il faut un annuaire, voir
[04-annuaire-vm-app-gov.md](04-annuaire-vm-app-gov.md).
