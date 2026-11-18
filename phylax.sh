#!/usr/bin/env bash
# phylax menu (gum). Usage: ./phylax.sh
KIT="$(cd "$(dirname "$0")" && pwd)"; PY="python3 $KIT/phylax.py"
while true; do
  clear; $PY status || true; echo
  A=$(gum choose --header "phylax" "Sync now" "Add a project" "Add folders in bulk" "Health check" "Projects" "Live status (watch)" "Backup sessions now" "Restore from Drive" "Reinstall schedule" "Quit") || exit 0
  case "$A" in
    "Sync now") gum spin --title "Syncing…" --show-output -- $PY sync; gum input --placeholder "enter to continue" >/dev/null;;
    "Add a project") N=$(gum input --header "Project name"); D=$(gum input --header "Project folder" --value "$HOME/$N"); D="${D/#\~/$HOME}"
        [ -n "$N" ] && $PY init --name "$N" --dir "$D"; sleep 1;;
    "Add folders in bulk") P=$(gum input --header "Parent folder (its subfolders will be listed)" --value "$HOME/Documents"); P="${P/#\~/$HOME}"
        SEL=$($PY discover "$P" | gum choose --no-limit --header "Select folders to back up (space = tick, enter = confirm)") || continue
        MODE=$(gum choose --header "What to back up for these folders?" "context  (Claude context only)" "full  (encrypted copy of all files)" "both" | awk '{print $1}')
        while IFS= read -r F; do [ -n "$F" ] && $PY init --name "$F" --dir "$P/$F" --mode "$MODE"; done <<< "$SEL"; sleep 1;;
    "Health check") $PY doctor; gum input --placeholder "enter to continue" >/dev/null;;
    "Projects") $PY projects; gum input --placeholder "enter to continue" >/dev/null;;
    "Live status (watch)") $PY watch;;
    "Backup sessions now") gum spin --title "Encrypting + uploading…" --show-output -- $PY backup --force; gum input --placeholder "enter to continue" >/dev/null;;
    "Restore from Drive") ID=$(gum input --header "Path to your age private key (identity.txt)" --placeholder "~/Downloads/identity.txt"); ID="${ID/#\~/$HOME}"
        gum confirm "Restore latest backup into $HOME? Existing files may be overwritten." && $PY restore --identity "$ID"; gum input --placeholder "enter to continue" >/dev/null;;
    "Reinstall schedule") $PY schedule install; sleep 1;;
    *) exit 0;;
  esac
done
