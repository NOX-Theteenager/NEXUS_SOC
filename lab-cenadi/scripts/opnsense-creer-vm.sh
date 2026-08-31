#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : définition de la machine OPNsense
#
#      bash lab-cenadi/scripts/opnsense-creer-vm.sh              # aperçu
#      bash lab-cenadi/scripts/opnsense-creer-vm.sh --appliquer
#
#  Sept interfaces : le WAN, puis une par zone. L'ORDRE COMPTE — c'est lui qui
#  détermine le nom des cartes vues par OPNsense (vtnet0 à vtnet6). Les adresses
#  MAC sont fixées pour que la correspondance ne bouge jamais, y compris après
#  une redéfinition.
#
#      vtnet0  52:54:00:ce:ff:00  default            WAN (sortie filtrée)
#      vtnet1  52:54:00:ce:ff:01  nexus-cenadi-mgmt  10.50.0.1/24
#      vtnet2  52:54:00:ce:ff:02  nexus-cenadi-dmz   10.50.10.1/24
#      vtnet3  52:54:00:ce:ff:03  nexus-cenadi-app   10.50.20.1/24
#      vtnet4  52:54:00:ce:ff:04  nexus-cenadi-sens  10.50.30.1/24
#      vtnet5  52:54:00:ce:ff:05  nexus-cenadi-adm   10.50.40.1/24
#      vtnet6  52:54:00:ce:ff:06  nexus-cenadi-men   10.50.50.1/24
#
#  POURQUOI LE WAN EST SUR « default »
#  -----------------------------------
#  Le réseau libvirt « default » fait de la traduction d'adresses vers
#  l'extérieur. Il donne donc à OPNsense une sortie réelle, que le pare-feu
#  filtre ensuite zone par zone. C'est ce qui rend la politique de sortie
#  démontrable : sans lien montant, il n'y aurait rien à filtrer.
#
#  Prérequis : lab-cenadi/01-network-setup.sh --appliquer
#  Suite     : lab-cenadi/07-opnsense.md
# =============================================================================
set -uo pipefail
export LIBVIRT_DEFAULT_URI="qemu:///system"

DOMAINE="OPNsense-CENADI"
DISQUE="/var/lib/libvirt/images/OPNsense-CENADI.qcow2"
INSTALLATEUR="/var/lib/libvirt/images/opnsense-installateur.img"
RAM_MIO=4096
VCPU=2

APPLIQUER=0
[[ "${1:-}" == "--appliquer" ]] && APPLIQUER=1
GREEN="\033[32m"; RED="\033[31m"; JAUNE="\033[33m"; BOLD="\033[1m"; RAZ="\033[0m"

CARTES=(
  "default|52:54:00:ce:ff:00|WAN — sortie filtrée"
  "nexus-cenadi-mgmt|52:54:00:ce:ff:01|LAN_MGMT  10.50.0.1/24"
  "nexus-cenadi-dmz|52:54:00:ce:ff:02|LAN_DMZ   10.50.10.1/24"
  "nexus-cenadi-app|52:54:00:ce:ff:03|LAN_APP   10.50.20.1/24"
  "nexus-cenadi-sens|52:54:00:ce:ff:04|LAN_SENS  10.50.30.1/24"
  "nexus-cenadi-adm|52:54:00:ce:ff:05|LAN_ADM   10.50.40.1/24"
  "nexus-cenadi-men|52:54:00:ce:ff:06|LAN_MEN   10.50.50.1/24"
)

# ── Contrôles ───────────────────────────────────────────────────────────────
echo -e "${BOLD}Machine ${DOMAINE}${RAZ}"
echo
bloquant=0
for f in "$DISQUE" "$INSTALLATEUR"; do
  if [[ -r "$f" ]] || sudo -n test -r "$f" 2>/dev/null; then
    printf "  ✓ %s\n" "$f"
  else
    printf "  ${RED}✗ absent ou illisible : %s${RAZ}\n" "$f"; bloquant=1
  fi
done
for c in "${CARTES[@]}"; do
  IFS='|' read -r res mac role <<< "$c"
  if virsh net-info "$res" >/dev/null 2>&1; then
    printf "  ✓ réseau %-20s %-18s %s\n" "$res" "$mac" "$role"
  else
    printf "  ${RED}✗ réseau absent : %s${RAZ}\n" "$res"; bloquant=1
  fi
done

if virsh dominfo "$DOMAINE" >/dev/null 2>&1; then
  echo -e "\n  ${JAUNE}La machine existe déjà.${RAZ} --appliquer la redéfinira (disque conservé)."
fi
[[ $bloquant -eq 1 ]] && { echo -e "\n${RED}Prérequis manquants — rien n'est fait.${RAZ}"; exit 1; }

# ── Génération du XML ───────────────────────────────────────────────────────
interfaces=""
for c in "${CARTES[@]}"; do
  IFS='|' read -r res mac role <<< "$c"
  interfaces+="
    <interface type='network'>
      <mac address='$mac'/>
      <source network='$res'/>
      <model type='virtio'/>
    </interface>"
done

XML=$(cat <<XMLDOC
<domain type='kvm'>
  <name>$DOMAINE</name>
  <title>Pare-feu du lab souverain CENADI</title>
  <description>Routage inter-zone, matrice de flux, alias de reponse NEXUS.
Sept interfaces : WAN puis une par zone, dans l ordre vtnet0 a vtnet6.</description>
  <memory unit='MiB'>$RAM_MIO</memory>
  <currentMemory unit='MiB'>$RAM_MIO</currentMemory>
  <vcpu placement='static'>$VCPU</vcpu>
  <os>
    <type arch='x86_64' machine='q35'>hvm</type>
    <!-- Pas de <boot dev=...> ici : l'ordre est porté par chaque disque
         (libvirt refuse les deux notations ensemble). -->
  </os>
  <features><acpi/><apic/></features>
  <cpu mode='host-passthrough' check='none'/>
  <clock offset='utc'/>
  <on_poweroff>destroy</on_poweroff>
  <on_reboot>restart</on_reboot>
  <on_crash>destroy</on_crash>
  <devices>
    <emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type='file' device='disk'>
      <driver name='qemu' type='raw'/>
      <source file='$INSTALLATEUR'/>
      <target dev='vda' bus='virtio'/>
      <readonly/>
      <boot order='1'/>
    </disk>
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='$DISQUE'/>
      <target dev='vdb' bus='virtio'/>
      <boot order='2'/>
    </disk>$interfaces
    <serial type='pty'><target port='0'/></serial>
    <console type='pty'><target type='serial' port='0'/></console>
    <graphics type='vnc' port='-1' listen='127.0.0.1'/>
    <video><model type='vga'/></video>
    <memballoon model='virtio'/>
  </devices>
</domain>
XMLDOC
)

if [[ $APPLIQUER -eq 0 ]]; then
  cat <<'EOF'

MODE APERÇU — rien n'est défini. Ajoutez --appliquer pour agir.

Disposition des disques :
  vda  image d'installation, en lecture seule, démarrée en premier
  vdb  disque système 20 Go, cible de l'installation

Après l'installation, retirer l'image :
  virsh detach-disk OPNsense-CENADI vda --config
  virsh dumpxml OPNsense-CENADI | grep -A2 "boot order"   # vdb doit rester seul
EOF
  exit 0
fi

echo
if virsh dominfo "$DOMAINE" >/dev/null 2>&1; then
  virsh destroy "$DOMAINE" >/dev/null 2>&1
  virsh undefine "$DOMAINE" --nvram >/dev/null 2>&1 || virsh undefine "$DOMAINE" >/dev/null 2>&1
fi
if printf '%s' "$XML" | virsh define /dev/stdin >/dev/null 2>&1; then
  echo -e "  ${GREEN}✓ ${DOMAINE} définie${RAZ} — ${RAM_MIO} Mio, ${VCPU} vCPU, 7 interfaces"
else
  echo -e "  ${RED}✗ définition refusée${RAZ}"; exit 1
fi

# Constater plutôt que supposer : on relit l'ordre réel des cartes.
echo
echo "  Correspondance relue depuis la définition :"
virsh domiflist "$DOMAINE" | awk 'NR>2 && NF {printf "    vtnet%d  %-18s %s\n", n++, $5, $3}'

cat <<EOF

Démarrer et ouvrir la console :
    virsh start $DOMAINE
    virt-viewer $DOMAINE        # ou : virsh console $DOMAINE

Identifiants de l'image d'installation : installer / opnsense
Suite : lab-cenadi/07-opnsense.md
EOF
