# phylax — instructions for Claude Code

This repo is a team tool that backs up a Claude Code project's context to the user's OWN Google Drive
(one-way, local files stay the source of truth). When a teammate asks you to "set me up" / "install phylax":

1. Detect the OS (macOS or Windows) and run the matching installer for them: `./install.sh` or `./install.ps1`.
   The installer is interactive (gum) — tell the user to run it themselves with `! ./install.sh` so prompts work.
2. NEVER run `rclone config`/`age-keygen` in a way that prints tokens or the private key into the chat.
   The installer hides that output on purpose. If the user pastes secrets, tell them once to revoke/rotate them.
3. The age private key (`~/.config/phylax/identity.txt`, or `%APPDATA%\phylax\identity.txt`) must be saved in the user's
   password manager. Don't read or print it. Confirm they did it before calling setup finished.
4. Verify with `python3 phylax.py status` (use `python` on Windows) — expect "SYNCED".
5. Troubleshooting: sync log at `~/.config/phylax/sync.log` (macOS); `rclone about <remote>:` tests Drive auth;
   if Drive auth errors mention "client_id", rclone's shared Google client ID was retired — see README "Own Google client ID".

Design rules (keep when editing): stdlib-only Python core; one-way push (`rclone copy`, never `sync`); sessions are only
uploaded age-encrypted; nothing customer- or company-specific in this repo; per-user config lives outside the repo.
