#!/usr/bin/env bash
# phylax one-line installer for macOS/Linux:
#   curl -fsSL https://github.com/agentnetes/phylax/releases/latest/download/bootstrap.sh | bash
# Downloads the release tarball, verifies its SHA-256, installs to ~/.phylax, links `phylax` into ~/.local/bin, then runs `phylax setup`.
set -euo pipefail
REPO="${PHYLAX_REPO:-agentnetes/phylax}"; BASE="${PHYLAX_BASE:-https://github.com/$REPO/releases/latest/download}"
DEST="${PHYLAX_HOME:-$HOME/.phylax}"; BIN="$HOME/.local/bin"
need() { command -v "$1" >/dev/null 2>&1 || { echo "'$1' is required. $2"; exit 1; }; }
need curl "" ; need tar "" ; need python3 "On macOS run: xcode-select --install"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
echo "Downloading phylax…"
curl -fsSL "$BASE/phylax.tar.gz" -o "$T/k.tgz"; curl -fsSL "$BASE/phylax.tar.gz.sha256" -o "$T/k.sha"
WANT="$(cut -d' ' -f1 "$T/k.sha")"; GOT="$(shasum -a 256 "$T/k.tgz" | cut -d' ' -f1)"
[ "$WANT" = "$GOT" ] || { echo "Checksum mismatch — aborting (nothing installed)."; exit 1; }
rm -rf "$DEST.new"; mkdir -p "$DEST.new"; tar xzf "$T/k.tgz" -C "$DEST.new" --strip-components=1
rm -rf "$DEST"; mv "$DEST.new" "$DEST"
mkdir -p "$BIN"; printf '#!/bin/sh\nexec "%s" "%s/phylax.py" "$@"\n' "$(command -v python3)" "$DEST" > "$BIN/phylax"; chmod +x "$BIN/phylax"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "Adding $BIN to your PATH in ~/.zshrc"; echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc"; export PATH="$BIN:$PATH";; esac
echo "phylax $(cat "$DEST/VERSION") installed."
if [ "${PHYLAX_NO_SETUP:-}" != 1 ]; then phylax setup </dev/tty; fi   # </dev/tty so prompts work under `curl | bash`
