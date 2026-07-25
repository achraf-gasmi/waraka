#!/usr/bin/env bash
# Regenerates hf_spaces/{agents,graph,models,tools,config} from the repo-root
# packages of the same name.
#
# hf_spaces/ is deployed to Hugging Face Spaces as its own self-contained
# checkout -- it can't do an editable install of the root packages or import
# across a repo boundary, so the packages it needs are vendored in place
# instead. That means the copies under hf_spaces/ are generated, not
# hand-maintained: always edit the root agents/, graph/, models/, tools/,
# config/ and re-run this script, never the hf_spaces/ copies directly.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

dirs=(agents graph models tools config)

for d in "${dirs[@]}"; do
  rm -rf "hf_spaces/$d"
  mkdir -p "hf_spaces/$d"
  cp -r "$d/." "hf_spaces/$d/"
  find "hf_spaces/$d" -type d -name "__pycache__" -exec rm -rf {} +
done

echo "Synced ${dirs[*]} into hf_spaces/"
