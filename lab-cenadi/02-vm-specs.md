# CENADI — Spécifications des VMs

Le HÔTE joue le cœur SOC. 4 VMs à créer dans virt-manager.

| VM | ISO | RAM | vCPU | Disque | Réseau libvirt | MAC | IP |
|----|-----|-----|------|--------|----------------|-----|-----|
| `vm-app-gov` | Ubuntu 22.04 Server | 2 Go | 2 | 25 Go | `nexus-cenadi-app` | `52:54:00:ce:00:20` | 10.50.20.20 |
| `vm-antilope` | Ubuntu 22.04 Server | 2 Go | 2 | 25 Go | `nexus-cenadi-sens` | `52:54:00:ce:00:30` | 10.50.30.30 |
| `vm-rssi` | Ubuntu 22.04 Desktop | 2 Go | 2 | 30 Go | `nexus-cenadi-adm` | `52:54:00:ce:00:40` | 10.50.40.40 |
| `vm-menace` | Kali Rolling | 4 Go | 2 | 40 Go | `nexus-cenadi-men` | `52:54:00:ce:00:50` | 10.50.50.50 |

**Total VMs ≈ 10 Go RAM** + pfSense (1 Go) + MikroTik (0,5 Go) dans GNS3.

## Points d'attention
- **Forcer la MAC** de chaque VM (sinon pas d'IP fixe DHCP).
- Brancher chaque VM sur **son** réseau libvirt (colonne « Réseau »).
- Cocher **OpenSSH server** à l'installation (sauf vm-rssi Desktop où ce n'est
  pas indispensable).
- Profils suggérés : user `cenadi` / mdp `cenadi` (adapter selon la politique).

## Après installation
Depuis le HÔTE, transférer et exécuter le script de chaque VM :

```bash
# Exemple pour vm-app-gov
scp lab-cenadi/scripts/vm-app-gov-setup.sh cenadi@10.50.20.20:/tmp/
ssh cenadi@10.50.20.20 'sudo bash /tmp/vm-app-gov-setup.sh'

# vm-antilope (zone sensible) — nécessite l'ACL MikroTik zone30→SOC d'abord
scp lab-cenadi/scripts/vm-antilope-setup.sh cenadi@10.50.30.30:/tmp/

# vm-rssi : d'abord pousser l'AC racine, puis le script
scp ~/pki-cenadi/cenadi-root-ca.crt cenadi@10.50.40.40:/tmp/
scp lab-cenadi/scripts/vm-rssi-setup.sh cenadi@10.50.40.40:/tmp/

# vm-menace
scp lab-cenadi/scripts/vm-menace-setup.sh kali@10.50.50.50:/tmp/
```

## Snapshots
```bash
for vm in vm-app-gov vm-antilope vm-rssi vm-menace; do
    virsh snapshot-create-as "$vm" os-installed "OS installé — $(date -I)"
done
```
