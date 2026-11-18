#!/usr/bin/env bash
# End-to-end smoke test against a local folder acting as the "Drive" (no Google account, no real home touched).
set -euo pipefail
command -v age >/dev/null && command -v rclone >/dev/null || { echo "needs age and rclone"; exit 1; }
KIT="$(cd "$(dirname "$0")/.." && pwd)"; S="$(cd "$(mktemp -d)" && pwd -P)"
export HOME="$S/home" RCLONE_CONFIG_TESTL_TYPE=local; mkdir -p "$HOME" "$S/remote"
mm() { python3 "$KIT/phylax.py" "$@"; }; fail() { echo "FAIL: $*"; exit 1; }
K="$HOME/.config/phylax"; mkdir -p "$K"; age-keygen -o "$K/identity.txt" 2>/dev/null; age-keygen -y "$K/identity.txt" > "$K/recipient.txt"
W="$HOME/proj"; mkdir -p "$W/Board" "$W/node_modules"; echo "plan v1" > "$W/Board/plan.txt"; echo k > "$W/prod.pem"; echo n > "$W/node_modules/x.js"
mm init --name t --dir "$W" --remote testl --folder "$S/remote/t" --mode full >/dev/null
mm sync >/dev/null 2>&1 || fail "sync"
grep -rqE "plan|Board" "$S/remote" && fail "readable name/content on remote"
echo "plan v2" > "$W/Board/plan.txt"; mm sync >/dev/null 2>&1 || fail "second sync"
SNAP="$(mm restore-files -p t --identity "$K/identity.txt" --snapshots | head -1 | grep -o '[0-9]\{8\}T[0-9]*Z')"
mm restore-files -p t --identity "$K/identity.txt" --at "$SNAP" --to "$S/r1" >/dev/null || fail "restore old"
[ "$(cat "$S/r1/Board/plan.txt")" = "plan v1" ] || fail "old version wrong"
mm restore-files -p t --identity "$K/identity.txt" --to "$S/r2" >/dev/null || fail "restore latest"
[ "$(cat "$S/r2/Board/plan.txt")" = "plan v2" ] || fail "latest version wrong"
[ ! -e "$S/r2/node_modules" ] || fail "node_modules should be skipped"
mm restore-files -p t --identity "$K/identity.txt" --to "$W" >/dev/null 2>&1 && fail "restore over original should be refused"
echo "PASS"
