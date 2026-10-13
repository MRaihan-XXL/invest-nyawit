# watchdog.ps1 - cek kesehatan semua komponen setiap 10 menit, alert Telegram bila ada yang mati.
# Dijalankan scheduled task. Komponen: cloudflared, docker containers (postgres/n8n/caddy/dashboard/render),
# n8n healthz, dashboard health, OAuth receiver (:8099), tunnel URL sinkron dengan .env.
# Token dibaca dari .env saat runtime.

$ErrorActionPreference = 'SilentlyContinue'
$root = 'D:\FlyEnv-Data\server\www\invest-nyawit'
$envf = Join-Path $root '.env'

function Log($m) {
    Add-Content -Path (Join-Path $env:TEMP 'watchdog.log') -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
}
function Get-EnvLine($name) {
    (Get-Content $envf | Where-Object { $_ -match "^$name=" } | Select-Object -First 1) -replace "^$name=",''
}
function Send-Telegram($msg) {
    $tok  = Get-EnvLine 'TELEGRAM_BOT_TOKEN'
    $chat = Get-EnvLine 'TELEGRAM_CHAT_ID'
    if (-not $tok -or -not $chat) { return }
    $escaped = [uri]::EscapeDataString($msg)
    curl.exe -s --max-time 15 "https://api.telegram.org/bot$tok/sendMessage?chat_id=$chat&text=$escaped" | Out-Null
}

# cegah instance ganda
$lock = Join-Path $env:TEMP 'watchdog.lock'
if (Test-Path $lock) {
    $lockAge = (Get-Date) - (Get-Item $lock).LastWriteTime
    if ($lockAge.TotalMinutes -lt 8) { exit }
}
Set-Content -Path $lock -Value (Get-Date -Format o) -Encoding utf8

try {
    $issues = @()

    # 1. cloudflared hidup?
    $cf = Get-Process cloudflared -ErrorAction SilentlyContinue
    if (-not $cf) { $issues += 'cloudflared mati' }

    # 2. docker containers running?
    $want = @('invest-nyawit-postgres-1','invest-nyawit-n8n-1','invest-nyawit-caddy-1','invest-nyawit-dashboard-1','invest-nyawit-render-1')
    $running = (docker ps --format '{{.Names}}') -join "`n"
    foreach ($c in $want) {
        if ($running -notmatch [regex]::Escape($c)) { $issues += "container $c tidak running" }
    }

    # 3. n8n healthz
    $n8n = curl.exe -s --max-time 5 -o NUL -w "%{http_code}" 'http://127.0.0.1:5678/healthz'
    if ($n8n -ne '200') { $issues += "n8n healthz=$n8n" }

    # 4. dashboard health
    $dash = curl.exe -s --max-time 5 -o NUL -w "%{http_code}" 'http://127.0.0.1:8091/health'
    if ($dash -ne '200') { $issues += "dashboard health=$dash" }

    # 5. OAuth receiver (:8099)
    $oauth = curl.exe -s --max-time 5 -o NUL -w "%{http_code}" 'http://127.0.0.1:8099/health'
    if ($oauth -ne '200') { $issues += "oauth-receiver health=$oauth" }

    # 6. tunnel URL sinkron?
    $tunnelUrl = $null
    $log = Join-Path $env:TEMP 'cloudflared-live.log'
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
        if ($m) { $tunnelUrl = $m.Matches[0].Value }
    }
    $cur = (Get-EnvLine 'PUBLIC_BASE_URL').Trim()
    if ($tunnelUrl -and $tunnelUrl -ne $cur) { $issues += "tunnel URL beda (.env=$cur live=$tunnelUrl) - tunnel-up seharusnya sync" }

    if ($issues.Count -gt 0) {
        $msg = "[invest-nyawit] WATCHDOG ALERT`n" + ($issues -join "`n")
        Log $msg
        Send-Telegram $msg
    } else {
        Log 'watchdog OK - semua sehat'
    }
} finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
