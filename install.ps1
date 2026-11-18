# phylax installer for Windows (PowerShell 5.1+/7). NOTE: written for Windows but not yet tested on a Windows machine.
$ErrorActionPreference = "Stop"
$Kit = Split-Path -Parent $MyInvocation.MyCommand.Path
function Have($c) { [bool](Get-Command $c -ErrorAction SilentlyContinue) }
function Ensure($cmd, $wingetId) {
  if (Have $cmd) { return }
  Write-Host "Installing $cmd via winget..."; winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  if (-not (Have $cmd)) { throw "$cmd installed but not on PATH yet. Open a NEW terminal and re-run install.ps1." }
}
Ensure "gum" "charmbracelet.gum"; Ensure "python" "Python.Python.3.12"; Ensure "rclone" "Rclone.Rclone"; Ensure "age" "FiloSottile.age"; Ensure "git" "Git.Git"
gum style --border rounded --padding "1 3" --border-foreground 212 "phylax setup" "Back up your Claude Code context to YOUR OWN Google Drive."

$Remote = "gdrive-phylax"
function Add-Project {
  $n = gum input --header "Project name (e.g. my-project)" --placeholder "my-project"; if (-not $n) { return $null }
  $d = gum input --header "Project folder (existing or new)" --value (Join-Path $HOME $n.ToLower())
  python "$Kit\phylax.py" init --name $n --dir $d --remote $Remote
  return $n
}
$Last = Add-Project; if (-not $Last) { exit 1 }
while (gum confirm "Add another project folder?") { $x = Add-Project; if ($x) { $Last = $x } else { break } }

if (-not ((rclone listremotes) -match "^$Remote`:")) {
  gum style --foreground 212 "A browser will open to authorize Google Drive (limited 'drive.file' scope)."
  rclone config create $Remote drive scope drive.file *> $null   # output hidden: contains tokens
}
gum style --foreground 2 "Google Drive connected"

$Cfg = Join-Path $env:APPDATA "phylax"; New-Item -ItemType Directory -Force $Cfg | Out-Null
$Id = Join-Path $Cfg "identity.txt"
if (-not (Test-Path $Id)) {
  age-keygen -o $Id 2>$null | Out-Null
  age-keygen -y $Id | Set-Content (Join-Path $Cfg "recipient.txt") -Encoding ascii
  icacls $Id /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
}
gum style --foreground 214 "IMPORTANT: save your private key in your password manager NOW." "Without it, encrypted backups can't be restored."
if (gum confirm "Copy the private key to the clipboard now? (not displayed)") { Get-Content $Id -Raw | Set-Clipboard; Write-Host "Copied. Paste into your password manager, then clear the clipboard (Win+V)." }

if ((Have "gh") -and (gum confirm "Create a PRIVATE GitHub repo for this project folder (your own account) so it is backed up with git?")) {
  gh auth status *> $null; if ($LASTEXITCODE -ne 0) { gh auth login }
  python "$Kit\phylax.py" git-init -p $Last
}
python "$Kit\phylax.py" schedule install
if (gum confirm "Install the team status line (ccstatusline) with the sync indicator?") { python "$Kit\phylax.py" statusline }
python "$Kit\phylax.py" sync --all
gum style --border double --padding "0 2" --foreground 2 "Done! Open the menu any time:  $Kit\phylax.ps1"
