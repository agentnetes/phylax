# phylax menu (gum) for Windows
$Kit = Split-Path -Parent $MyInvocation.MyCommand.Path
while ($true) {
  Clear-Host; python "$Kit\phylax.py" status; ""
  $a = gum choose --header "phylax" "Sync now" "Add a project" "Add folders in bulk" "Health check" "Projects" "Live status (watch)" "Backup sessions now" "Restore from Drive" "Reinstall schedule" "Quit"
  switch ($a) {
    "Sync now" { python "$Kit\phylax.py" sync --all; Read-Host "enter to continue" | Out-Null }
    "Add a project" { $n = gum input --header "Project name"; $d = gum input --header "Project folder" --value (Join-Path $HOME $n); if ($n) { python "$Kit\phylax.py" init --name $n --dir $d }; Start-Sleep 1 }
    "Add folders in bulk" { $par = gum input --header "Parent folder" --value (Join-Path $HOME "Documents"); $sel = python "$Kit\phylax.py" discover $par | gum choose --no-limit --header "Select folders"; $mode = (gum choose --header "Back up what?" "context" "full" "both"); foreach ($f in $sel) { if ($f) { python "$Kit\phylax.py" init --name $f --dir (Join-Path $par $f) --mode $mode } }; Start-Sleep 1 }
    "Health check" { python "$Kit\phylax.py" doctor; Read-Host "enter to continue" | Out-Null }
    "Projects" { python "$Kit\phylax.py" projects; Read-Host "enter to continue" | Out-Null }
    "Live status (watch)" { python "$Kit\phylax.py" watch }
    "Backup sessions now" { python "$Kit\phylax.py" backup --force --all; Read-Host "enter to continue" | Out-Null }
    "Restore from Drive" { $id = gum input --header "Path to your age private key"; if (gum confirm "Restore latest backup into $HOME?") { python "$Kit\phylax.py" restore --identity $id }; Read-Host "enter to continue" | Out-Null }
    "Reinstall schedule" { python "$Kit\phylax.py" schedule install }
    default { exit }
  }
}
