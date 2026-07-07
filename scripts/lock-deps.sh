#!/usr/bin/env sh
# Generate a fully hash-pinned lock from requirements.txt for supply-chain-hardened,
# reproducible installs.
#
# WHY: requirements.txt pins versions but not artifact hashes, so a compromised or
# substituted package (typosquat, hijacked release, MITM) could still be installed.
# A hash-pinned lock makes pip reject anything whose sha256 doesn't match.
#
# Run this in a TRUSTED, network-connected environment (CI or a clean dev box),
# review the diff, then COMMIT requirements.lock. The Dockerfile installs from it
# with --require-hashes when present.
#
#   ./scripts/lock-deps.sh
#
# Re-run whenever requirements.txt changes.
set -eu

python -m pip install --upgrade pip pip-tools

# --generate-hashes : pin every direct AND transitive package to its sha256(s)
# --allow-unsafe    : also pin build deps (pip/setuptools) so --require-hashes is clean
python -m piptools compile \
    --generate-hashes \
    --allow-unsafe \
    --output-file requirements.lock \
    requirements.txt

echo "Wrote requirements.lock — review the diff and commit it."
echo "Docker will then install with --require-hashes (tamper-evident)."
