# invest-nyawit

Pabrik konten afiliasi otomatis 24/7 — AI bikin video, AI nilai sendiri, kamu cuma
approve lewat Telegram, sistem yang tayang ke TikTok (mode inbox) + Instagram Reels.

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
              [06] AI analis mingguan → usul strategi baru → kamu approve
                       │
                       └──► eksekutor (01/02) patuh strategi aktif
                       
  Dashboard: https://DOMAIN/stats (KPI + chart + tabel, auto-refresh, basic auth)
  Link-in-bio: https://DOMAIN/bio (publik — tujuan klik dari video)
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
| `docs/SETUP.md` | **baca ini** — langkah daftar Oracle/TikTok/Shopee/IG/Telegram |
| `docs/NICHE.md` | strategi niche dual-track ID + EN |
| `docs/demo/` | bukti render asli: `demo01.mp4` (16,7 dtk) + 2 frame |
| `scripts/validate-workflows.js` | validasi struktur workflow (`node scripts/validate-workflows.js`) |

## Deploy singkat

1. Ikuti `docs/SETUP.md` (registrasi akun + token + hash basic auth dashboard).
2. Salin folder ini ke VPS (Oracle Always Free), buat `.env` dari `.env.example`.
3. `docker compose --env-file .env -f server/docker-compose.yml up -d --build`
   (`--env-file .env` WAJIB: compose tidak otomatis baca `.env` root saat file compose ada di subfolder `server/`).
4. Buka `https://DOMAIN-KAMU` → login n8n → import 6 file dari `workflows/`.
5. Set kredensial (Postgres, Telegram Bot) di tiap node yang bertanda REPLACE_ME.
6. Aktifkan semua workflow.
7. Cek `https://DOMAIN-KAMU/stats` (user/pass dari `.env`) dan `/bio` (publik).

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
video tayang → penonton buka DOMAIN/bio → klik produk → checkout di Shopee/TikTok
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
- Maksimal 3-5 post/hari/akun. Jangan pernah pakai bot auto-like/auto-comment.
- Satu orang satu kepemilikan akun; jangan pinjam akun teman.
- Semua konten melewati gate AI + approval kamu. Kalau ragu, tap ❌.
- Konten judi/slot/kesehatan berlebihan = banned. Diblokir oleh gate, tapi tetap
  jangan diloloskan manual.
