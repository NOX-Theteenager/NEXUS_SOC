# Annuaire souverain — rendre `freeze_account` exécutable

Le seul verrou qu'aucune topologie réseau ne peut lever. Un routeur transporte,
un annuaire authentifie : aucun câble ne suspend une identité.

---

## 1. Pourquoi c'est nécessaire

`vm-app-gov` porte déjà le rôle « annuaire, messagerie » dans
[README.md](README.md#L104) — mais comme **rôle documenté**, pas comme service
déployé. Aucun annuaire n'existe dans le lab : chaque mention d'AD ou de LDAP
dans le dépôt est une note d'intention.

Conséquence : `freeze_account` n'a rien à geler. Même avec un connecteur parfait,
il n'y aurait aucune identité à modifier.

---

## 2. Déploiement

```bash
scp lab-cenadi/scripts/vm-app-gov-annuaire.sh cenadi@10.50.20.20:/tmp/
ssh cenadi@10.50.20.20 'sudo bash /tmp/vm-app-gov-annuaire.sh'
```

Le script est idempotent. Il installe OpenLDAP, active la surcouche `ppolicy`,
crée l'arborescence, trois comptes de démonstration et un compte de service pour
NEXUS. Il affiche en fin d'exécution les identifiants à reporter dans le `.env`
du cœur SOC.

### Choix techniques, et leurs raisons

**Le gel passe par `pwdAccountLockedTime`, pas par une suppression.** Un compte
gelé refuse l'authentification mais reste présent et lisible. On suspend un
accès sans détruire une trace d'enquête — c'est la différence entre contenir un
incident et effacer les preuves qui permettront de le qualifier.

**Le compte de service ne peut écrire que cet attribut.** Les ACL le limitent à
`pwdAccountLockedTime` ; il lit le reste, ne crée rien, ne supprime rien. Un
SOAR compromis ne doit pas pouvoir vider un annuaire.

**`ppolicy` plutôt que `nsAccountLock`.** `nsAccountLock` appartient à 389-DS et
FreeIPA ; sur OpenLDAP il n'aurait aucun effet — l'attribut serait accepté puis
ignoré. Le compte paraîtrait gelé sans l'être.

**L'écoute est restreinte à 10.50.20.20.** L'annuaire n'est pas exposé au-delà
de la zone applicative, et la matrice de flux du §2 de l'architecture n'autorise
que le cœur SOC à l'atteindre.

---

## 3. Identifiants des comptes

Le Modèle 2 produit des entités de la forme `agent_<PERIMETRE>_<matricule>` à
partir des journaux applicatifs. Les `uid` de l'annuaire suivent exactement cette
convention — sans quoi le connecteur chercherait un compte introuvable.

| uid | Périmètre |
|---|---|
| `agent_SIGIPES_0421` | SIGIPES |
| `agent_SIGIPES_0198` | SIGIPES |
| `agent_ANTILOPE_0733` | ANTILOPE |

Une entité préfixée `hote_` ne correspond à **aucun** compte : ce sont des
agrégats de machine. La console refuse désormais de proposer un gel sur ce
type de cible.

---

## 4. Commandes

**Geler** — c'est ce que la console affiche après approbation :

```bash
ldapmodify -x -D "cn=nexus-soar,ou=services,dc=cenadi,dc=local" -W <<'EOF'
dn: uid=agent_SIGIPES_0421,ou=agents,dc=cenadi,dc=local
changetype: modify
replace: pwdAccountLockedTime
pwdAccountLockedTime: 000001010000Z
EOF
```

**Dégeler** — la réversibilité que la console annonce :

```bash
ldapmodify -x -D "cn=nexus-soar,ou=services,dc=cenadi,dc=local" -W <<'EOF'
dn: uid=agent_SIGIPES_0421,ou=agents,dc=cenadi,dc=local
changetype: modify
delete: pwdAccountLockedTime
EOF
```

**Vérifier l'effet réel** — l'authentification doit échouer :

```bash
ldapwhoami -x -D "uid=agent_SIGIPES_0421,ou=agents,dc=cenadi,dc=local" -w 'Cenadi@2026'
# avant gel : dn:uid=agent_SIGIPES_0421,...
# après gel : ldap_bind: Invalid credentials (49)
```

C'est cette dernière commande qui fait la démonstration. Le reste n'est que
configuration ; ici, on voit un accès réellement refusé.

---

## 5. Configuration du cœur SOC

Reporter dans `.env`, puis redémarrer `nexus-soc.service` :

```bash
LDAP_URI=ldap://10.50.20.20:389
LDAP_BASE_DN=dc=cenadi,dc=local
LDAP_SOAR_DN=cn=nexus-soar,ou=services,dc=cenadi,dc=local
LDAP_SOAR_PASSWORD=<affiché par le script>
```

`LDAP_BASE_DN` et `LDAP_SOAR_DN` alimentent la commande affichée par la console.
Sans eux, elle retombe sur les valeurs par défaut ci-dessus.

> **Piège connu** : pas de commentaire en fin de ligne dans `.env`. Sous systemd,
> il est lu comme faisant partie de la valeur.

---

## 6. Une fois le connecteur raccordé

Aujourd'hui la console affiche la commande et enregistre qui déclare l'avoir
passée. Le connecteur remplacera cette étape, avec deux règles :

1. **Vérifier l'effet, pas le code de retour.** `ldapmodify` peut réussir sur un
   attribut sans effet réel. Le connecteur doit rejouer un `ldapwhoami` et
   confirmer l'échec d'authentification avant de marquer l'exécution
   `automatique`.
2. **Ne jamais élargir les droits du compte de service.** Si une action réclame
   plus que `pwdAccountLockedTime`, c'est l'action qu'il faut revoir.

---

## 7. Déployé le 28 août 2026

L'annuaire tourne sur vm-app-gov et répond au cœur SOC. Les identifiants
générés à l'installation sont dans le `.env` de la racine (`LDAP_URI`,
`LDAP_BASE_DN`, `LDAP_SOAR_DN`, `LDAP_SOAR_PASSWORD`), fichier ignoré par git.

> **Nom de variable.** Le gabarit versionné `.env.example` dit
> `LDAP_SOAR_PASSWORD` ; ce document disait `LDAP_SOAR_PW`. Deux noms pour la
> même chose finissent toujours par diverger : tout est aligné sur celui du
> gabarit. Le script d'installation et la recette acceptent encore l'ancien nom
> en repli.

### 7.1 Installer sans Internet, sans percer la matrice de flux

La zone applicative n'a pas de sortie — sa matrice n'autorise que la résolution
de noms vers sa passerelle et la télémétrie vers le cœur SOC. `apt-get install
slapd` ne pouvait donc pas aboutir.

Ouvrir une sortie pour la commodité d'un installateur aurait défait
l'architecture que ce lab existe pour démontrer. Le cœur SOC sert de point de
distribution logicielle, comme dans tout système d'information cloisonné :

```bash
bash lab-cenadi/scripts/paquets-hors-ligne.sh noxtheteenager@10.50.20.20 slapd ldap-utils
scp lab-cenadi/scripts/vm-app-gov-annuaire.sh noxtheteenager@10.50.20.20:/tmp/
ssh noxtheteenager@10.50.20.20 'sudo bash /tmp/vm-app-gov-annuaire.sh'
```

Le calcul des dépendances mérite un mot : l'hôte est en 24.04, la machine cible
en 22.04. Résoudre sur l'hôte aurait produit les mauvaises versions. Le script
récupère donc l'état dpkg **réel** de la cible et fait résoudre `apt` contre lui,
dans une racine séparée pointant sur les dépôts de la cible. Six paquets, deux
mégaoctets : uniquement ce qui manquait.

Le script d'annuaire installe depuis `/tmp/nexus-debs` s'il y trouve des paquets,
et retombe sur `apt-get` sinon. Il reste donc utilisable tel quel dans une zone
qui aurait une sortie.

### 7.2 La recette

```bash
export LDAP_SOAR_PASSWORD=…
bash lab-cenadi/scenarios/07-preuve-gel-annuaire.sh
```

**7 contrôles sur 7.** Elle ne conclut jamais sur le code de retour de
`ldapmodify` — un attribut peut être accepté puis ignoré, c'est exactement le
piège de `nsAccountLock` sur OpenLDAP. Elle rejoue une authentification.

| Étape | Authentification | Lecture du compte |
|---|---|---|
| Avant | passe | passe |
| **Gelé** | **refusée, code 49** | **passe** |
| Après dégel | passe | passe |

La deuxième colonne compte autant que la première : le compte gelé reste lisible.
On suspend un accès, on ne détruit pas une trace d'enquête.

La recette porte aussi un **contrôle négatif**, et c'est peut-être le plus utile
à l'oral : avec les identifiants du compte de service, supprimer un compte et
changer un mot de passe échouent tous deux en **code 50, accès insuffisant**. Le
périmètre du SOAR n'est pas une intention écrite dans un document, c'est une ACL
qui refuse.
