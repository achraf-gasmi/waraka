# Regenerates hf_spaces/{agents,graph,models,tools,config} from the repo-root
# packages of the same name.
#
# hf_spaces/ is deployed to Hugging Face Spaces as its own self-contained
# checkout -- it can't do an editable install of the root packages or import
# across a repo boundary, so the packages it needs are vendored in place
# instead. That means the copies under hf_spaces/ are generated, not
# hand-maintained: always edit the root agents/, graph/, models/, tools/,
# config/ and re-run this script, never the hf_spaces/ copies directly.

$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

$dirs = @("agents", "graph", "models", "tools", "config")

foreach ($d in $dirs) {
    $dest = Join-Path "hf_spaces" $d
    if (Test-Path $dest) {
        Remove-Item -Recurse -Force $dest
    }
    Copy-Item -Recurse $d $dest
    Get-ChildItem -Path $dest -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force
}

Write-Host "Synced $($dirs -join ', ') into hf_spaces/"
