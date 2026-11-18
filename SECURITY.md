# Security Policy

Phylax handles encryption keys and Google Drive access, so we take security reports seriously.

## Reporting a vulnerability

**Please do not open a public issue.** Report it privately through GitHub:
[**Report a vulnerability**](https://github.com/agentnetes/phylax/security/advisories/new).

Include what you found, how to reproduce it, and the version (`phylax version`). **Never include real tokens, private keys
or backup contents** in a report — redact them. We will acknowledge your report, keep you updated while we investigate, and
credit you in the fix if you wish.

## Supported versions

Only the latest release receives security fixes. Update with `phylax update`.

## In scope

- Plaintext data, names or keys reaching Google Drive, logs, the git history or this repository
- The installer or update path running unexpected code, or skipping checksum verification
- Restore writing outside its target folder, or over the original data without `--force`
- Auto-commit or auto-push exposing secret-looking files

## Out of scope

- Loss of the age private key (it is deliberately never uploaded; keep it in a password manager)
- Issues that require an attacker who already controls your machine or your Google account
- Weaknesses in third-party tools (rclone, age, gum, git); please report those upstream

## Security design (summary)

- Data is encrypted on your machine with [age](https://age-encryption.org) to public recipients only; the machine cannot decrypt its own backups.
- Drive access uses rclone's `drive.file` scope, limited to files Phylax created.
- The installer hides the Google login output (it contains tokens) and never prints the private key.
- Release downloads are verified against a SHA-256 checksum before installing.
