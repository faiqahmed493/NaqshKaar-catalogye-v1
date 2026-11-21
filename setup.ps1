# Naqshkaar Catalogue Studio - one-command setup for Windows.
#
#   Double-click setup.cmd, or run in PowerShell from this folder:
#     powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# First run: creates .env, builds, starts everything, runs the self-test.
# Later runs: rebuilds and restarts with your existing .env.
# Needs Docker Desktop (with the WSL 2 backend), running.

$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
$EnvFile = Join-Path $PSScriptRoot ".env"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Say($msg)  { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Note($msg) { Write-Host "    $msg" }
function Fail($msg) { Write-Host ""; Write-Host "ERROR: $msg" -ForegroundColor Red; Read-Host "Press Enter to close"; exit 1 }

# ---------------------------------------------------------------- .env helpers
function Get-EnvValue([string]$key) {
    if (-not (Test-Path $EnvFile)) { return "" }
    foreach ($line in [IO.File]::ReadAllLines($EnvFile)) {
        if ($line.StartsWith("$key=")) { return $line.Substring($key.Length + 1).Trim("'") }
    }
    return ""
}
function Set-EnvValue([string]$key, [string]$value) {
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.AddRange([string[]][IO.File]::ReadAllLines($EnvFile))
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i].StartsWith("$key=")) { $lines[$i] = "$key=$value"; $found = $true }
    }
    if (-not $found) { $lines.Add("$key=$value") }
    # LF line endings and no BOM, so Docker Compose reads the first line correctly.
    [IO.File]::WriteAllText($EnvFile, (($lines -join "`n") + "`n"), $Utf8NoBom)
}
function New-Secret([int]$n) {
    $chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = New-Object byte[] $n
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}
function Test-PortBusy([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { return ($client.ConnectAsync("127.0.0.1", $port).Wait(300) -and $client.Connected) }
    catch { return $false }
    finally { $client.Close() }
}
function Get-FreePort([int]$port) {
    while (Test-PortBusy $port) { $port++ }
    return $port
}
function Read-Plain([string]$prompt) {
    $secure = Read-Host $prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

# ---------------------------------------------------------------- 1. Docker
Say "Checking Docker"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker is not installed. Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and restart Windows."
}
docker compose version *> $null
if ($LASTEXITCODE -ne 0) { Fail "'docker compose' is not available. Update Docker Desktop." }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail "Docker Desktop is not running. Start it, wait until it shows 'Engine running', then run this again." }
Note (docker compose version)

# ---------------------------------------------------------------- 2. .env
if (-not (Test-Path $EnvFile)) {
    Say "Creating .env (your settings and secrets)"
    $template = [IO.File]::ReadAllText((Join-Path $PSScriptRoot ".env.example"))
    $template = $template -replace "`r`n", "`n"
    [IO.File]::WriteAllText($EnvFile, $template, $Utf8NoBom)
    Set-EnvValue "POSTGRES_PASSWORD" (New-Secret 24)
    Set-EnvValue "SECRET_KEY" (New-Secret 48)
    Note "Generated a database password and a secret key."

    $email = (Read-Host "    Admin email for the studio").Trim()
    if (-not $email) { Fail "An email is required." }
    while ($true) {
        $pw = Read-Plain "    Admin password (10+ characters)"
        if ($pw.Length -lt 10) { Note "Too short."; continue }
        if ($pw.Contains("'")) { Note "Please avoid the ' character."; continue }
        $pw2 = Read-Plain "    Repeat the password"
        if ($pw -eq $pw2) { break }
        Note "Passwords do not match."
    }
    Set-EnvValue "BOOTSTRAP_ADMIN_EMAIL" $email
    Set-EnvValue "BOOTSTRAP_ADMIN_PASSWORD" "'$pw'"

    foreach ($key in @("DB_PORT", "API_PORT", "WEB_PORT")) {
        $want = [int](Get-EnvValue $key)
        $got = Get-FreePort $want
        if ($got -ne $want) { Set-EnvValue $key "$got"; Note "Port $want is in use, so $key=$got." }
    }
} else {
    Say "Using your existing .env"
}
if (@([IO.File]::ReadAllLines($EnvFile) | Where-Object { -not $_.StartsWith("#") -and $_ -match "CHANGE_ME" }).Count -gt 0) {
    Fail ".env still has CHANGE_ME values. Edit them, or delete .env and run this again."
}
$apiPort = Get-EnvValue "API_PORT"
$webPort = Get-EnvValue "WEB_PORT"

# ---------------------------------------------------------------- 3. build and start
Say "Building and starting the studio (the first build takes 5-15 minutes)"
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Fail "docker compose up failed. Scroll up for the first red error line." }

Say "Waiting for the API on http://localhost:$apiPort"
$ok = $false
for ($i = 0; $i -lt 120; $i++) {
    try {
        Invoke-RestMethod -Uri "http://localhost:$apiPort/api/health" -TimeoutSec 5 | Out-Null
        $ok = $true; break
    } catch { Write-Host -NoNewline "."; Start-Sleep -Seconds 5 }
}
Write-Host ""
if (-not $ok) {
    docker compose logs --tail=80 api
    Fail "The API did not start. The log above shows why; SETUP.md section 14 lists common fixes."
}
Note "API is healthy."

# ---------------------------------------------------------------- 4. mock 3D worker
if (-not (Get-EnvValue "WORKER_API_KEY")) {
    Say "Creating an API key for the built-in 3D worker"
    $out = docker compose exec -T api python -m app.cli create-api-key --name docker-mock-worker --scopes worker
    $key = ([string]($out | Select-Object -Last 1)).Trim()
    if (-not $key.StartsWith("nqk_")) { Fail "Could not create the worker key: $out" }
    Set-EnvValue "WORKER_API_KEY" $key
    Note "Saved to .env as WORKER_API_KEY."
}
Say "Starting the mock 3D worker (tests the pipeline without a GPU)"
docker compose --profile mock up -d --build generator-mock
if ($LASTEXITCODE -ne 0) { Fail "Could not start the mock worker." }

# ---------------------------------------------------------------- 5. self-test
$ans = Read-Host "`n    Run the end-to-end self-test now? [Y/n]"
if ($ans -ne "n" -and $ans -ne "N") {
    Start-Sleep -Seconds 5
    docker compose exec -T api python -m app.smoke
    if ($LASTEXITCODE -ne 0) { Fail "The self-test failed. Send the output above to get help." }
}

Say "Done"
Note "Web UI:   http://localhost:$webPort    (sign in with $(Get-EnvValue 'BOOTSTRAP_ADMIN_EMAIL'))"
Note "API docs: http://localhost:$apiPort/docs"
Note "Stop:     docker compose --profile mock down      Start again: run setup.cmd"
Start-Process "http://localhost:$webPort"
Read-Host "`nPress Enter to close"
