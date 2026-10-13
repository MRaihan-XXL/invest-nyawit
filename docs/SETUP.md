# SETUP — dari nol sampai jalan 24/7

Ikuti urutannya. Bagian yang **wajib manual** (karena butuh login/klikmu): daftar
akun, OAuth sekali, tempel token. Sisanya otomatis.

## 0. Persiapan akun (sekali, ~1 jam)

### 0a. TikTok — rebrand akun lama
1. Buka @dewa_gacor20 → ganti nama jadi nama finds (mis. **@primefinds.id** juga,
   atau @gudang.finds). Ganti bio: "Barang unik harga mahasiswa 🔍".
2. Ganti ke **akun Kreator**: Pengaturan → Kelola akun → Alihkan ke Akun Kreator.
3. Hapus semua unggahan lama (kalau ada). Nama lama "gacor" = magnet masalah.

### 0b. Instagram
1. @primefinds.id → Settings → Account type → **Professional** (Creator).
2. Bikin juga **Facebook Page** (terhubung ke IG ini) — syarat Graph API.

### 0c. Telegram
1. Chat @BotFather → `/newbot` → simpan **token**.
2. Chat @userinfobot → catat **chat ID** kamu (untuk approval).

### 0d. Shopee Affiliate Open API
1. Daftar https://affiliate.shopee.co.id → aktivasi program affiliate.
2. Menu Open API / Developer → buat aplikasi → dapat **APPID + SECRET**.
3. **CATATAN PENTING (riset 13/10/2026):** Shopee Open Platform **hanya buka API
   untuk (a) Shopee Seller** (Individual/Registered Business) dengan ≥30 orders/30 hari
   di ID, **atau (b) ISV berbadan hukum (PT/CV)**. Affiliate tanpa toko / tanpa PT
   **tidak memenuhi syarat** — jangan buang waktu daftar Open Platform. Jalur legal:
   tetap pakai seed/manual (sudah jalan) atau tunggu undangan Shopee Affiliate
   API (invite-only untuk affiliate volume tinggi). Scraping = against ToS.
4. **Opsional** — tanpa APPID/SECRET sistem tetap jalan: WF01 (harvest) & WF05
   (laporan konversi) melewati cabang API Shopee **diam** (eksekusi tetap sukses).
   APPID hanya untuk harvest produk otomatis + laporan konversi; begitu kunci diisi
   di `.env` + recreate n8n, cabang itu otomatis aktif penuh.

### 0e. TikTok Developer (Content Posting API)
1. https://developers.tiktok.com → daftar (pakai email, bukan akun spam).
2. Create app → tambah produk **Content Posting API** → mode **Direct Post + Inbox**
   → aktifkan scope `video.upload` (inbox mode, tanpa audit).
3. Set redirect URI: **`https://<TUNNEL_URL>/oauth/tiktok`** — ganti `<TUNNEL_URL>`
   dengan URL trycloudflare aktif (cek `%TEMP%\tunnel-url.txt` atau `.env` `PUBLIC_BASE_URL`).
   **Wajib didaftarkan dulu di app console** (menu Redirect URIs) sebelum OAuth flow
   bisa mengembalikan `code` — kalau belum terdaftar, callback datang tapi `params` kosong.
4. Catat **Client Key + Client Secret** → isi `TIKTOK_CLIENT_KEY` + `TIKTOK_CLIENT_SECRET` di `.env`.
5. **URL verification (untuk submit review Live):** app console → URL properties →
   Verify by URL prefix → unduh file signature (mis. `tiktok-developer-site-verification.txt`)
   → taruh di folder `well-known/` di repo ini → file otomatis disajikan via
   `https://<TUNNEL_URL>/.well-known/<nama-file>` (Caddy → oauth-receiver). Verifikasi
   URL ini wajib sebelum Content Posting API bisa dipakai di mode Live.
6. **Review:** app review → tambahkan produk Content Posting API + Login Kit →
   upload demo video (pakai `test-pro-v1.mp4` atau hasil render) → Submit for review.
   Review bisa 1–4 minggu. Individual developer account (tanpa badan usaha) bisa
   submit review — business verification (org) hanya wajib untuk mini games/mini dramas
   atau saat butuh skala besar.

### 0f. Instagram Graph API
1. https://developers.facebook.com → Create App → tipe **Business** →
   tambah product **Instagram Graph API**.
2. Catat **App ID + App Secret**.

## 1. VPS Oracle Always Free (~15 menit)

1. https://www.oracle.com/cloud/free/ → daftar (kartu hanya verifikasi, tidak
   dicharge). Pilih region Asia (Singapore/Osaka) kalau tersedia.
2. Create Instance:
   - Shape: **VM.Standard.A1.Flex**, **2 OCPU / 12 GB RAM**
   - Image: **Ubuntu 24.04** (aarch64), boot volume 50 GB
3. Catat **IP publik** + buka port 80/443 di Security List (ingress rules).
4. Install Docker:
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo usermod -aG docker $USER && newgrp docker
   ```

## 2. DuckDNS (domain gratis)

1. https://www.duckdns.org → login GitHub/Google → buat subdomain, mis. `investmu`.
   Arahkan ke IP VPS.
2. Catat token untuk Caddy (opsional, auto-renew).
3. **Domain sekarang opsional.** Telegram WF03 polling lokal (`Schedule 15 detik` →
   `getUpdates`), bukan webhook — tidak ada `setWebhook`/URL publik untuk Telegram
   (webhook lama sudah dihapus via `deleteWebhook`). Publish juga upload file lokal
   (TikTok `FILE_UPLOAD` + IG multipart), bukan tarik URL — jadi **tidak butuh domain
   terverifikasi / `PUBLIC_MEDIA_URL`**. `https://DOMAIN/...` + tunnel
   (`scripts/tunnel-up.ps1`) hanya untuk akses remote dashboard opsional
   (dan redirect URI OAuth TikTok di §0e).

## 3. Deploy stack

```bash
scp -r invest-nyawit/ ubuntu@IP_VPS:/home/ubuntu/
ssh ubuntu@IP_VPS
cd invest-nyawit
cp .env.example .env && nano .env     # isi SEMUA nilai

# WAJIB sebelum up: buat hash basic auth untuk dashboard /stats
# (perhatikan: perintahnya diawali 'caddy' — image Caddy memakai CMD, bukan ENTRYPOINT;
#  --env-file .env juga wajib — compose tidak baca .env root secara otomatis)
docker compose --env-file .env -f server/docker-compose.yml run --rm --no-deps caddy caddy hash-password --plaintext 'pilih-kata-sandi-dashboard'
# tempel hasilnya (diawali $2a$/$2b$) ke .env → BASIC_AUTH_HASH, DENGAN kutip satu:
#   BASIC_AUTH_HASH='$2a$12$...'
nano .env

docker compose --env-file .env -f server/docker-compose.yml up -d --build
```

Cek: `docker compose --env-file .env -f server/docker-compose.yml ps` (semua Up),
buka `https://investmu.duckdns.org` → halaman login n8n (user/pass dibuat sekali).

Dashboard: LAN `http://192.168.18.228:8091/stats` (user/pass = `STATS_USER` + kata
sandi yang tadi di-hash), atau remote `https://investmu.duckdns.org/stats` lewat tunnel
(opsional). Link-in-bio publik via GitHub Pages:
`https://mraihan-xxl.github.io/invest-nyawit/bio.html` (langkah §8).

Kuota harian: `POSTS_PER_DAY_ID=4` di `.env` → maksimal **4 video/hari** (track ID).
WF04 "Pick Approved" berhenti saat sudah 4 post TikTok/hari, karena limit API TikTok
= 5 pending/24 jam.

## 4. Import workflow n8n

1. Dashboard n8n → **Workflows → Import from File** → ulangi untuk 6 file di
   folder `workflows/` (termasuk `06-strategy-analyst`).
2. Di tiap node Postgres (ditandai `REPLACE_ME`) → pilih/isi kredensial:
   host `postgres`, port 5432, DB/user/password = nilai `.env`.
3. Workflow `03-approval-telegram` sekarang **polling lokal, bukan webhook**:
   Schedule 15 detik → node `Get Updates` (`getUpdates`, offset disimpan di
   staticData) → routing approval lama. Isi `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`
   di `.env` (node baca env, bukan kredensial Telegram terpisah). Tidak perlu
   `setWebhook`, URL publik, atau tunnel untuk Telegram — webhook lama sudah dihapus
   via `deleteWebhook`.
4. Activate (toggle) semua workflow.

## 5. OAuth sekali — isi tabel tokens

> **Wajib untuk publish.** Kalau tabel `tokens` kosong (TikTok / Instagram), WF04 error
> `Token ... belum diisi di tabel tokens` tiap 30 menit — itu sinyal token belum diisi,
> bukan bug. Kerjakan langkah OAuth di bawah sekali; refresh token jalan sendiri.

**Cara kerja receiver:** `scripts/oauth-receiver.js` jalan sebagai background process
di port 8099 (host). Caddy (`:80` block) meneruskan `/oauth/*` dan `/.well-known/*`
ke `host.docker.internal:8099`. Callback disimpan ke `%TEMP%\oauth-callback.json`.
Receiver punya endpoint `/health` untuk watchdog.

### TikTok (scope `video.upload`)
1. Pastikan redirect URI `https://<TUNNEL_URL>/oauth/tiktok` **sudah didaftarkan** di
   app console (lihat §0e langkah 3). Kalau belum, callback datang tapi `params` kosong.
2. Buka link authorize (ganti CLIENT_KEY & TUNNEL_URL):
   ```
   https://www.tiktok.com/v2/auth/authorize/?client_key=CLIENT_KEY&scope=video.upload&response_type=code&redirect_uri=https://TUNNEL_URL/oauth/tiktok&state=xyz
   ```
3. Setujui → redirect ke receiver → buka `%TEMP%\oauth-callback.json` → salin `code`.
4. Tukar token:
   ```bash
   curl -X POST https://open.tiktokapis.com/v2/oauth/token/ \
     -d "client_key=KEY" -d "client_secret=SECRET" \
     -d "code=CODE" -d "grant_type=authorization_code" \
     -d "redirect_uri=https://TUNNEL_URL/oauth/tiktok"
   ```
5. Simpan (ganti nilai dlm SQL):
   ```sql
   INSERT INTO tokens (platform, access_token, refresh_token, expires_at, extra)
   VALUES ('tiktok', 'ACCESS_TOKEN', 'REFRESH_TOKEN', now() + interval '1 day', '{}')
   ON CONFLICT (platform) DO UPDATE SET access_token = EXCLUDED.access_token,
     refresh_token = EXCLUDED.refresh_token, expires_at = EXCLUDED.expires_at;
   ```
   (Workflow refresh otomatis tiap 18 jam — setelah ini kamu tidak perlu sentuh.)

### Instagram (long-lived token)
1. Dapatkan user token dulu (Graph API Explorer / OAuth) dengan scope
   `instagram_basic,instagram_content_publish,pages_show_list,instagram_manage_insight`.
   Terakhir = untuk AI analis membaca performa konten (plays/likes/saves) —
   centang juga **Instagram API → Insights** di dasbor Facebook developers
   (form app jadi sedikit lebih panjang, tapi tidak ada biaya).
2. Tukar ke long-lived (60 hari):
   ```
   https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=USER_TOKEN
   ```
3. Ambil IG user id (pakai token tsb):
   ```
   https://graph.facebook.com/v21.0/me/accounts?access_token=LONGLIVED_TOKEN
   ```
   lalu `GET /{page-id}?fields=instagram_business_account&access_token=...`
4. Simpan:
   ```sql
   INSERT INTO tokens (platform, access_token, refresh_token, expires_at, extra)
   VALUES ('instagram', 'LONGLIVED_TOKEN', '', now() + interval '60 days',
           '{"ig_user_id": "IG_USER_ID"}')
   ON CONFLICT (platform) DO UPDATE SET access_token = EXCLUDED.access_token,
     expires_at = EXCLUDED.expires_at, extra = EXCLUDED.extra;
   ```

## 6. Seed produk EN (Track B)

Edit `data/seed_en_offers.sample.sql` (ganti URL afiliasi milikmu), lalu masukkan
ke DB. Langkah ini bisa ditunda — Track ID jalan tanpa ini.

## 7. Uji end-to-end

1. Jalankan manual workflow `01` (Execute Workflow) → cek `SELECT count(*) FROM products;`
2. Jalankan `02` → harus muncul video preview di Telegram dalam 2–5 menit.
3. Tap ✅ → jalankan `04` manual → cek TikTok inbox (notifikasi post) + IG feed.
   Kalau muncul error `Token ... belum diisi di tabel tokens` → isi token dulu (§5).
4. Buka dashboard (`http://192.168.18.228:8091/stats` atau `https://DOMAIN/stats`) →
   KPI terisi (bisa dummy dulu: INSERT 1 baris ke `conversions`) dan link-in-bio
   GitHub Pages (§8) tampil 15 kartu produk.
5. Jalankan `06` manual → proposal strategi masuk Telegram; tap ✅ → eksekutor
   (01/02) pakai strategi itu di run berikutnya.
6. Semua hijau? Biarkan jadwalnya jalan sendiri. Kamu cuma perlu buka Telegram
   5 menit/hari.

## 8. Link-in-bio publik gratis (GitHub Pages)

`docs/bio.html` (15 kartu produk, link afiliasi `s.shopee.co.id`) disajikan gratis
dari folder `/docs` repo ini — tanpa VPS/domain:

1. Push repo ke GitHub.
2. Repo → **Settings → Pages** → Source: **Deploy from branch** → branch `main`,
   folder **`/docs`** → Save.
3. Tunggu 1–2 menit → `https://mraihan-xxl.github.io/invest-nyawit/bio.html`.
4. Tempel URL itu sebagai link di bio TikTok/IG (tujuan klik dari video).

## 9. Tunnel 24/7 + Scheduled Tasks (otomasi Windows)

Sistem ini dirancang jalan di PC Windows (bukan VPS). Tiga scheduled task menjaga
semua tetap hidup tanpa intervensi manual:

| Task | Jadwal | Fungsi |
|---|---|---|
| `invest-nyawit-tunnel-up-min` | Setiap 10 menit | Jalankan `scripts/tunnel-up.ps1` (loop abadi): pastikan cloudflared hidup, sinkron URL baru ke `.env`, recreate stack, hapus webhook Telegram, notifikasi URL baru. Lock file cegah instance ganda. |
| `invest-nyawit-backup-db` | Harian 03:00 | `scripts/backup-db.ps1`: pg_dump via docker exec → compress gzip → simpan di `D:\FlyEnv-Data\backup\invest-nyawit\` → rotasi 7 hari. Ringkasan mingguan (Senin) dikirim ke Telegram. |
| `invest-nyawit-watchdog` | Setiap 10 menit | `scripts/watchdog.ps1`: cek cloudflared, semua container docker, n8n healthz, dashboard health, oauth-receiver health, sinkronisasi tunnel URL. Alert Telegram bila ada yang mati. |

**Manual (sekali):** buat scheduled task via admin:
```powershell
schtasks /create /tn "invest-nyawit-tunnel-up-min" /tr "powershell -ExecutionPolicy Bypass -File 'D:\...\scripts\tunnel-up.ps1'" /sc minute /mo 10 /f
schtasks /create /tn "invest-nyawit-backup-db" /tr "powershell -ExecutionPolicy Bypass -File 'D:\...\scripts\backup-db.ps1'" /sc daily /st 03:00 /f
schtasks /create /tn "invest-nyawit-watchdog" /tr "powershell -ExecutionPolicy Bypass -File 'D:\...\scripts\watchdog.ps1'" /sc minute /mo 10 /f
```

**OAuth receiver:** jalankan manual (atau via startup shortcut):
```powershell
node scripts\oauth-receiver.js
```
Receiver listen di `:8099` (host), punya `/health` untuk watchdog, serve file
`/.well-known/*` dari folder `well-known/` (untuk verifikasi URL TikTok), dan simpan
callback OAuth ke `%TEMP%\oauth-callback.json`.

## Troubleshooting cepat

| Gejala | Penyebab | Solusi |
|---|---|---|
| edge-tts 403 | versi lama | `pip install -U edge-tts` di dalam container render |
| TikTok init error `unaudited...` | pakai direct post | pastikan endpoint `/inbox/video/init/` (bukan `/publish/video/init/`) |
| IG container stuck IN_PROGRESS | video > 60 dtk / transcode lambat | tunggu; kalau timeout, cek `SELECT * FROM posts ORDER BY id DESC` |
| Render gagal "image fetch" | CDN Shopee blokir | otomatis pakai placeholder; ganti gambar kalau sering |
| Workflow diam tanpa error | kredensial belum di-attach | buka node bertanda REPLACE_ME, pilih credential |
| WF04 error `Token ... belum diisi di tabel tokens` tiap 30 menit | tabel `tokens` kosong | ikuti langkah OAuth §5 — sinyal token belum diisi, bukan bug |
| Telegram tidak merespons tap ✅ | polling WF03 tidak jalan | cek `TELEGRAM_BOT_TOKEN` di `.env` + node `Poll Schedule`/`Get Updates` (webhook tidak dipakai) |
| WF01/WF05 dilewati senyap untuk Shopee | `SHOPEE_AFFILIATE_APPID`/`SECRET` kosong | perilaku fail-soft; isi `.env` + recreate n8n (§0d) |
| Caddy restart loop di awal | `BASIC_AUTH_HASH` bukan bcrypt | hash ulang dengan `caddy hash-password`; pakai kutip satu di `.env` |
| `/stats` 401 terus | user/pass salah | cocokkan `STATS_USER` + kata sandi yang di-hash (bukan hash-nya) |
