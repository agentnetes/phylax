---
name: phylax-setup
description: Set up phylax (Google Drive backup of Claude Code context, status line, scheduled sync) on this machine. Use when the user says "set me up", "install phylax" or "set up the backup".
---
Follow CLAUDE.md in this repo. Steps: detect OS → have the user run `! ./install.sh` (macOS) or `! ./install.ps1` (Windows)
→ never display tokens or the age private key → confirm the key is saved in their password manager → run
`python3 phylax.py status` (`python` on Windows) and report the result.
