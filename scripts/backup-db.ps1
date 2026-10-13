# backup-db.ps1 - backup harian PostgreSQL via docker exec pg_dump, rotasi 7 hari.
# Dijalankan scheduled task (harian). Token dibaca dari .env saat runtime.

$ErrorActionPreference = 'SilentlyContinue'
$root  = 'D:\FlyEnv-Data\server\www\invest-nyawit'
$envf  = Join-Path $root '.env'
$outDir = 'D:\FlyEnv-Data\backup\invest-nyawit'
$keep   = 7

function Log($m) {
    Add-Content -Path (Join-Path $env:TEMP 'backup-db.log') -Value ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m)
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
$lock = Join-Path $env:TEMP 'backup-db.lock'
if (Test-Path $lock) {
    $lockAge = (Get-Date) - (Get-Item $lock).LastWriteTime
    if ($lockAge.TotalMinutes -lt 30) { exit }
}
Set-Content -Path $lock -Value (Get-Date -Format o) -Encoding utf8

try {
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }

    $user = Get-EnvLine 'POSTGRES_USER'
    $db   = Get-EnvLine 'POSTGRES_DB'
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $file = Join-Path $outDir "investnyawit-$stamp.sql.gz"

    # pg_dump di dalam container postgres, compress via gzip
    $dump = docker exec invest-nyawit-postgres-1 sh -c "pg_dump -U $user $db" 2>$null
    if (-not $dump) {
        Log 'pg_dump gagal (container mati / auth error)'
        Send-Telegram '[invest-nyawit] BACKUP GAGAL - pg_dump kosong. Cek container postgres.'
        exit 1
    }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes(($dump -join "`n"))
    $gzip = [System.IO.Compression.GzipStream]::new(
        [System.IO.FileStream]::new($file, [System.IO.FileMode]::Create),
        [System.IO.Compression.CompressionLevel]::Optimal)
    $gzip.Write($bytes, 0, $bytes.Length)
    $gzip.Dispose()

    $sizeMB = [math]::Round((Get-Item $file).Length / 1MB, 2)
    Log "backup OK: $file ($sizeMB MB)"

    # rotasi: hapus file lebih dari $keep hari
    Get-ChildItem $outDir -Filter 'investnyawit-*.sql.gz' |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$keep) } |
        Remove-Item -Force
    Log 'rotasi selesai'

    # ringkas seminggu sekali (Senin) saja ke Telegram; harian cukup log
    if ((Get-Date).DayOfWeek -eq 'Monday') {
        Send-Telegram "[invest-nyawit] Backup DB harian OK: $sizeMB MB ($((Get-ChildItem $outDir -Filter '*.sql.gz').Count) file tersimpan)"
    }
} finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
