#!/usr/bin/env bash
# Enregistre etat/bots.json sur la branche « etat » (un seul commit, réécrit à chaque fois).
set -euo pipefail
tmp=$(mktemp -d)
mkdir -p "$tmp/etat"
cp etat/bots.json "$tmp/etat/bots.json"
cd "$tmp"
git init -q -b etat
git add etat/bots.json
git -c user.name="grid-bot" -c user.email="41898282+github-actions[bot]@users.noreply.github.com" commit -q -m "État des bots $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" etat
