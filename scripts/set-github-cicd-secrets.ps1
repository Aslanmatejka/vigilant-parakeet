# Upload CI/CD secrets from local .env to GitHub Actions.
# Does NOT print secret values.
#
# Mapping:
#   AUTH_TOKEN   (nfp_…)  → NETLIFY_AUTH_TOKEN
#   RAILWAY_TOKEN         → RAILWAY_TOKEN
#   .netlify/state.json   → NETLIFY_SITE_ID  (fallback hardcoded site id)
#
# Prerequisites: gh auth login (once)
# Usage (repo root):  .\scripts\set-github-cicd-secrets.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Fail($msg) {
    Write-Error $msg
    exit 1
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Fail "GitHub CLI (gh) not found. Install: https://cli.github.com/"
}

gh auth status 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail "Not logged into GitHub CLI. Run: gh auth login"
}

function Get-DotEnvValue([string]$key) {
    $path = Join-Path (Get-Location) ".env"
    if (-not (Test-Path $path)) { return $null }
    foreach ($line in Get-Content $path) {
        if ($line -match ("^\s*" + [regex]::Escape($key) + "\s*=\s*(.*)$")) {
            return $matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $null
}

$netlifyToken = Get-DotEnvValue "NETLIFY_AUTH_TOKEN"
if (-not $netlifyToken) { $netlifyToken = Get-DotEnvValue "AUTH_TOKEN" }

$railwayToken = Get-DotEnvValue "RAILWAY_TOKEN"

$siteId = Get-DotEnvValue "NETLIFY_SITE_ID"
if (-not $siteId -and (Test-Path ".netlify/state.json")) {
    try {
        $siteId = (Get-Content ".netlify/state.json" -Raw | ConvertFrom-Json).siteId
    } catch { }
}
if (-not $siteId) {
    $siteId = "d5f37690-0335-437a-89b9-34a90c3107ed"
}

if (-not $netlifyToken) { Fail "Missing NETLIFY_AUTH_TOKEN or AUTH_TOKEN in .env" }
if (-not $railwayToken) { Fail "Missing RAILWAY_TOKEN in .env" }
if (-not $siteId) { Fail "Missing NETLIFY_SITE_ID" }

Write-Host "Setting GitHub Actions secrets (values never printed)..."
Write-Host "  NETLIFY_AUTH_TOKEN  from .env (AUTH_TOKEN or NETLIFY_AUTH_TOKEN)"
Write-Host "  NETLIFY_SITE_ID     = $siteId"
Write-Host "  RAILWAY_TOKEN       from .env"

$netlifyToken | gh secret set NETLIFY_AUTH_TOKEN
if ($LASTEXITCODE -ne 0) { Fail "Failed to set NETLIFY_AUTH_TOKEN" }

$siteId | gh secret set NETLIFY_SITE_ID
if ($LASTEXITCODE -ne 0) { Fail "Failed to set NETLIFY_SITE_ID" }

$railwayToken | gh secret set RAILWAY_TOKEN
if ($LASTEXITCODE -ne 0) { Fail "Failed to set RAILWAY_TOKEN" }

Write-Host ""
Write-Host "Done. Secrets set on this repo."
Write-Host "Re-run the failed Deploy jobs in Actions, or push an empty commit."
