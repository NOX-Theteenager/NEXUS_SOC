#!/usr/bin/env bash
# =============================================================================
#  NEXUS SOC — Annuaire LDAP souverain sur vm-app-gov
#
#    scp lab-cenadi/scripts/vm-app-gov-annuaire.sh cenadi@10.50.20.20:/tmp/
#    ssh cenadi@10.50.20.20 'sudo bash /tmp/vm-app-gov-annuaire.sh'
#
#  Déploie un OpenLDAP minimal qui donne au SOAR une identité réelle à geler.
#  Sans lui, « freeze_account » n'a aucune cible : c'est le seul verrou que la
#  topologie réseau ne peut pas lever, parce qu'un annuaire n'est pas du réseau.
#
#  CHOIX TECHNIQUE — le gel se fait par `pwdAccountLockedTime` (surcouche ppolicy,
#  standard OpenLDAP), pas par `nsAccountLock` qui est propre à 389-DS/FreeIPA.
#  Un compte gelé refuse l'authentification MAIS reste présent et lisible : on
#  suspend un accès, on ne détruit pas une trace d'enquête.
#
#  Idempotent : relançable sans effet de bord.
# =============================================================================
set -euo pipefail

DOMAINE="cenadi.local"
BASE_DN="dc=cenadi,dc=local"
ORG="CENADI"
ADMIN_PW="${LDAP_ADMIN_PW:-}"

if [[ $EUID -ne 0 ]]; then echo "À exécuter avec sudo." >&2; exit 1; fi

if [[ -z "$ADMIN_PW" ]]; then
    ADMIN_PW="$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | head -c 20)"
    echo "→ Mot de passe admin généré (à conserver) : $ADMIN_PW"
fi

# ── 1. Installation non interactive ─────────────────────────────────────────
export DEBIAN_FRONTEND=noninteractive
debconf-set-selections <<EOF
slapd slapd/no_configuration boolean false
slapd slapd/domain string $DOMAINE
slapd shared/organization string $ORG
slapd slapd/password1 password $ADMIN_PW
slapd slapd/password2 password $ADMIN_PW
slapd slapd/backend select MDB
slapd slapd/purge_database boolean false
slapd slapd/move_old_database boolean true
EOF

apt-get update -qq
apt-get install -y -qq slapd ldap-utils

# ── 2. Politique de mots de passe : c'est elle qui porte le gel ──────────────
if ! ldapsearch -Y EXTERNAL -H ldapi:/// -b cn=config -LLL \
       "(olcOverlay=ppolicy)" dn 2>/dev/null | grep -q ppolicy; then
    ldapadd -Y EXTERNAL -H ldapi:/// -Q <<'EOF'
dn: cn=module{0},cn=config
changetype: modify
add: olcModuleLoad
olcModuleLoad: ppolicy
EOF
    ldapadd -Y EXTERNAL -H ldapi:/// -Q <<EOF
dn: olcOverlay=ppolicy,olcDatabase={1}mdb,cn=config
objectClass: olcOverlayConfig
objectClass: olcPPolicyConfig
olcOverlay: ppolicy
olcPPolicyDefault: cn=default,ou=policies,$BASE_DN
EOF
    echo "→ Surcouche ppolicy activée."
else
    echo "→ ppolicy déjà active, rien à faire."
fi

# ── 3. Arborescence ─────────────────────────────────────────────────────────
ldapadd -x -D "cn=admin,$BASE_DN" -w "$ADMIN_PW" -c <<EOF || true
dn: ou=agents,$BASE_DN
objectClass: organizationalUnit
ou: agents

dn: ou=policies,$BASE_DN
objectClass: organizationalUnit
ou: policies

dn: ou=services,$BASE_DN
objectClass: organizationalUnit
ou: services

dn: cn=default,ou=policies,$BASE_DN
objectClass: pwdPolicy
objectClass: device
cn: default
pwdAttribute: userPassword
pwdLockout: TRUE
pwdMaxFailure: 5
pwdLockoutDuration: 0
EOF

# ── 4. Comptes de démonstration ─────────────────────────────────────────────
# Les identifiants correspondent aux entités que le Modèle 2 produit sur les
# journaux applicatifs (agent_<PERIMETRE>_<matricule>).
for uid in agent_SIGIPES_0421 agent_SIGIPES_0198 agent_ANTILOPE_0733; do
    ldapadd -x -D "cn=admin,$BASE_DN" -w "$ADMIN_PW" <<EOF 2>/dev/null || true
dn: uid=$uid,ou=agents,$BASE_DN
objectClass: inetOrgPerson
uid: $uid
cn: $uid
sn: ${uid#agent_}
userPassword: $(slappasswd -s "Cenadi@2026")
description: Compte applicatif de démonstration — périmètre supervisé
EOF
done

# ── 5. Compte de service pour NEXUS ─────────────────────────────────────────
# Il peut modifier pwdAccountLockedTime, rien d'autre : le SOAR n'a pas besoin
# de créer ni de supprimer des comptes, et ne doit pas pouvoir le faire.
SOAR_PW="${LDAP_SOAR_PW:-$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | head -c 20)}"
ldapadd -x -D "cn=admin,$BASE_DN" -w "$ADMIN_PW" <<EOF 2>/dev/null || true
dn: cn=nexus-soar,ou=services,$BASE_DN
objectClass: organizationalRole
objectClass: simpleSecurityObject
cn: nexus-soar
userPassword: $(slappasswd -s "$SOAR_PW")
description: Compte de service NEXUS SOC — gel et dégel de comptes uniquement
EOF

ldapmodify -Y EXTERNAL -H ldapi:/// -Q <<EOF
dn: olcDatabase={1}mdb,cn=config
changetype: modify
replace: olcAccess
olcAccess: {0}to attrs=userPassword,shadowLastChange
  by self write
  by anonymous auth
  by dn="cn=admin,$BASE_DN" write
  by * none
olcAccess: {1}to attrs=pwdAccountLockedTime
  by dn="cn=nexus-soar,ou=services,$BASE_DN" write
  by dn="cn=admin,$BASE_DN" write
  by * read
olcAccess: {2}to *
  by dn="cn=admin,$BASE_DN" write
  by dn="cn=nexus-soar,ou=services,$BASE_DN" read
  by * read
EOF

# ── 6. Écoute restreinte au cœur SOC et à la machine elle-même ──────────────
sed -i 's|^SLAPD_SERVICES=.*|SLAPD_SERVICES="ldap://10.50.20.20:389/ ldapi:///"|' \
    /etc/default/slapd 2>/dev/null || true
systemctl restart slapd
systemctl enable slapd >/dev/null 2>&1

cat <<EOF

═══════════════════════════════════════════════════════════════════════════
  Annuaire déployé — $BASE_DN

  Admin        : cn=admin,$BASE_DN
  Mot de passe : $ADMIN_PW
  Service SOAR : cn=nexus-soar,ou=services,$BASE_DN
  Mot de passe : $SOAR_PW

  À reporter dans le .env du cœur SOC :
      LDAP_URI=ldap://10.50.20.20:389
      LDAP_BASE_DN=$BASE_DN
      LDAP_SOAR_DN=cn=nexus-soar,ou=services,$BASE_DN
      LDAP_SOAR_PW=$SOAR_PW

  Vérifier :
      ldapsearch -x -H ldap://10.50.20.20 -b ou=agents,$BASE_DN uid
═══════════════════════════════════════════════════════════════════════════
EOF
