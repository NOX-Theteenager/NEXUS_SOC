#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Phase 1 : Réseaux libvirt multi-VLAN pour GNS3
# =============================================================================
# Crée les 4 réseaux libvirt nécessaires à l'architecture GNS3 fusionnée :
#
#   1. nexus-mgmt   (10.42.0.0/24)   — HÔTE SOC ↔ GNS3 (management)
#   2. nexus-vlan10 (10.42.10.0/24)  — Client Afriland (VLAN 10)
#   3. nexus-vlan20 (10.42.20.0/24)  — Client UBA      (VLAN 20)
#   4. nexus-vlan30 (10.42.30.0/24)  — Attaquant externe (VLAN 30)
#
# Chaque réseau est ISOLÉ (pas de <forward>) : c'est le routeur MikroTik
# (dans GNS3) qui gère le routage inter-VLAN + les ACLs.
#
# Idempotent : peut être relancé sans casser l'existant.
#
# Usage :
#   ./01-network-setup.sh              # crée les 4 réseaux
#   ./01-network-setup.sh --destroy    # supprime les 4 réseaux
#   ./01-network-setup.sh --status     # affiche l'état
# =============================================================================
set -euo pipefail

# ── Configuration des réseaux ───────────────────────────────────────────────
declare -A NETWORKS=(
    [nexus-mgmt]="virbr-mgmt|10.42.0.0/24|10.42.0.1|Management (HÔTE SOC + GNS3)"
    [nexus-vlan10]="virbr-vlan10|10.42.10.0/24|10.42.10.1|VLAN 10 (Client Afriland)"
    [nexus-vlan20]="virbr-vlan20|10.42.20.0/24|10.42.20.1|VLAN 20 (Client UBA)"
    [nexus-vlan30]="virbr-vlan30|10.42.30.0/24|10.42.30.1|VLAN 30 (Attaquant externe)"
)

# Réservations MAC → IP fixes (à utiliser à la création des VMs)
MAC_VM_CIBLE="52:54:00:aa:00:20"      # → 10.42.10.20 (VLAN 10 Afriland)
MAC_VM_DSI="52:54:00:aa:00:40"        # → 10.42.10.40 (VLAN 10 Afriland)
MAC_VM_CIBLEB="52:54:00:aa:00:50"     # → 10.42.20.20 (VLAN 20 UBA)
MAC_VM_KALI="52:54:00:aa:00:30"       # → 10.42.30.30 (VLAN 30 external)

# ── Actions annexes ─────────────────────────────────────────────────────────

if [[ "${1:-}" == "--status" ]]; then
    echo "─── Réseaux libvirt actifs ───"
    virsh net-list --all
    for net in "${!NETWORKS[@]}"; do
        if virsh net-info "$net" >/dev/null 2>&1; then
            echo; echo "─── $net ───"
            virsh net-info "$net" | grep -E "Name|Active|Bridge"
            virsh net-dhcp-leases "$net" 2>/dev/null | head -8
        fi
    done
    exit 0
fi

if [[ "${1:-}" == "--destroy" ]]; then
    for net in "${!NETWORKS[@]}"; do
        echo "⚠  Suppression de $net"
        virsh net-destroy   "$net" 2>/dev/null || true
        virsh net-undefine  "$net" 2>/dev/null || true
    done
    # Compat : ancien réseau du lab d'avant fusion GNS3
    virsh net-destroy   "nexus-lab" 2>/dev/null || true
    virsh net-undefine  "nexus-lab" 2>/dev/null || true
    echo "✓ Réseaux supprimés."
    exit 0
fi

# ── Vérifications préalables ────────────────────────────────────────────────
if ! command -v virsh >/dev/null; then
    echo "✗ virsh introuvable. Exécuter d'abord : sudo apt install libvirt-clients"
    exit 1
fi

if ! groups | grep -qw libvirt; then
    echo "✗ L'utilisateur '$USER' n'est pas dans le groupe libvirt."
    echo "  sudo usermod -aG libvirt \$USER puis se reconnecter."
    exit 1
fi

# Détection de conflit d'IP sur le hôte
for cidr in "10.42.0" "10.42.10" "10.42.20" "10.42.30"; do
    if ip -o addr show 2>/dev/null | grep -q "$cidr\."; then
        # OK si c'est déjà l'un de nos bridges (idempotence)
        BRIDGE_MATCH=$(ip -o addr show | grep "$cidr\." | grep -oE "virbr-[a-z0-9]+" | head -1)
        if [[ -z "$BRIDGE_MATCH" || ! "$BRIDGE_MATCH" =~ ^virbr- ]]; then
            echo "✗ Une interface du hôte utilise déjà $cidr.x :"
            ip -o addr show | grep "$cidr\."
            echo "  → Éditer le script pour changer les CIDR ($cidr → 10.43.$cidr par ex.)"
            exit 1
        fi
    fi
done

# ── Création idempotente de chaque réseau ───────────────────────────────────
for net in "${!NETWORKS[@]}"; do
    IFS='|' read -r bridge cidr gateway description <<< "${NETWORKS[$net]}"
    prefix="${cidr%.*}"                            # ex : 10.42.10
    dhcp_start="${prefix}.100"
    dhcp_end="${prefix}.200"

    # Génération XML
    xml="/tmp/${net}.xml"
    cat > "$xml" <<XML
<network>
  <name>${net}</name>
  <bridge name='${bridge}' stp='on' delay='0'/>
  <!-- ISOLÉ : pas de forward → routage inter-VLAN passe par MikroTik dans GNS3 -->
  <domain name='nexus.local' localOnly='yes'/>
  <ip address='${gateway}' netmask='255.255.255.0'>
    <dhcp>
      <range start='${dhcp_start}' end='${dhcp_end}'/>
XML

    # Ajouter les réservations MAC/IP spécifiques par VLAN
    case "$net" in
        nexus-vlan10)
            cat >> "$xml" <<XML
      <host mac='${MAC_VM_CIBLE}' name='vm-cible' ip='10.42.10.20'/>
      <host mac='${MAC_VM_DSI}'   name='vm-dsi'   ip='10.42.10.40'/>
XML
            ;;
        nexus-vlan20)
            cat >> "$xml" <<XML
      <host mac='${MAC_VM_CIBLEB}' name='vm-cibleB' ip='10.42.20.20'/>
XML
            ;;
        nexus-vlan30)
            cat >> "$xml" <<XML
      <host mac='${MAC_VM_KALI}' name='vm-kali' ip='10.42.30.30'/>
XML
            ;;
    esac

    cat >> "$xml" <<XML
    </dhcp>
  </ip>
</network>
XML

    # (Ré)appliquer
    if virsh net-info "$net" >/dev/null 2>&1; then
        virsh net-destroy  "$net" 2>/dev/null || true
        virsh net-undefine "$net" 2>/dev/null || true
    fi
    virsh net-define    "$xml"
    virsh net-start     "$net"
    virsh net-autostart "$net"
    printf "  ✓ %-15s %-25s %s\n" "$net" "$bridge" "$description"
done

# ── Résumé ──────────────────────────────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════════════════"
echo "✓ 4 réseaux libvirt créés — prêts pour la topologie GNS3"
echo "════════════════════════════════════════════════════════════════════"
echo
echo "  Réservations IP fixes (à saisir dans virt-manager comme MAC forcé) :"
echo "  ┌──────────┬────────────────┬──────────────┬─────────────────────┐"
echo "  │ vm-cible │ 10.42.10.20    │ vlan10       │ ${MAC_VM_CIBLE} │"
echo "  │ vm-dsi   │ 10.42.10.40    │ vlan10       │ ${MAC_VM_DSI} │"
echo "  │ vm-cibleB│ 10.42.20.20    │ vlan20       │ ${MAC_VM_CIBLEB} │"
echo "  │ vm-kali  │ 10.42.30.30    │ vlan30       │ ${MAC_VM_KALI} │"
echo "  │ HÔTE     │ 10.42.0.1      │ mgmt         │ (gateway libvirt)   │"
echo "  └──────────┴────────────────┴──────────────┴─────────────────────┘"
echo
echo "  Prochaines étapes :"
echo "    1. Ouvrir GNS3 et suivre 03-gns3-architecture.md"
echo "    2. Câbler les 4 Cloud nodes vers les bridges ci-dessus"
echo "    3. Exécuter scripts/host-configure.sh"
echo "    4. Créer les VMs (02-vm-specs.md)"
echo "════════════════════════════════════════════════════════════════════"
