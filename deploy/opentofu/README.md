# Déploiement souverain NEXUS SOC — OpenTofu

Module d'infrastructure-as-code pour déployer la pile NEXUS SOC complète sur un
serveur souverain du CENADI, via SSH. Écrit en HCL et exécuté avec
[OpenTofu](https://opentofu.org/) (outil IaC libre et open source, licence MPL 2.0) afin
de garantir une chaîne d'outils 100 % open source.

## Prérequis

- OpenTofu >= 1.6 (`tofu version`)
- Un serveur cible SSH avec `sudo` (Ubuntu 22.04+ recommandé)
- Une clé SSH dédiée au déploiement

## Providers

`hashicorp/null`, `hashicorp/tls`, `hashicorp/local`, `hashicorp/random` —
compatibles OpenTofu sans modification.

## Utilisation

```bash
cd deploy/opentofu
cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars          # server_host, ssh_private_key_path, etc.
                               # institution_name et nexus_domain valent CENADI par défaut

ssh-keygen -t ed25519 -f ~/.ssh/nexus_deploy -C "nexus-soc-deploy"
ssh-copy-id -i ~/.ssh/nexus_deploy.pub ubuntu@<IP_SERVEUR>

tofu init          # télécharge les providers
tofu plan          # prévisualise
tofu apply         # déploie (~5–15 min)

# Secrets auto-générés
tofu output -raw postgres_password
tofu output -raw wazuh_admin_password
tofu output nexus_api_url
```

> OpenTofu lit les mêmes fichiers que Terraform (`*.tf`, `terraform.tfvars`,
> `terraform.tfstate`) : les noms de fichiers d'état et de variables sont
> conservés pour compatibilité. Seul l'exécutable change (`tofu` au lieu de
> `terraform`).
