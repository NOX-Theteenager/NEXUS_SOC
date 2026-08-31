#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — CENADI : livrer des paquets à une zone sans Internet
#
#      bash lab-cenadi/scripts/paquets-hors-ligne.sh <user@ip> <paquet…>
#      bash lab-cenadi/scripts/paquets-hors-ligne.sh noxtheteenager@10.50.20.20 slapd ldap-utils
#
#  POURQUOI
#  --------
#  La zone applicative n'a pas d'accès Internet, et c'est voulu : sa matrice de
#  flux n'autorise que la résolution de noms vers sa passerelle et la télémétrie
#  vers le cœur SOC. Installer un paquet ne doit donc PAS passer par l'ouverture
#  d'une sortie — ce serait défaire l'architecture pour la commodité d'un apt.
#
#  Le cœur SOC sert de point de distribution logicielle. C'est exactement ainsi
#  que fonctionne un système d'information cloisonné : une zone de confiance
#  reçoit les mises à jour et les redistribue, le reste ne parle à personne.
#
#  COMMENT LES DÉPENDANCES SONT CALCULÉES
#  --------------------------------------
#  L'hôte est en 24.04, la machine cible en 22.04 : résoudre sur l'hôte
#  donnerait les mauvaises versions. On récupère donc l'état dpkg RÉEL de la
#  cible et on fait résoudre apt contre lui, dans une racine séparée pointant
#  sur les dépôts de la cible. Résultat : uniquement ce qui lui manque, dans les
#  versions qu'elle attend.
# =============================================================================
set -uo pipefail

CIBLE="${1:-}"; shift || true
PAQUETS=("$@")
[[ -z "$CIBLE" || ${#PAQUETS[@]} -eq 0 ]] && {
  echo "usage : $0 <user@ip> <paquet…>" >&2; exit 2; }

CLE="${CLE_SSH:-$HOME/.ssh/id_ed25519}"
SSH=(ssh -o BatchMode=yes -o IdentitiesOnly=yes -i "$CLE"
     -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10)
RACINE="/var/tmp/nexus-apt-cible"
GREEN="\033[32m"; RED="\033[31m"; BOLD="\033[1m"; RAZ="\033[0m"

echo -e "${BOLD}Livraison hors ligne vers ${CIBLE}${RAZ}"

# ── 1. Quelle distribution, et que possède-t-elle déjà ? ────────────────────
NOM_CODE=$("${SSH[@]}" "$CIBLE" '. /etc/os-release; echo $VERSION_CODENAME' 2>/dev/null | tr -d '\r')
ARCH=$("${SSH[@]}" "$CIBLE" 'dpkg --print-architecture' 2>/dev/null | tr -d '\r')
[[ -z "$NOM_CODE" ]] && { echo -e "${RED}✗ machine injoignable par clé${RAZ}"; exit 1; }
echo "  cible : $NOM_CODE/$ARCH"

rm -rf "$RACINE"
mkdir -p "$RACINE"/{etc/apt/apt.conf.d,etc/apt/preferences.d,etc/apt/trusted.gpg.d} \
         "$RACINE"/var/lib/apt/lists/partial "$RACINE"/var/cache/apt/archives/partial \
         "$RACINE"/var/lib/dpkg "$RACINE"/sortie

# L'état dpkg de la cible : sans lui, apt téléchargerait toute la base du
# système, y compris la libc — qu'on n'a aucune raison de réinstaller.
if ! scp -q -o BatchMode=yes -o IdentitiesOnly=yes -i "$CLE" \
     -o StrictHostKeyChecking=accept-new \
     "$CIBLE:/var/lib/dpkg/status" "$RACINE/var/lib/dpkg/status" 2>/dev/null; then
  echo -e "${RED}✗ impossible de lire l'état dpkg de la cible${RAZ}"; exit 1
fi
echo "  état dpkg relu : $(grep -c '^Package:' "$RACINE/var/lib/dpkg/status") paquets installés"

cat > "$RACINE/etc/apt/sources.list" <<EOF
deb http://archive.ubuntu.com/ubuntu $NOM_CODE main universe
deb http://archive.ubuntu.com/ubuntu $NOM_CODE-updates main universe
deb http://security.ubuntu.com/ubuntu $NOM_CODE-security main universe
EOF
cp /etc/apt/trusted.gpg.d/*.gpg "$RACINE/etc/apt/trusted.gpg.d/" 2>/dev/null
cp -r /usr/share/keyrings "$RACINE/usr-keyrings" 2>/dev/null

OPT=(-o "Dir=$RACINE"
     -o "Dir::State::status=$RACINE/var/lib/dpkg/status"
     -o "Dir::Etc::sourcelist=$RACINE/etc/apt/sources.list"
     -o "Dir::Etc::sourceparts=$RACINE/etc/apt/sources.list.d"
     -o "Dir::Cache::archives=$RACINE/var/cache/apt/archives"
     -o "Dir::Etc::trusted=/etc/apt/trusted.gpg"
     -o "Dir::Etc::trustedparts=/etc/apt/trusted.gpg.d"
     -o "APT::Architecture=$ARCH"
     -o "APT::Get::AllowUnauthenticated=false"
     -o "Debug::NoLocking=1")

echo "  interrogation des dépôts…"
if ! apt-get "${OPT[@]}" update -qq 2>"$RACINE/erreurs.txt"; then
  echo -e "${RED}✗ mise à jour des index refusée${RAZ}"; tail -4 "$RACINE/erreurs.txt"; exit 1
fi

echo "  résolution des dépendances manquantes…"
apt-get "${OPT[@]}" install -y --download-only --no-install-recommends \
        "${PAQUETS[@]}" >"$RACINE/resolution.txt" 2>&1 || {
  echo -e "${RED}✗ résolution impossible${RAZ}"; tail -8 "$RACINE/resolution.txt"; exit 1; }

mapfile -t DEBS < <(find "$RACINE/var/cache/apt/archives" -maxdepth 1 -name '*.deb')
[[ ${#DEBS[@]} -eq 0 ]] && { echo "  rien à livrer : la cible a déjà tout."; exit 0; }
printf "  %d paquet(s), %s\n" "${#DEBS[@]}" \
       "$(du -ch "${DEBS[@]}" 2>/dev/null | tail -1 | cut -f1)"

# ── 2. Livraison ────────────────────────────────────────────────────────────
"${SSH[@]}" "$CIBLE" 'rm -rf /tmp/nexus-debs && mkdir -p /tmp/nexus-debs' || exit 1
if ! scp -q -o BatchMode=yes -o IdentitiesOnly=yes -i "$CLE" \
     -o StrictHostKeyChecking=accept-new "${DEBS[@]}" "$CIBLE:/tmp/nexus-debs/"; then
  echo -e "${RED}✗ copie interrompue${RAZ}"; exit 1
fi
echo -e "  ${GREEN}✓${RAZ} déposés dans /tmp/nexus-debs sur la cible"
cat <<EOF

Installation, sur la cible et en root :
    dpkg -i /tmp/nexus-debs/*.deb
EOF
