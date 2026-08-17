#!/usr/bin/env bash
# =============================================================================
# CENADI : setup vm-menace (10.50.50.50) — poste bureautique compromis (Kali)
# =============================================================================
# Outils pour démontrer que même un poste interne compromis NE PEUT PAS
# atteindre la zone sensible (air-gap ANTILOPE), grâce aux règles OPNsense.
# =============================================================================
set -euo pipefail

echo "═══ Installation outils d'attaque ═══"
sudo apt-get update -qq
sudo apt-get install -y -qq nmap netcat-openbsd tcpdump curl

echo
echo "════════════════════════════════════════════════════════════════════"
echo "✓ Setup vm-menace terminé (poste compromis simulé, zone 50)"
echo "════════════════════════════════════════════════════════════════════"
echo
echo "  Démonstration du cloisonnement (à jouer pendant la démo) :"
echo
echo "  # 1. Tenter d'atteindre la zone SENSIBLE (doit ÉCHOUER — air-gap)"
echo "  nmap -Pn --max-retries 1 --host-timeout 5s 10.50.30.30"
echo "  ping -c 3 10.50.30.30"
echo
echo "  # 2. Tenter la zone applicative (doit ÉCHOUER)"
echo "  nmap -Pn 10.50.20.20"
echo
echo "  # 3. Internet (doit ÉCHOUER — datacenter hermétique)"
echo "  ping -c 3 8.8.8.8"
echo
echo "  → Toutes ces tentatives échouent : le poste compromis est piégé"
echo "    dans sa zone. La solde de l'État reste hors d'atteinte."
echo "════════════════════════════════════════════════════════════════════"
