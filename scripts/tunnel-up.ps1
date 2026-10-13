# tunnel-up.ps1 - jaga Cloudflare quick tunnel hidup 24/7 + sinkron URL ke sistem.
# Dijalankan scheduled task (ONLOGON) / manual. Loop abadi:
#   1. pastikan cloudflared hidup (auto-restart dgn URL baru bila crash)
#   2. baca URL dari log
#   3. bila URL != PUBLIC_BASE_URL di .env -> update .env -> docker compose up -d
#      -> jaga webhook Telegram bersih (deleteWebhook; WF03 = polling) -> notifikasi ke bot
#   4. tidur 60s, ulang.
# Tidak menyimpan rahasia apa pun di file ini - token dibaca dari .env saat runtime.

$ErrorActionPreference = 'SilentlyContinue'
$root  = 'D:\FlyEnv-Data\server\www\invest-nyawit'
$envf  = Join-Path $root '.env'
$cf    = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
$log   = Join-Path $env:TEMP 'cloudflared-live.log'
$state = Join-Path $env:TEMP 'tunnel-url.txt'

# cegah instance ganda (scheduled task ONLOGON + retry per 5 menit bisa tabrakan)
$lock = Join-Path $env:TEMP 'tunnel-up.lock'
if (Test-Path $lock) {
    $lockAge = (Get-Date) - (Get-Item $lock).LastWriteTime
    if ($lockAge.TotalMinutes -lt 3) { exit }
}
Set-Content -Path $lock -Value (Get-Date -Format o) -Encoding utf8

function Log($m) {
    Add-Content -Path (Join-Path $env:TEMP 'tunnel-up.log') -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
}
function Get-EnvLine($name) {
    (Get-Content $envf | Where-Object { $_ -match "^$name=" } | Select-Object -First 1) -replace "^$name=",''
}
function Set-EnvVal($name, $val) {
    $out = Get-Content $envf | ForEach-Object {
        if ($_ -match "^$name=") { "$name=$val" } else { $_ }
    }
    Set-Content -Path $envf -Value $out -Encoding utf8
}
function Get-TunnelUrl {
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
        if ($m) { return $m.Matches[0].Value }
    }
    return $null
}
function Start-Tunnel {
    Remove-Item $log -Force -ErrorAction SilentlyContinue
    Start-Process -FilePath $cf -ArgumentList 'tunnel','--url','http://127.0.0.1:80' `
        -WindowStyle Hidden -RedirectStandardError $log -RedirectStandardOutput "$log.out"
    for ($i = 0; $i -lt 45; $i++) {
        Start-Sleep -Seconds 2
        $u = Get-TunnelUrl
        if ($u) { return $u }
    }
    return $null
}
function Sync-Url($url) {
    $hostName = ($url -replace '^https://','').Trim('/')
    Set-EnvVal 'PUBLIC_BASE_URL' $url
    Set-EnvVal 'PUBLIC_HOST' $hostName
    Set-Content -Path $state -Value $url -Encoding utf8 -NoNewline
    Log "URL baru -> recreate stack: $url"
    & docker compose --env-file $envf -f (Join-Path $root 'server/docker-compose.yml') up -d *>> (Join-Path $env:TEMP 'tunnel-up.log')
    # tunggu n8n sehat
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 3
        $c = curl.exe -s --max-time 4 -o NUL -w "%{http_code}" 'http://127.0.0.1:5678/healthz'
        if ($c -eq 200) { break }
    }
    # v3.5: WF03 pakai polling getUpdates - pastikan TIDAK ada webhook terdaftar
    #       (webhook aktif -> getUpdates 409 -> polling macet diam-diam)
    $tok = Get-EnvLine 'TELEGRAM_BOT_TOKEN'
    curl.exe -s --max-time 15 "https://api.telegram.org/bot$tok/deleteWebhook" | Out-Null
    # kabarkan link baru ke owner
    $chat = Get-EnvLine 'TELEGRAM_CHAT_ID'
    $msg  = [uri]::EscapeDataString(" Tunnel baru (dashboard): $url/stats")
    curl.exe -s --max-time 15 "https://api.telegram.org/bot$tok/sendMessage?chat_id=$chat&text=$msg" | Out-Null
    Log "deleteWebhook OK (polling mode)"
}

Log 'tunnel-up start'
while ($true) {
    Set-Content -Path $lock -Value (Get-Date -Format o) -Encoding utf8  # refresh lock tiap iterasi
    $alive = Get-Process cloudflared -ErrorAction SilentlyContinue
    $url = if ($alive) { Get-TunnelUrl } else { $null }

    if (-not $url) {
        $url = Start-Tunnel
        if (-not $url) { Log 'gagal start tunnel, retry 60s'; Start-Sleep -Seconds 60; continue }
        Log "tunnel started: $url"
    }

    $cur = (Get-EnvLine 'PUBLIC_BASE_URL').Trim()
    if ($url -ne $cur) {
        try { Sync-Url $url } catch { Log "sync error: $_" }
    } else {
        Set-Content -Path $state -Value $url -Encoding utf8 -NoNewline
    }
    Start-Sleep -Seconds 60
}
