# invest-nyawit — start Cloudflare Quick Tunnel, kirim URL baru ke Telegram.
# Dipanggil scheduled task saat logon. URL quick tunnel selalu BEDA tiap start,
# jadi script ini wajib kirim link terbaru ke chat Telegram pemilik.
$ErrorActionPreference = 'Stop'

$envFile = 'D:\FlyEnv-Data\server\www\invest-nyawit\.env'
$urlFile = 'D:\FlyEnv-Data\server\www\invest-nyawit\.tunnel-url'
$cfExe   = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'

# 1. Bunuh cloudflared lama (kalau ada)
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# 2. Baca .env (token bot + chat id)
$envMap = @{}
Get-Content $envFile | Where-Object { $_ -match '^[A-Z_]+=.*' } | ForEach-Object {
  $i = $_.IndexOf('='); if ($i -gt 0) { $envMap[$_.Substring(0,$i)] = $_.Substring($i+1).Trim("'") }
}
$bot  = $envMap['TELEGRAM_BOT_TOKEN']
$chat = $envMap['TELEGRAM_CHAT_ID']

function Send-Tg([string]$text) {
  $body = @{ chat_id = $chat; text = $text } | ConvertTo-Json -Compress
  $tmp = [System.IO.Path]::GetTempFileName()
  [System.IO.File]::WriteAllText($tmp, $body, [System.Text.UTF8Encoding]::new($false))
  try { Invoke-RestMethod -Uri "https://api.telegram.org/bot$bot/sendMessage" -Method Post -ContentType 'application/json' -InFile $tmp -TimeoutSec 30 | Out-Null }
  catch { Write-Output "TG FAIL: $($_.Exception.Message)" }
  finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

# 3. Start tunnel (log ke file; URL muncul di stderr)
$logErr = Join-Path ([System.IO.Path]::GetTempPath()) 'cf-tunnel.log'
if (Test-Path $logErr) { Remove-Item $logErr -Force }
$proc = Start-Process -FilePath $cfExe -ArgumentList 'tunnel','--url','http://localhost:8091','--no-autoupdate' `
  -RedirectStandardError $logErr -RedirectStandardOutput "$logErr.out" -PassThru -WindowStyle Hidden

# 4. Tunggu URL (maks 60 dtk)
$url = $null
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 2
  if (Test-Path $logErr) {
    $c = Get-Content $logErr -Raw -ErrorAction SilentlyContinue
    if ($c -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $url = $Matches[0]; break }
  }
  if ($proc.HasExited) { break }
}

if ($url) {
  Set-Content -Path $urlFile -Value $url -NoNewline
  $msg = "Tunnel aktif!`nDashboard: $url/stats`nUser: admin`nPassword: nyawit2026`nBio (publik): $url/bio`n`nCatatan: link berganti tiap PC restart - pesan ini otomatis terkirim ulang."
  Send-Tg $msg
} else {
  Send-Tg "Cloudflare tunnel GAGAL start. Cek log: $logErr"
}

# 5. Biarkan proses tetap hidup (script exit, process orphan = jalan terus)
Write-Output "TUNNEL_URL=$url"
