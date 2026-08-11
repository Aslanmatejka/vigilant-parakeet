# Deploy DoGoods backend to Railway (uploads current workspace).
#
# Auth options (either works):
#   1. Project token in .env:  RAILWAY_TOKEN=<token from Project → Settings → Tokens>
#   2. Interactive login:      railway login  (once per machine)
#
# Usage (from repo root):
#   .\scripts\deploy-railway.ps1
#   .\scripts\deploy-railway.ps1 -Message "hotfix claim flow"
#   $env:RAILWAY_TOKEN = "<project-token>"; .\scripts\deploy-railway.ps1

param(
    [string]$Message = "Deploy backend/ai + claim/share fixes",
    [string]$Service = "dogoods-backend",
    [string]$Environment = "production",
    [string]$Project = "cbd9e9c8-c48b-4c8b-9a88-0e3b6c2dfb8c"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Prefer RAILWAY_TOKEN from .env / .env.local over a stale shell value.
# Project tokens are UUID-shaped and fail `railway whoami`, but work with
# `railway up -p/-s/-e`.
foreach ($envFile in @(".env", ".env.local")) {
    $path = Join-Path (Get-Location) $envFile
    if (Test-Path $path) {
        Get-Content $path | ForEach-Object {
            if ($_ -match '^\s*RAILWAY_TOKEN=(.*)$') {
                $env:RAILWAY_TOKEN = $matches[1].Trim().Trim('"').Trim("'")
            }
        }
    }
}

function Fail($msg) {
    Write-Error $msg
    exit 1
}

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Fail "Railway CLI not found. Install: npm i -g @railway/cli"
}

$hasProjectToken = [bool]$env:RAILWAY_TOKEN
if ($hasProjectToken) {
    Write-Host "Using RAILWAY_TOKEN from env/.env (project tokens skip whoami)."
} else {
    Write-Host "Checking Railway auth (interactive session)..."
    railway whoami 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Fail @"
Not logged in to Railway. Either:
  1. Set a project deploy token in .env:
       RAILWAY_TOKEN=<token from Railway → Project → Settings → Tokens>
  2. Or run interactively:
       railway login
"@
    }

    Write-Host "Checking project link..."
    $status = railway status 2>&1
    if ($LASTEXITCODE -ne 0 -or ($status -match "No linked project")) {
        Fail @"
No Railway project linked in this folder. Run once:
  railway link
Pick the dogoods-backend (production) project and service.
Or set RAILWAY_TOKEN in .env and re-run (no link needed).
"@
    }
    Write-Host $status
}

Write-Host ""
Write-Host "Deploying backend to Railway (railway up)..."
Write-Host "Message: $Message"
Write-Host ""

$upArgs = @("up", "-d", "-c", "-m", $Message, "-s", $Service, "-e", $Environment, "-p", $Project)

& railway @upArgs
if ($LASTEXITCODE -ne 0) {
    Fail "railway up failed (exit $LASTEXITCODE)"
}

Write-Host ""
Write-Host "Deploy triggered. Verifying health endpoints..."
Start-Sleep -Seconds 8

$health = curl.exe -sS "https://dogoods-backend-production.up.railway.app/api/ai/health" 2>&1
Write-Host "GET /api/ai/health -> $health"
if ($health -match "openai_configured") {
    Write-Host "OK: new backend/ai routes are live."
} elseif ($health -match "ai_configured") {
    Write-Warning "Still on OLD backend (ai_configured). Wait for build or check Railway logs."
} else {
    Write-Warning "Unexpected health response - check Railway dashboard logs."
}

$probe = curl.exe -sS -o NUL -w "%{http_code}" -X POST `
    -H "Content-Type: application/json" `
    -d '{"message":"hi"}' `
    "https://dogoods-backend-production.up.railway.app/api/ai/public_chat" 2>&1
Write-Host "POST /api/ai/public_chat -> HTTP $probe (expect 200 after deploy, was 404 on old build)"
