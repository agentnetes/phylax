#!/usr/bin/env bash
# phylax installer for macOS/Linux — interactive (gum). Never prints tokens or the private key.
set -euo pipefail
KIT="$(cd "$(dirname "$0")" && pwd)"
have() { command -v "$1" >/dev/null 2>&1; }

if ! have gum; then
  echo "Installing gum (the TUI toolkit)…"
  if have brew; then brew install gum; else echo "Install Homebrew (https://brew.sh) or gum (https://github.com/charmbracelet/gum) and re-run."; exit 1; fi
fi
gum style --border rounded --padding "1 3" --border-foreground 212 "$(gum style --bold 'phylax setup')" "Back up your Claude Code context to YOUR OWN Google Drive." "Files stay local. Metadata + encrypted sessions go to Drive."

# 1. dependencies
for t in python3 rclone age git; do
  have "$t" && continue
  gum confirm "Install missing dependency: $t (via Homebrew)?" || { echo "$t is required."; exit 1; }
  case "$t" in python3) brew install python;; *) brew install "$t";; esac
done

# 2. projects (add as many as you like)
REMOTE="gdrive-phylax"
add_project() {
  NAME=$(gum input --header "Project name (e.g. my-project)" --placeholder "my-project"); [ -n "$NAME" ] || return 1
  DIR=$(gum input --header "Project folder (existing or new)" --value "$HOME/$(echo "$NAME" | tr '[:upper:]' '[:lower:]')")
  DIR="${DIR/#\~/$HOME}"
  python3 "$KIT/phylax.py" init --name "$NAME" --dir "$DIR" --remote "$REMOTE"
  LAST="$NAME"
}
add_project || exit 1
while gum confirm "Add another project folder?"; do add_project || break; done

# 3. Google Drive login (scope limited to files rclone creates). Output hidden so tokens never hit the screen/logs.
if ! rclone listremotes | grep -q "^$REMOTE:"; then
  gum style --foreground 212 "A browser will open to authorize Google Drive (limited 'drive.file' scope)."
  rclone config create "$REMOTE" drive scope drive.file >/dev/null 2>&1 || { echo "Drive login failed."; exit 1; }
fi
gum style --foreground 2 "✓ Google Drive connected"

# 4. encryption key (private key stays on this machine only until YOU move it to a password manager)
CFG="$HOME/.config/phylax"; mkdir -p "$CFG"; chmod 700 "$CFG"
if [ ! -f "$CFG/identity.txt" ]; then
  age-keygen -o "$CFG/identity.txt" >/dev/null 2>&1; chmod 600 "$CFG/identity.txt"
  age-keygen -y "$CFG/identity.txt" > "$CFG/recipient.txt"
fi
gum style --foreground 214 "IMPORTANT: save your private key in your password manager NOW." "Without it, encrypted backups can't be restored."
gum confirm "Copy the private key to the clipboard now? (it is NOT displayed)" && { pbcopy < "$CFG/identity.txt"; gum style --foreground 2 "Copied. Paste it into your password manager, then clear your clipboard."; }
gum confirm "I have saved the key safely" || gum style --foreground 1 "Do it before relying on backups: pbcopy < $CFG/identity.txt"

# 4b. optional: private GitHub repo (your own account) for the project folder
if have gh && gum confirm "Create a PRIVATE GitHub repo for the LAST project added (your own account) so it is backed up with git?"; then
  gh auth status >/dev/null 2>&1 || gh auth login
  python3 "$KIT/phylax.py" git-init -p "$LAST" || gum style --foreground 1 "git repo setup failed — you can retry later: python3 $KIT/phylax.py git-init"
elif ! have gh; then gum style --faint "Tip: install GitHub CLI (brew install gh) and run 'python3 $KIT/phylax.py git-init' for git backup."; fi

# 5. schedule, statusline, first sync
gum spin --title "Scheduling background sync…" -- python3 "$KIT/phylax.py" schedule install
if gum confirm "Install the team status line (ccstatusline) with the sync indicator?"; then
  if [ -f "$HOME/.config/ccstatusline/settings.json" ] && gum confirm "You already have a ccstatusline config. Replace it with the team standard? (No = just add the sync widget; a .bak is kept)"; then
    python3 "$KIT/phylax.py" statusline --overwrite
  else python3 "$KIT/phylax.py" statusline; fi
fi
gum spin --title "Running first sync…" --show-output -- python3 "$KIT/phylax.py" sync --all
gum style --border double --padding "0 2" --foreground 2 "Done! Open the menu any time:  $KIT/phylax.sh"
