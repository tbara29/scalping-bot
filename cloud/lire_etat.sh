#!/usr/bin/env bash
# Récupère etat/bots.json depuis la branche « etat » (ou crée un état vide).
set -uo pipefail
mkdir -p etat
if git fetch -q --depth 1 origin etat 2>/dev/null && git show FETCH_HEAD:etat/bots.json > etat/bots.json 2>/dev/null; then
  echo "État récupéré"
else
  echo '{"bots":{}}' > etat/bots.json
  echo "Nouvel état"
fi
