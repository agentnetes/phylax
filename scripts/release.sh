#!/usr/bin/env bash
# Build release assets locally. Usage: scripts/release.sh 1.0.0 agentnetes/phylax
# Output: dist/ (archives + checksums + bootstrap scripts) and Formula/phylax.rb + bucket/phylax.json. Does NOT publish anything.
set -euo pipefail
V="${1:?version e.g. 1.0.0}"; REPO="${2:?OWNER/repo}"; cd "$(cd "$(dirname "$0")/.." && pwd)"
echo "$V" > VERSION; echo "$REPO" > REPO
git add VERSION REPO >/dev/null 2>&1 || true; git diff --cached --quiet || git commit -q -m "release $V"
rm -rf dist; mkdir -p dist Formula bucket
git archive --prefix=phylax/ --format=tar.gz -o "dist/phylax-$V.tar.gz" HEAD
git archive --prefix=phylax/ --format=zip    -o "dist/phylax-$V.zip" HEAD
cp "dist/phylax-$V.tar.gz" dist/phylax.tar.gz; cp "dist/phylax-$V.zip" dist/phylax.zip
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }
for f in dist/*.tar.gz dist/*.zip; do echo "$(sha "$f")  $(basename "$f")" > "$f.sha256"; done
sed "s#agentnetes/phylax#$REPO#g" bootstrap.sh  > dist/bootstrap.sh;  sed "s#agentnetes/phylax#$REPO#g" bootstrap.ps1 > dist/bootstrap.ps1
sed -e "s#@REPO@#$REPO#g" -e "s#@VERSION@#$V#g" -e "s#@SHA_TGZ@#$(sha dist/phylax-$V.tar.gz)#" packaging/homebrew/phylax.rb.tmpl > Formula/phylax.rb
sed -e "s#@REPO@#$REPO#g" -e "s#@VERSION@#$V#g" -e "s#@SHA_ZIP@#$(sha dist/phylax-$V.zip)#"  packaging/scoop/phylax.json.tmpl  > bucket/phylax.json
echo "Built dist/ for v$V ($REPO), plus Formula/phylax.rb and bucket/phylax.json. To publish:"
echo "  git tag v$V && git push origin main v$V && gh release create v$V dist/* --title v$V"
echo "  then: git add Formula bucket && git commit -m 'Formula/bucket for v$V' && git push"
