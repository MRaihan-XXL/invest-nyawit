# Tutorial Lengkap: Nol Sampai Duit

Panduan operasional invest-nyawit dari hari pertama sampai penarikan komisi.
Baca sekali penuh (~10 menit), sisanya tinggal jalanin.

---

## 1. Ini bisnis apa, jujur

Kamu punya **pabrik konten afiliasi otomatis 24 jam**:

```
AI cari produk (Shopee ID / SaaS EN)
  → AI buat naskah + render video (TTS + ffmpeg)
  → AI nilai sendiri (gerbang skor)
  → Kamu tap ✅ di Telegram (1 ketukan per konten)
  → Sistem tayang: TikTok (mode inbox) + Instagram Reels (full auto)
  → Pembeli klik link kamu → komisi masuk
  → AI analis pantau angka tiap hari, kalau turun dia diagnosis + usul strategi
  → Kamu cek semua lewat link: /stats (dashboard) + laporan Telegram
```

**Yang otomatis penuh:** riset produk, naskah, render, kurasi AI, tayang di IG,
analisis harian, deteksi penurunan, laporan.
**Yang butuh kamu (±2 menit/hari):** tap ✅ approval di Telegram + tap *Post*
di TikTok (aturan TikTok: video dari API harus dikonfirmasi manual di app —
bukan kelemahan sistem, itu batas platform).

---

## 2. Produknya apa aja

Dua jalur (track) berjalan paralel, jatah terpisah per hari:

| Track | Sumber | Produk | Komisi | Kapan |
|---|---|---|---|---|
| **ID** | Shopee Affiliate | 8 niche impulse-buy 15rb–150rb: rumah-tangga, dapur, gadget-kecil, kesehatan, parenting, otomotif-kecil, fashion-murah, alat kerja | 3–10% per sale (validasi Shopee 1–2 minggu) | Setiap hari |
| **EN** | Program afiliasi SaaS seed-list | Tools AI/notion/scripting dengan recurring commission | $5–50/akun/bulan | Setiap hari |

- AI memilih produk sendiri lewat skor kurasi (harga × komisi × tren × poin masuk akal),
  otomatis buang yang lewat batas (harga >300rb, rating <4, dsb).
- Strategi bisa diubah AI analis (keyword, gaya hook, kuota) — kamu approve lewat tombol.
- Link shortener + asosiasi token: atribusi per-akun (TikTok) dan per-video
  untuk IG — jadi kamu tahu konten mana yang menghasilkan.

## 3. Jam berapa upload

Semua jam dalam **WIB** (server pakai TZ Asia/Jakarta):

| Aktivitas | Jam | Keterangan |
|---|---|---|
| Riset produk | 03:00 (tiap hari) | workflow 01 — ambil kandidat segar |
| **Produksi + tayang** | **07:00 · 12:00 · 19:00 · 21:00** | workflow 02 — slot prime time ID (pagi commuter, makan siang, malam scroll, prime malam) |
| Tarik metrik + laporan | 06:00 (tiap hari) | workflow 05 — ringkasan Telegram harian |
| Tarik insights IG + analisis AI | 05:00 (tiap hari) | workflow 06 — diam kalau sehat, nyala kalau ada penurunan |
| Ringkasan mingguan | Minggu 08:00 | dari workflow 05 |

Quota default per hari: ID 3 + EN 2 (total 5 video). Bisa diubah oleh AI analis
(lewat tombol approve di Telegram) dalam rentang aman 0–6 ID / 0–4 EN.

**Kenapa 19:00–21:00:** jam prime ID; tapi ingat — video TikTok baru benar-benar
"live" setelah kamu tap Post, jadi rentang tayang ≈ jam slot + beberapa menit
sampai kamu sempat approve.

## 4. Alur sampai duit (realistis, tanpa janji)

```
Minggu 1–2   Setup sekali (SETUP.md) + akun affiliate + kumpulkan 600 follower TikTok
             (syarat full-mode TikTok Shop; sebelum itu pakai Link-Share Only — tetap jalan)
Minggu 2–4   IG mulai dapat impresi; TikTok belajar algoritma; komisi pertama biasa
             muncul sebagai order kecil (Rp500–5.000/order)
Bulan 2–3    Kalau konsisten 5 video/hari: order naik, AI sudah beberapa iterasi
             strategi; komisi bulanan realistis di orde Rp100rb–jutaan (bukan garansi)
Penarikan   Shopee: minimum Rp10 · pembayaran mingguan · validasi komisi 1–2 minggu
             SaaS EN: minimum payout masing-masing program
```

Cek duit di: `https://domain-kamu/stats` (password) → kartu *Income hari ini /
7 hari / 30 hari* + grafik harian. Atau laporan Telegram tiap pagi.

## 5. Rutinitas harian kamu (±2 menit)

1. **Pagi** — buka Telegram: baca laporan harian (income, funnel, error).
2. **Kapanpun** — muncul notifikasi "konten siap": tap ✅ (atau ❌ kalau jelek;
   penolakan dicatat AI untuk belajar).
3. **Kalau AI kirim 🚨 PENURUNAN** — baca diagnosisnya, tap ✅ untuk terapkan
   strategi pemulihan (atau ❌ kalau kamu tidak setuju).
4. **Sesekali** — buka `https://domain-kamu/stats` untuk gambaran besar.
5. **Tiap hari yang sama** — tap *Post* di app TikTok untuk antrian inbox.

### Tambah produk manual (karena Shopee API belum dibuka)

Kalau kamu nemu produk bagus di Shopee tapi API-nya belum aktif, kirim langsung ke bot:

```
/produk <url_afiliasi> <harga> <judul>
```

Contoh:
```
/produk https://shopee.co.id/product/12345/67890 150000 Power Bank 20000mAh Fast Charging
```

- Bot langsung masukin ke kurasi (status `new`, skor 75) — render berikutnya otomatis pakai.
- URL yang sama dikirim ulang → data diperbarui, tidak duplikat.
- Format salah → bot balas cara pakai yang benar.
- Hanya pemilik bot (chat ID kamu) yang bisa tambah produk; pesan lain diabaikan.

Tidak ada lagi yang perlu dikerjakan manual. Kalau kamu libur sehari pun:
antrian menunggu, IG tetap tayang, laporan tetap jalan.

## 6. Otak adaptif: bagaimana AI "berpikir kayak pembisnis"

Workflow **06-strategy-analyst** jalan **tiap hari** (05:00 WIB):

1. Tarik metrik nyata: income 7d vs 7d sebelumnya, AOV, approval rate,
   drop rate, performa per jam posting, per platform, konten terbaik/jelek.
2. **Kalau sehat** → `skip`, diam, tidak spam kamu.
3. **Kalau Minggu** → ulasan mingguan penuh (proposal baru, tombol approve).
4. **Kalau income turun ≥25% atau drop rate ≥40%** → 🚨 alarm:
   diagnosis akar masalah dari data (bukan tebakan), lalu usul **1–2 perubahan
   terukur** — bukan rombak semua. Prinsipnya Pareto: potong yang rugi,
   gandakan yang menang, uji kecil dulu.
5. Strategi baru **tidak aktif sendiri** — tunggu kamu tap ✅ (kamu tetap boss).

Kandidat strategi + riwayat health score terlihat di `/stats` → panel *Strategi*.

## 7. Checklist hari pertama

- [ ] Ikuti `SETUP.md` sampai selesai (registrasi token = bagian yang tidak bisa diotomasi: KTP, rekening, akun medsos).
- [ ] Set `HANDLE_ID`, `HANDLE_EN`, `SITE_HANDLE` di `.env` (rebrand akun lama).
- [ ] Aktifkan 6 workflow di n8n, cek biru semua (jadwal di atas otomatis nyangkut).
- [ ] Test 1 konten end-to-end: render → approve → tayang.
- [ ] Buka `https://domain-kamu/stats` sekali — pastikan KPI muncul.
- [ ] Set reminder: tiap hari cek Telegram + tap Post TikTok.

## 8. Kalau ada masalah

- Telegram tidak masuk → cek `TELEGRAM_BOT_TOKEN` / chat id, lihat log n8n.
- `/stats` minta password → user `STATS_USER`, hash `BASIC_AUTH_HASH` (lihat SETUP).
- Video gagal render → lihat tab *Log error* di `/stats`, umumnya font/ffmpeg/TTS.
- Detail penuh: `SETUP.md` bagian Troubleshooting.

---

*Sistem ini alat, bukan mesin uang instan. Yang membedakan hasil: konsistensi
tayang + keberanian approve strategi yang berbasis data. Semua keputusan tetap di tangan kamu.*
