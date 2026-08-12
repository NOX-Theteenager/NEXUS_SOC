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
LDAP_SOAR_PW=<affiché par le script>
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
