#Requires -RunAsAdministrator
# =============================================================================
# NEXUS SOC — Script d'installation de l'agent (Windows)
# Généré automatiquement par la console fournisseur.
# Exécuter dans PowerShell en tant qu'Administrateur :
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   .\Install-NexusAgent.ps1
# =============================================================================
param(
  [string]$NexusServer   = "{{SERVER_URL}}",
  [string]$NexusToken    = "{{BEARER_TOKEN}}",
  [string]$NexusHmacKey  = "{{HMAC_KEY}}",
  [string]$NexusTenantId = "{{TENANT_ID}}",
  [string]$NexusAgentId  = "{{AGENT_ID}}",
  [string]$NexusHostname = "{{HOSTNAME}}",
  [string]$NexusVersion  = "{{VERSION}}"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------------------- #
# Fonctions d'affichage
# --------------------------------------------------------------------------- #
function Write-Info    { param($msg) Write-Host "[NEXUS] $msg"    -ForegroundColor Cyan    }
function Write-Success { param($msg) Write-Host "[✓]    $msg"     -ForegroundColor Green   }
function Write-Warning { param($msg) Write-Host "[!]    $msg"     -ForegroundColor Yellow  }
function Write-Fail    { param($msg) Write-Host "[✗]    $msg"     -ForegroundColor Red; exit 1 }

# --------------------------------------------------------------------------- #
# Paramètres d'installation
# --------------------------------------------------------------------------- #
$InstallDir  = "$env:ProgramFiles\NexusSOC"
$ConfigDir   = "$env:ProgramData\NexusSOC"
$QueueDir    = "$env:ProgramData\NexusSOC\queue"
$LogDir      = "$env:ProgramData\NexusSOC\logs"
$BinaryPath  = "$InstallDir\nexusagent.exe"
$ConfigPath  = "$ConfigDir\config.json"
$ServiceName = "NexusSOCAgent"
$ServiceDisp = "NEXUS SOC Agent"

Write-Info "=== Installation de l'agent NEXUS SOC ==="
Write-Info "Tenant   : $NexusTenantId"
Write-Info "Hostname : $NexusHostname"
Write-Info "Serveur  : $NexusServer"

# --------------------------------------------------------------------------- #
# 1. Créer les répertoires
# --------------------------------------------------------------------------- #
Write-Info "Création des répertoires..."
@($InstallDir, $ConfigDir, $QueueDir, $LogDir) | ForEach-Object {
  if (-not (Test-Path $_)) { New-Item -ItemType Directory -Path $_ -Force | Out-Null }
}
Write-Success "Répertoires créés."

# --------------------------------------------------------------------------- #
# 2. Télécharger (ou utiliser la copie locale) le binaire
# --------------------------------------------------------------------------- #
$DownloadUrl = "$NexusServer/agent/download/$NexusVersion/windows/amd64/nexusagent.exe"
Write-Info "Téléchargement du binaire ($NexusVersion windows/amd64)..."

try {
  $Headers = @{ Authorization = "Bearer $NexusToken" }
  Invoke-WebRequest -Uri $DownloadUrl -Headers $Headers -OutFile "$BinaryPath.tmp" `
                    -UseBasicParsing -TimeoutSec 30
  Move-Item "$BinaryPath.tmp" $BinaryPath -Force
  Write-Success "Binaire installé dans $BinaryPath."
} catch {
  # Fallback : binaire inclus dans le pack offline
  $OfflineBin = Join-Path (Split-Path $MyInvocation.MyCommand.Path) "nexusagent.exe"
  if (Test-Path $OfflineBin) {
    Write-Warning "Téléchargement impossible — utilisation du binaire offline."
    Copy-Item $OfflineBin $BinaryPath -Force
    Write-Success "Binaire offline installé dans $BinaryPath."
  } else {
    Write-Fail "Impossible d'obtenir le binaire (réseau et offline tous deux indisponibles). Erreur : $_"
  }
}

# --------------------------------------------------------------------------- #
# 3. Écrire la configuration
# --------------------------------------------------------------------------- #
Write-Info "Écriture de la configuration..."
$Config = @{
  server_url   = "$NexusServer/ingest"
  enroll_token = $NexusToken
  hmac_key     = $NexusHmacKey
  agent_id     = $NexusAgentId
  tenant_id    = $NexusTenantId
  hostname     = $NexusHostname
  interval_sec = 30
  watch_dirs   = @("$env:USERPROFILE", "$env:TEMP", "$env:windir\System32\winevt\Logs")
  queue_dir    = $QueueDir
  queue_max_mb = 50
  tls_verify   = $true
} | ConvertTo-Json -Depth 3

Set-Content -Path $ConfigPath -Value $Config -Encoding UTF8

# Restreindre l'accès au fichier de config (lecture seule pour SYSTEM et Admins)
$Acl = Get-Acl $ConfigPath
$Acl.SetAccessRuleProtection($true, $false)
$Acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
  "SYSTEM", "FullControl", "Allow")))
$Acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule(
  "Administrators", "FullControl", "Allow")))
Set-Acl -Path $ConfigPath -AclObject $Acl
Write-Success "Configuration écrite dans $ConfigPath."

# --------------------------------------------------------------------------- #
# 4. Installer et démarrer le service Windows
# --------------------------------------------------------------------------- #
Write-Info "Installation du service Windows '$ServiceName'..."

# Supprimer une ancienne installation éventuelle
if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
  Write-Info "Service existant détecté — suppression..."
  Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
  & sc.exe delete $ServiceName | Out-Null
  Start-Sleep -Seconds 2
}

# Créer le service avec sc.exe (pas de dépendances externes comme NSSM)
$BinPathQuoted = "`"$BinaryPath`" -config `"$ConfigPath`""
& sc.exe create $ServiceName `
    binPath= $BinPathQuoted `
    start= auto `
    DisplayName= $ServiceDisp `
    obj= "LocalSystem" | Out-Null

& sc.exe description $ServiceName "Agent de sécurité NEXUS SOC — collecte la télémétrie et l'envoie vers le SOC." | Out-Null
& sc.exe failure $ServiceName reset= 86400 actions= restart/30000/restart/60000/restart/120000 | Out-Null

Start-Service -Name $ServiceName
Start-Sleep -Seconds 3

$Svc = Get-Service -Name $ServiceName
if ($Svc.Status -eq 'Running') {
  Write-Success "Service '$ServiceName' démarré avec succès."
} else {
  Write-Warning "Le service n'est pas en cours d'exécution. Statut : $($Svc.Status)"
  Write-Warning "Vérifier les logs : $LogDir"
}

# --------------------------------------------------------------------------- #
# 5. Vérifier le premier contact avec le serveur
# --------------------------------------------------------------------------- #
Write-Info "Vérification de la connexion au serveur (attente jusqu'à 60 s)..."
$Connected = $false
for ($i = 0; $i -lt 12; $i++) {
  try {
    $Headers = @{ Authorization = "Bearer $NexusToken" }
    Invoke-WebRequest -Uri "$NexusServer/health" -Headers $Headers `
                      -UseBasicParsing -TimeoutSec 5 | Out-Null
    $Connected = $true
    break
  } catch {
    Start-Sleep -Seconds 5
  }
}

if ($Connected) {
  Write-Success "Agent en contact avec le serveur NEXUS SOC."
} else {
  Write-Warning "Serveur injoignable après 60 s. Vérifiez le réseau et le token."
}

# --------------------------------------------------------------------------- #
# Résumé final
# --------------------------------------------------------------------------- #
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   Agent NEXUS SOC installé avec succès               ║" -ForegroundColor Green
Write-Host "╠══════════════════════════════════════════════════════╣" -ForegroundColor Green
Write-Host "║ Binaire  : $BinaryPath"
Write-Host "║ Config   : $ConfigPath"
Write-Host "║ Logs     : $LogDir"
Write-Host "║ Service  : Get-Service $ServiceName"
Write-Host "║ Arrêter  : Stop-Service $ServiceName"
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Warning "Ce token d'enrôlement est à usage unique. Ne pas le réutiliser."
