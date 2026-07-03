#!/usr/bin/env bash
# =============================================================================
# NEXUS SOC LAB — Phase 1 : Réseau libvirt isolé
# =============================================================================
# Crée le réseau 'nexus-lab' : 10.42.0.0/24, ISOLÉ (aucun accès Internet).
# Ce réseau est la condition-clé du scénario Souveraineté : les VMs ne peuvent
# PAS joindre l'extérieur, donc aucune donnée client ne peut fuiter.
#
# Idempotent : peut être relancé plusieurs fois sans casser l'existant.
#
# Usage :
#   ./01-network-setup.sh              # crée le réseau
#   ./01-network-setup.sh --destroy    # supprime le réseau (avant modification)
#   ./01-network-setup.sh --status     # affiche l'état
# =============================================================================
set -euo pipefail

NET_NAME="nexus-lab"
NET_XML="/tmp/${NET_NAME}.xml"
NET_BRIDGE="virbr-lab"
NET_CIDR="10.42.0.0/24"
NET_GATEWAY="10.42.0.1"
NET_DHCP_START="10.42.0.100"
NET_DHCP_END="10.42.0.200"

# IPs statiques réservées via DHCP (matchées par MAC configurée dans virt-manager)
# Les MACs sont générées ici et à réutiliser lors de la création des VMs.
#
# ⚠  IMPORTANT : dans ce lab, LE HÔTE joue le rôle de SOC (10.42.0.1 = gateway).
#     Pas de vm-soc — on utilise la machine hôte Ubuntu qui a déjà
#     PostgreSQL, uvicorn (nexus-soc.service) et cloudflared configurés en systemd.
MAC_VM_CIBLE="52:54:00:aa:00:20"
MAC_VM_KALI="52:54:00:aa:00:30"
MAC_VM_DSI="52:54:00:aa:00:40"

IP_HOTE_SOC="10.42.0.1"       # gateway libvirt = hôte Ubuntu = serveur NEXUS SOC
IP_VM_CIBLE="10.42.0.20"
IP_VM_KALI="10.42.0.30"
IP_VM_DSI="10.42.0.40"

# ── Actions annexes ─────────────────────────────────────────────────────────

if [[ "${1:-}" == "--status" ]]; then
    echo "─── Réseaux libvirt actifs ───"
    virsh net-list --all
    if virsh net-info "$NET_NAME" >/dev/null 2>&1; then
        echo
        echo "─── Détail de $NET_NAME ───"
        virsh net-info "$NET_NAME"
        echo
        echo "─── Baux DHCP actifs ───"
        virsh net-dhcp-leases "$NET_NAME" 2>/dev/null || true
    fi
    exit 0
fi

if [[ "${1:-}" == "--destroy" ]]; then
    echo "⚠  Suppression du réseau $NET_NAME (les VMs qui l'utilisent seront déconnectées)"
    virsh net-destroy   "$NET_NAME" 2>/dev/null || true
    virsh net-undefine  "$NET_NAME" 2>/dev/null || true
    echo "✓ Réseau supprimé."
    exit 0
fi

# ── Vérifications préalables ────────────────────────────────────────────────

if ! command -v virsh >/dev/null 2>&1; then
    echo "✗ virsh introuvable. Exécuter d'abord : sudo apt install libvirt-clients"
    exit 1
fi

if ! groups | grep -qw libvirt; then
    echo "✗ L'utilisateur '$USER' n'est pas dans le groupe libvirt."
    echo "  Faire : sudo usermod -aG libvirt \$USER puis se reconnecter."
    exit 1
fi

# Détection de conflit d'IP sur le hôte
if ip -o addr show | grep -q "10.42.0"; then
    echo "✗ Une interface du hôte utilise déjà la plage 10.42.0.x :"
    ip -o addr show | grep "10.42.0"
    echo "  → Changer NET_CIDR dans ce script (ex. 10.43.0.0/24) et relancer."
    exit 1
fi

# ── Génération du XML libvirt ───────────────────────────────────────────────

cat > "$NET_XML" <<XML
<network>
  <name>${NET_NAME}</name>
  <bridge name='${NET_BRIDGE}' stp='on' delay='0'/>
  <!--
    NB : PAS de balise <forward .../> → réseau ISOLÉ.
    Les VMs se voient entre elles et voient le hôte via le bridge,
    mais ne peuvent PAS atteindre Internet (pas de NAT, pas de route sortie).
    C'est CE POINT qui rend le scénario Souveraineté démontrable.
  -->
  <domain name='minfi.local' localOnly='yes'/>
  <ip address='${NET_GATEWAY}' netmask='255.255.255.0'>
    <dhcp>
      <range start='${NET_DHCP_START}' end='${NET_DHCP_END}'/>
      <!-- Réservations DHCP → IP fixes prévisibles pour la démo -->
      <host mac='${MAC_VM_CIBLE}' name='vm-cible' ip='${IP_VM_CIBLE}'/>
      <host mac='${MAC_VM_KALI}'  name='vm-kali'  ip='${IP_VM_KALI}'/>
      <host mac='${MAC_VM_DSI}'   name='vm-dsi'   ip='${IP_VM_DSI}'/>
    </dhcp>
  </ip>
  <!-- DNS interne : les VMs résolvent soc.minfi.local vers le HÔTE (gateway) -->
  <dns>
    <host ip='${IP_HOTE_SOC}'>
      <hostname>soc.minfi.local</hostname>
      <hostname>api.soc.minfi.local</hostname>
      <hostname>portail.soc.minfi.local</hostname>
    </host>
  </dns>
</network>
XML

# ── Application ─────────────────────────────────────────────────────────────

# Si le réseau existe déjà et est actif → recharger sa config proprement
if virsh net-info "$NET_NAME" >/dev/null 2>&1; then
    echo "ℹ Réseau existant détecté — recréation propre..."
    virsh net-destroy  "$NET_NAME" 2>/dev/null || true
    virsh net-undefine "$NET_NAME" 2>/dev/null || true
fi

virsh net-define "$NET_XML"
virsh net-start  "$NET_NAME"
virsh net-autostart "$NET_NAME"

# ── Résumé ──────────────────────────────────────────────────────────────────

echo
echo "════════════════════════════════════════════════════════════════════"
echo "✓ Réseau '$NET_NAME' créé et actif."
echo "════════════════════════════════════════════════════════════════════"
echo
echo "  Bridge          : $NET_BRIDGE"
echo "  Subnet          : $NET_CIDR (ISOLÉ - aucun accès Internet)"
echo "  Gateway / SOC   : $NET_GATEWAY  ← le HÔTE Ubuntu joue le rôle de vm-soc"
echo
echo "  IPs et MACs réservées (à saisir dans virt-manager) :"
echo "  ┌──────────┬───────────────────┬───────────────────────┐"
echo "  │ HÔTE     │ ${IP_HOTE_SOC}      │ (gateway libvirt)     │"
echo "  │ vm-cible │ ${IP_VM_CIBLE}     │ ${MAC_VM_CIBLE}      │"
echo "  │ vm-kali  │ ${IP_VM_KALI}     │ ${MAC_VM_KALI}      │"
echo "  │ vm-dsi   │ ${IP_VM_DSI}     │ ${MAC_VM_DSI}      │"
echo "  └──────────┴───────────────────┴───────────────────────┘"
echo
echo "  DNS interne (résolu par les VMs) :"
echo "  soc.minfi.local          → ${IP_HOTE_SOC} (hôte)"
echo "  api.soc.minfi.local      → ${IP_HOTE_SOC}"
echo "  portail.soc.minfi.local  → ${IP_HOTE_SOC}"
echo
echo "Prochaine étape : lancer scripts/host-configure.sh sur le hôte"
echo "puis créer les 3 VMs (vm-cible, vm-kali, vm-dsi) selon 02-vm-specs.md"
echo "════════════════════════════════════════════════════════════════════"
