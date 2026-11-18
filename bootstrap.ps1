# phylax one-line installer for Windows (PowerShell):
#   irm https://github.com/agentnetes/phylax/releases/latest/download/bootstrap.ps1 | iex
$ErrorActionPreference = "Stop"
$Repo = if ($env:PHYLAX_REPO) { $env:PHYLAX_REPO } else { "agentnetes/phylax" }
$Base = if ($env:PHYLAX_BASE) { $env:PHYLAX_BASE } else { "https://github.com/$Repo/releases/latest/download" }
$Dest = Join-Path $env:LOCALAPPDATA "phylax"; $Bin = Join-Path $Dest "bin"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Write-Host "Installing Python via winget…"; winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User")
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Python installed but not on PATH yet. Open a NEW PowerShell window and run the one-liner again." }
}
$T = Join-Path $env:TEMP ("phylax-" + [guid]::NewGuid()); New-Item -ItemType Directory $T | Out-Null
Write-Host "Downloading phylax…"
Invoke-WebRequest "$Base/phylax.zip" -OutFile "$T\k.zip" -UseBasicParsing; Invoke-WebRequest "$Base/phylax.zip.sha256" -OutFile "$T\k.sha" -UseBasicParsing
$want = ((Get-Content "$T\k.sha" -Raw).Trim() -split "\s+")[0].ToLower(); $got = (Get-FileHash "$T\k.zip" -Algorithm SHA256).Hash.ToLower()
if ($want -ne $got) { throw "Checksum mismatch - aborting (nothing installed)." }
Expand-Archive "$T\k.zip" "$T\x" -Force; $src = (Get-ChildItem "$T\x" | Select-Object -First 1).FullName
Remove-Item $Dest -Recurse -Force -ErrorAction SilentlyContinue; Move-Item $src $Dest
New-Item -ItemType Directory $Bin -Force | Out-Null
Set-Content "$Bin\phylax.cmd" ("@echo off`r`n`"" + (Get-Command python).Source + "`" `"$Dest\phylax.py`" %*") -Encoding ascii
$up = [Environment]::GetEnvironmentVariable("Path","User")
if (($up -split ";") -notcontains $Bin) { [Environment]::SetEnvironmentVariable("Path", "$up;$Bin", "User"); Write-Host "Added $Bin to your PATH" }
$env:Path += ";$Bin"
Write-Host ("phylax " + (Get-Content "$Dest\VERSION").Trim() + " installed.")
if ($env:PHYLAX_NO_SETUP -ne "1") { & "$Bin\phylax.cmd" setup }
