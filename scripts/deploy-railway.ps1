# Deploy DoGoods backend to Railway (uploads current workspace).
# Prereq: railway login  &&  railway link  (once per machine)
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

# Load RAILWAY_TOKEN from .env / .env.local if not already set
if (-not $env:RAILWAY_TOKEN) {
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
}

function Fail($msg) {
    Write-Error $msg
    exit 1
}

if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Fail "Railway CLI not found. Install: npm i -g @railway/cli"
}

Write-Host "Checking Railway auth..."
railway whoami 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Fail @"
Not logged in to Railway. In an interactive terminal run:
  railway login
Or set a project deploy token:
  `$env:RAILWAY_TOKEN = '<token from Railway dashboard → Project → Settings → Tokens>'
"@
}

Write-Host "Checking project link..."
$status = railway status 2>&1
if ($LASTEXITCODE -ne 0 -or ($status -match "No linked project")) {
    Fail @"
No Railway project linked in this folder. Run once:
  railway link
Pick the dogoods-backend (production) project and service.
"@
}

Write-Host $status
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
