# CENADI — Spécifications des machines virtuelles

L'hôte joue le cœur SOC. Cinq machines virtuelles à créer, dont le pare-feu.

| VM | Image | RAM | vCPU | Disque | Réseau libvirt | MAC | IP |
|----|-------|-----|------|--------|----------------|-----|-----|
| `OPNsense-CENADI` | OPNsense 24.x | 4 Go | 2 | 20 Go | les 6 zones + WAN | — | `.1` de chaque zone |
| `vm-app-gov` | Ubuntu 22.04 Server | 1,5 Go | 2 | 25 Go | `nexus-cenadi-app` | `52:54:00:ce:00:20` | 10.50.20.20 |
| `vm-antilope` | Ubuntu 22.04 Server | 1 Go | 2 | 25 Go | `nexus-cenadi-sens` | `52:54:00:ce:00:30` | 10.50.30.30 |
| `vm-rssi` | Ubuntu 22.04 Desktop | 2 Go | 2 | 30 Go | `nexus-cenadi-adm` | `52:54:00:ce:00:40` | 10.50.40.40 |
| `KaliPrime` | Kali Rolling | 2 Go | 2 | 40 Go | `nexus-cenadi-men` | `52:54:00:ce:00:50` | 10.50.50.50 |

## Budget mémoire

Mesuré sur l'hôte le 17 août 2026, machines éteintes : **23 841 Mio au total,
14 409 Mio disponibles**, aucune pression mémoire, échange intact.

| Poste | Mio |
|---|---:|
| Disponible, machines éteintes | 14 409 |
| OPNsense avec Suricata | −4 096 |
| vm-rssi | −2 048 |
| KaliPrime | −2 048 |
| vm-app-gov | −1 536 |
| vm-antilope | −1 024 |
| DFIR-IRIS (app, worker, base, RabbitMQ) | −1 250 |
| Mattermost | −400 |
| **Marge** | **≈ 2 000** |

La carte mère accepte 64 Go sur deux emplacements, ce qui laisse une marge
matérielle si le besoin apparaît. Le choix de DFIR-IRIS plutôt que de TheHive
libère environ 4 500 Mio, et c'est ce qui finance Suricata sur le pare-feu.

**KaliPrime tourne sans session graphique.** Deux gigaoctets suffisent aux
scripts de scénario ; ils ne suffiraient pas à XFCE plus un outil Java. Basculer
la machine en mode console :

```bash
sudo systemctl set-default multi-user.target
```

GNS3 n'est plus nécessaire : avec un seul pare-feu et des réseaux libvirt, la
topologie se monte directement sous libvirt, ce qui retire une couche
d'émulation et sa consommation.

## Points d'attention

- **Forcer la MAC** de chaque machine, sinon pas d'adresse fixe.
- Brancher chaque machine sur **son** réseau libvirt.
- Les réseaux libvirt sont créés en mode isolé, sans DHCP ni passerelle :
  OPNsense fournit les deux. Voir `01-network-setup.sh`.
- Cocher **OpenSSH server** à l'installation, sauf sur vm-rssi.
- OPNsense reçoit sept interfaces : le WAN plus une par zone. L'ordre
  d'attachement détermine le nom de l'interface, à noter au moment de la
  création.

## Après installation

Depuis l'hôte, transférer et exécuter le script de chaque machine :

```bash
scp lab-cenadi/scripts/vm-app-gov-setup.sh <utilisateur>@10.50.20.20:/tmp/
ssh <utilisateur>@10.50.20.20 'sudo bash /tmp/vm-app-gov-setup.sh'

# vm-antilope : la règle OPNsense zone Sensible → SOC doit exister d'abord
scp lab-cenadi/scripts/vm-antilope-setup.sh <utilisateur>@10.50.30.30:/tmp/

# vm-rssi : pousser l'autorité racine, puis le script
scp ~/pki-cenadi/cenadi-root-ca.crt <utilisateur>@10.50.40.40:/tmp/
scp lab-cenadi/scripts/vm-rssi-setup.sh <utilisateur>@10.50.40.40:/tmp/

# KaliPrime
scp lab-cenadi/scripts/vm-menace-setup.sh kali@10.50.50.50:/tmp/
```

Le déploiement du collecteur passe par `scripts/deployer-collecteur.sh`, qui
préfère l'agent invité QEMU quand il est installé et retombe sur SSH sinon.

## Instantanés

```bash
for vm in OPNsense-CENADI vm-app-gov vm-antilope vm-rssi KaliPrime; do
    virsh -c qemu:///system snapshot-create-as "$vm" os-installed \
        "OS installé — $(date -I)"
done
```
