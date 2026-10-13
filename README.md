# invest-nyawit

Pabrik konten afiliasi otomatis 24/7 — AI bikin video, AI nilai sendiri, kamu cuma
approve lewat Telegram, sistem yang tayang ke TikTok (mode inbox) + Instagram Reels.

> **Baru mulai?** Baca [`docs/TUTORI.md`](docs/TUTORI.md) — tutorial lengkap nol → duit
> (produknya apa, jam berapa upload, rutinitas harian, cara cek penghasilan).

```
Shopee Affiliate API ──┐
                       ▼
              [01] harvest produk (harian, skor kurasi, keywords dari strategi)
                       ▼
              [02] naskah LLM → gate AI → render video → preview Telegram
                       ▼
              [03] kamu tap ✅ / ❌ di Telegram (naskah + strategi)
                       ▼
              [04] publish TikTok (inbox) + IG Reels + refresh token
                       ▼
              [05] tarik komisi HARIAN → laporan mingguan ke Telegram
                       ▼
               [06] AI analis HARIAN adaptif → deteksi penurunan → diagnosis → usul strategi → kamu approve
                       │
                       └──► eksekutor (01/02) patuh strategi aktif
                       
  Dashboard: http://192.168.18.228:8091/stats (KPI + chart + tabel, auto-refresh, basic auth)
             (remote opsional via tunnel: https://DOMAIN/stats)
  Link-in-bio: https://mraihan-xxl.github.io/invest-nyawit/bio.html (docs/bio.html, GitHub Pages)
```

## Isi folder

| Path | Fungsi |
|---|---|
| `server/` | docker-compose: n8n + Postgres + render + **dashboard** + Caddy (HTTPS) |
| `services/render/` | mesin video: edge-tts + ffmpeg → MP4 9:16 (verified jalan) |
| `services/dashboard/` | dashboard `/stats` + link-in-bio `/bio` (Python + psycopg) |
| `workflows/` | 6 workflow n8n — import ke dashboard setelah deploy |
| `data/schema.sql` | skema DB (auto-load saat compose pertama jalan) |
| `data/seed_en_offers.sample.sql` | contoh seed produk afiliasi EN |
| `docs/TUTORI.md` | **tutorial lengkap nol → duit**: produk, jam tayang, rutinitas harian |
| `docs/SETUP.md` | **baca ini** — langkah daftar Oracle/TikTok/Shopee/IG/Telegram |
| `docs/NICHE.md` | strategi niche dual-track ID + EN |
| `docs/bio.html` | link-in-bio 15 kartu produk → disajikan gratis via GitHub Pages (folder `/docs`) |
| `docs/demo/` | bukti render asli: `demo01.mp4` (16,7 dtk) + 2 frame |
| `scripts/validate-workflows.js` | validasi struktur workflow (`node scripts/validate-workflows.js`) |

## Deploy singkat

1. Ikuti `docs/SETUP.md` (registrasi akun + token + hash basic auth dashboard).
2. Salin folder ini ke VPS (Oracle Always Free), buat `.env` dari `.env.example`.
3. `docker compose --env-file .env -f server/docker-compose.yml up -d --build`
   (`--env-file .env` WAJIB: compose tidak otomatis baca `.env` root saat file compose ada di subfolder `server/`).
4. Buka `https://DOMAIN-KAMU` → login n8n → import 6 file dari `workflows/`.
5. Set kredensial Postgres di tiap node yang bertanda REPLACE_ME; token Telegram cukup
   dari `TELEGRAM_BOT_TOKEN` di `.env` (node baca env, bukan kredensial terpisah).
6. Isi token OAuth TikTok + Instagram ke tabel `tokens` (langkah OAuth di `docs/SETUP.md` §5).
7. Aktifkan semua workflow.
8. Cek dashboard (LAN `http://192.168.18.228:8091/stats` atau `https://DOMAIN-KAMU/stats`
   lewat tunnel — user/pass dari `.env`) dan link-in-bio GitHub Pages (`docs/bio.html`).

> **Catatan sistem v3.5:**
> - **Telegram = polling lokal.** WF03: Schedule 15 detik → `getUpdates` (offset disimpan
>   di staticData) → routing approval. Webhook sudah dihapus (`deleteWebhook`) — tidak ada
>   `setWebhook`/URL publik untuk Telegram. Tunnel (`scripts/tunnel-up.ps1`) opsional,
>   **hanya untuk dashboard remote**, bukan untuk webhook.
> - **Publish = upload lokal.** WF04 pakai TikTok INBOX mode `FILE_UPLOAD` (video_size/chunk,
>   PUT `upload_url`) + IG container multipart (`upload_type=VIDEO_FILE`) → **tidak butuh
>   domain terverifikasi, tidak butuh `PUBLIC_MEDIA_URL`**. `PUBLIC_BASE_URL`/`PUBLIC_HOST`/
>   `PUBLIC_MEDIA_URL` hanya relevan untuk akses remote opsional.
> - **Kuota maksimal 4 video/hari** (track ID, `POSTS_PER_DAY_ID=4`); WF04 "Pick Approved"
>   berhenti saat sudah 4 post TikTok/hari karena limit API TikTok = 5 pending/24 jam.
> - **Publish wajib token OAuth di tabel `tokens`** (TikTok + Instagram). Kalau kosong, WF04
>   error `Token ... belum diisi di tabel tokens` tiap 30 menit — itu sinyal token belum diisi,
>   bukan bug.
> - **APPID/SECRET Shopee opsional.** Kosong → cabang API Shopee di WF01/WF05 dilewati diam
>   (eksekusi tetap sukses). Isi `.env` + recreate n8n → harvest otomatis + laporan konversi
>   aktif penuh.

## Test lokal (tanpa VPS)

```powershell
# render sekali
services\render\.venv\Scripts\python.exe services\render\render.py --job job.json --out out

# atau jalankan service + kirim POST /render
services\render\.venv\Scripts\python.exe services\render\render.py --serve --port 8090 --media ./media

# validasi workflow
node scripts\validate-workflows.js

# dashboard lokal (butuh Postgres yang sudah jalan + env PG*):
# python services\dashboard\app.py   → http://localhost:8091/stats
```

## Alur sampai duit (jujur, tanpa janji muluk)

```
video tayang → penonton buka link-in-bio (GitHub Pages) → klik produk → checkout di Shopee/TikTok
→ komisi tercatat (estimasi) → order tervalidasi 1-2 minggu → tarik ke rekening
  via dashboard Shopee Affiliate / TikTok Shop
```

- Income **estimasi** tampil real-time di `/stats` (data ditarik harian).
- Atribusi per-VIDEO tidak tersedia: laporan Shopee tidak mengembalikan subId.
- Batas awal TikTok Shop Affiliate: mode Link-Share Only (0 follower) → full mode
  setelah 600 follower. Ini target pertama.

## License

**All rights reserved.** Repo ini publik untuk tujuan portofolio — boleh DIBACA,
tapi DILARANG menyalin, mendistribusikan ulang, atau menjual ulang isi program
ini tanpa izin tertulis. Tidak ada lisensi open source yang diberikan.

## Aturan main (resiko minimum — jangan dilanggar)

- TikTok **mode inbox** saja (tanpa audit API). Kamu tap Post di app = post normal.
- Maksimal 4 video/hari (kuota sistem: `POSTS_PER_DAY_ID=4` + WF04 berhenti saat sudah
  4 post TikTok/hari — limit API TikTok = 5 pending/24 jam). Jangan pernah pakai bot auto-like/auto-comment.
- Satu orang satu kepemilikan akun; jangan pinjam akun teman.
- Semua konten melewati gate AI + approval kamu. Kalau ragu, tap ❌.
- Konten judi/slot/kesehatan berlebihan = banned. Diblokir oleh gate, tapi tetap
  jangan diloloskan manual.
