# Point Railway DATABASE_URL at Supabase Postgres.
#
# Option A (recommended): paste the full session-pooler URI from Supabase Connect into .env:
#   DATABASE_URL=postgresql://postgres.ifzbpqyuhnxbhdcnmvfs:YOUR_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
#
# Option B: set only the password and pass -PoolerHost from the Connect panel:
#   SUPABASE_DB_PASSWORD=your-password
#   .\scripts\set-railway-supabase-database.ps1 -PoolerHost aws-0-us-west-1.pooler.supabase.com
#
# Dashboard: https://supabase.com/dashboard/project/ifzbpqyuhnxbhdcnmvfs?showConnect=true&method=session
#
# Usage (from repo root):
#   .\scripts\set-railway-supabase-database.ps1

param(
    [string]$Service = "dogoods-backend",
    [string]$Environment = "production",
    [string]$Project = "cbd9e9c8-c48b-4c8b-9a88-0e3b6c2dfb8c",
    [string]$ProjectRef = "ifzbpqyuhnxbhdcnmvfs",
    [string]$PoolerHost = ""
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

function Read-DotEnvValue([string]$Name) {
    $fromEnv = [Environment]::GetEnvironmentVariable($Name)
    if ($fromEnv) { return $fromEnv }
    foreach ($envFile in @(".env", ".env.local")) {
        $path = Join-Path (Get-Location) $envFile
        if (-not (Test-Path $path)) { continue }
        $found = $null
        Get-Content $path | ForEach-Object {
            if ($_ -match "^\s*$Name=(.*)$") {
                $found = $matches[1].Trim().Trim('"').Trim("'")
            }
        }
        if ($found) { return $found }
    }
    return $null
}

$url = Read-DotEnvValue "DATABASE_URL"
if (-not $url) {
    $password = Read-DotEnvValue "SUPABASE_DB_PASSWORD"
    if (-not $password) {
        Write-Error @"
Set DATABASE_URL or SUPABASE_DB_PASSWORD in .env (do not commit), then re-run.
Connect panel: https://supabase.com/dashboard/project/$ProjectRef?showConnect=true&method=session
"@
    }
    if (-not $PoolerHost) {
        Write-Error "Pass -PoolerHost from the Supabase Connect panel (e.g. aws-0-us-west-1.pooler.supabase.com)."
    }
    Add-Type -AssemblyName System.Web
    $encoded = [System.Web.HttpUtility]::UrlEncode($password)
    $url = "postgresql://postgres.${ProjectRef}:${encoded}@${PoolerHost}:5432/postgres"
}

if (-not $env:RAILWAY_TOKEN) {
    $env:RAILWAY_TOKEN = Read-DotEnvValue "RAILWAY_TOKEN"
}
if (-not $env:RAILWAY_TOKEN) {
    Write-Error "RAILWAY_TOKEN not found in environment or .env"
}

Write-Host "Setting DATABASE_URL on Railway ($Service / $Environment)..."
railway variable set "DATABASE_URL=$url" -s $Service -e $Environment -p $Project
if ($LASTEXITCODE -ne 0) {
    Write-Error "railway variable set failed (exit $LASTEXITCODE)"
}
Write-Host "Done. Railway will redeploy with durable Supabase Postgres."
