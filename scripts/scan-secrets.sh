#!/usr/bin/env bash
# Lightweight, dependency-free secret scan over TRACKED files.
# Exit non-zero if a likely secret is found. Used by the pre-push hook
# (.githooks/pre-push) and runnable manually:  ./scripts/scan-secrets.sh
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# High-signal patterns. Keep these scoped to real-credential shapes to
# avoid noise. Add project-specific known-bad values here as needed.
# Match real-credential shapes, not code that merely names a field:
#  - PEM private key blocks
#  - a private_key_hex assigned an actual 64-char hex value
#  - known project secret values
#  - extended public/private keys
PATTERNS='-----BEGIN [A-Z ]*PRIVATE KEY-----|private_key_hex"?[[:space:]]*[:=][[:space:]]*"?[0-9a-fA-F]{64}|cheritopass|cherito-jwt-secret-prod|oscar123|aws_secret_access_key|xpub[0-9A-Za-z]{50,}|xprv[0-9A-Za-z]{50,}'

# Files/paths that are allowed to contain placeholder-style matches.
EXCLUDES=':!:*.example :!:scripts/scan-secrets.sh :!:.githooks/pre-push'

hits=$(git grep -nIE -e "$PATTERNS" -- . $EXCLUDES || true)

if [ -n "$hits" ]; then
  echo "✖ Potential secret(s) found in tracked files:" >&2
  echo "$hits" >&2
  echo "" >&2
  echo "If these are false positives, refine PATTERNS/EXCLUDES in scripts/scan-secrets.sh." >&2
  echo "To bypass once (NOT recommended): git push --no-verify" >&2
  exit 1
fi

echo "✓ scan-secrets: no tracked secrets detected"
