#!/usr/bin/env bash
# Saves data/market.db to the "data" branch as a single commit, replacing the old one.
# Keeping only one commit stops the repo from growing every 15 minutes.
set -euo pipefail

tmp=$(mktemp -d)
cp data/market.db "$tmp/"
cd "$tmp"
git init -q -b data
git add market.db
git -c user.name="github-actions[bot]" \
    -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
    commit -qm "Update data $(date -u +%Y-%m-%dT%H:%M:%SZ)"
git push -qf "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" data
echo "Database saved to the data branch."
