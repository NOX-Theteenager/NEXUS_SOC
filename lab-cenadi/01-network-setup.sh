#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC — LAB CENADI (souverain) : réseaux libvirt zonés
# =============================================================================
# Crée les réseaux du datacenter CENADI simulé. TOUS isolés (pas de <forward>) :
# aucune zone n'a de route Internet. Le routage inter-zone + les ACL (dont
# l'air-gap de la zone sensible) sont gérés par le pare-feu pfSense + MikroTik
# dans GNS3 (voir 00-architecture-cenadi.md).
#
#   nexus-cenadi-mgmt  (10.50.0.0/24)   — Cœur SOC (HÔTE = 10.50.0.1)
#   nexus-cenadi-dmz   (10.50.10.0/24)  — DMZ interne (reverse-proxy, SMTP)
#   nexus-cenadi-app   (10.50.20.0/24)  — Serveurs applicatifs gouvernementaux
#   nexus-cenadi-sens  (10.50.30.0/24)  — Zone SENSIBLE ANTILOPE (AIR-GAP)
#   nexus-cenadi-adm   (10.50.40.0/24)  — Postes administration (RSSI/DSI)
#   nexus-cenadi-men   (10.50.50.0/24)  — Zone menace (poste compromis)
#
# Usage :
#   ./01-network-setup.sh            # crée les réseaux
#   ./01-network-setup.sh --destroy  # supprime
#   ./01-network-setup.sh --status   # état
# =============================================================================
set -euo pipefail

# libvirt : forcer la connexion SYSTÈME (démon libvirtd root). Pour un
# utilisateur non-root, virsh utilise par défaut qemu:///session, dont le démon
# tourne sans privilèges et NE PEUT PAS créer de bridge -> l'erreur
# « creating bridge interface ... : Operation not permitted ». L'appartenance au
# groupe libvirt (vérifiée plus bas) autorise l'accès système via polkit.
export LIBVIRT_DEFAULT_URI="qemu:///system"

declare -A NETWORKS=(
    [nexus-cenadi-mgmt]="virbr-cen-mgmt|10.50.0.0/24|10.50.0.1|Coeur SOC (HOTE)"
    [nexus-cenadi-dmz]="virbr-cen-dmz|10.50.10.0/24|10.50.10.1|DMZ interne"
    [nexus-cenadi-app]="virbr-cen-app|10.50.20.0/24|10.50.20.1|Serveurs applicatifs"
    [nexus-cenadi-sens]="virbr-cen-sens|10.50.30.0/24|10.50.30.1|Zone SENSIBLE (air-gap)"
    [nexus-cenadi-adm]="virbr-cen-adm|10.50.40.0/24|10.50.40.1|Admin RSSI/DSI"
    [nexus-cenadi-men]="virbr-cen-men|10.50.50.0/24|10.50.50.1|Zone menace"
)

# Réservations MAC → IP fixes
MAC_APP="52:54:00:ce:00:20"      # → 10.50.20.20 (vm-app-gov)
MAC_ANTILOPE="52:54:00:ce:00:30" # → 10.50.30.30 (vm-antilope, sensible)
MAC_RSSI="52:54:00:ce:00:40"     # → 10.50.40.40 (vm-rssi)
MAC_MENACE="52:54:00:ce:00:50"   # → 10.50.50.50 (vm-menace)

if [[ "${1:-}" == "--status" ]]; then
    virsh net-list --all
    for net in "${!NETWORKS[@]}"; do
        virsh net-info "$net" >/dev/null 2>&1 && { echo; echo "── $net ──"; virsh net-dhcp-leases "$net" 2>/dev/null | head -6; }
    done
    exit 0
fi

if [[ "${1:-}" == "--destroy" ]]; then
    for net in "${!NETWORKS[@]}"; do
        echo "⚠  Suppression $net"
        virsh net-destroy "$net" 2>/dev/null || true
        virsh net-undefine "$net" 2>/dev/null || true
    done
    echo "✓ Réseaux CENADI supprimés."
    exit 0
fi

command -v virsh >/dev/null || { echo "✗ virsh absent (sudo apt install libvirt-clients)"; exit 1; }
groups | grep -qw libvirt || { echo "✗ pas dans le groupe libvirt"; exit 1; }

# Conflit d'IP sur le hôte ?
for cidr in 10.50.0 10.50.10 10.50.20 10.50.30 10.50.40 10.50.50; do
    if ip -o addr show 2>/dev/null | grep -q "$cidr\."; then
        m=$(ip -o addr show | grep "$cidr\." | grep -oE "virbr-cen-[a-z]+" | head -1)
        [[ -z "$m" ]] && { echo "✗ $cidr.x déjà utilisé hors lab CENADI"; ip -o addr show | grep "$cidr\."; exit 1; }
    fi
done

for net in "${!NETWORKS[@]}"; do
    IFS='|' read -r bridge cidr gateway desc <<< "${NETWORKS[$net]}"
    prefix="${cidr%.*}"
    xml="/tmp/${net}.xml"
    cat > "$xml" <<XML
<network>
  <name>${net}</name>
  <bridge name='${bridge}' stp='on' delay='0'/>
  <!-- ISOLÉ : aucune route Internet ; routage inter-zone par pfSense/MikroTik -->
  <domain name='cenadi.local' localOnly='yes'/>
  <ip address='${gateway}' netmask='255.255.255.0'>
    <dhcp>
      <range start='${prefix}.100' end='${prefix}.200'/>
XML
    case "$net" in
        nexus-cenadi-app)  echo "      <host mac='${MAC_APP}'      name='vm-app-gov'  ip='10.50.20.20'/>" >> "$xml" ;;
        nexus-cenadi-sens) echo "      <host mac='${MAC_ANTILOPE}' name='vm-antilope' ip='10.50.30.30'/>" >> "$xml" ;;
        nexus-cenadi-adm)  echo "      <host mac='${MAC_RSSI}'     name='vm-rssi'     ip='10.50.40.40'/>" >> "$xml" ;;
        nexus-cenadi-men)  echo "      <host mac='${MAC_MENACE}'   name='vm-menace'   ip='10.50.50.50'/>" >> "$xml" ;;
    esac
    cat >> "$xml" <<XML
    </dhcp>
  </ip>
</network>
XML
    virsh net-info "$net" >/dev/null 2>&1 && { virsh net-destroy "$net" 2>/dev/null || true; virsh net-undefine "$net" 2>/dev/null || true; }
    virsh net-define "$xml"; virsh net-start "$net"; virsh net-autostart "$net"
    printf "  ✓ %-20s %-16s %s\n" "$net" "$bridge" "$desc"
done

echo
echo "════════════════════════════════════════════════════════════════════"
echo "✓ 6 zones réseau CENADI créées (toutes isolées d'Internet)"
echo "════════════════════════════════════════════════════════════════════"
echo "  HÔTE = Cœur SOC souverain : 10.50.0.1 (virbr-cen-mgmt)"
echo "  vm-app-gov  10.50.20.20  | vm-antilope 10.50.30.30 (AIR-GAP)"
echo "  vm-rssi     10.50.40.40  | vm-menace   10.50.50.50"
echo
echo "  Suite : scripts/host-cenadi-configure.sh puis 02-vm-specs.md"
echo "════════════════════════════════════════════════════════════════════"
