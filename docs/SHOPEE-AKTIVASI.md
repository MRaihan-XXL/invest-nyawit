# Aktivasi Shopee Affiliate — akses form & kenapa dibutuhkan

Status per 13 Okt 2026: kolom `price_min` produk masih NULL karena Shopee
memblokir endpoint harga.

## Kenapa dibutuhkan

- Endpoint harga (`api/v4/pdp/get_pc` / `api/v4/item/get`) mengembalikan
  `{"error":90309999,"is_login":false}` — diuji dari server DAN dari browser
  yang sudah login → harga hanya tersedia lewat jalur resmi (approval API).
- Tanpa harga: panel "Riwayat Harga" di dashboard menampilkan status kosong
  jujur, produk tidak punya harga, komisi tidak bisa diestimasi dari harga.
- Data komisi/konversi (conversionReport) SUDAH jalan — ini hanya soal
  harga produk.

## Jalur 1 (utama): formulir resmi Pusat Bantuan

Formulir langsung "Shopee Affiliate Program":

https://help.shopee.co.id/portal/webform/be6d30743a0446a28b3a246a99ec7a89

(Isi: akun Shopee terkait, kendala "butuh akses data harga / aktivasi API
afiliasi", media yang dipakai, sertakan screenshot error 90309999 bila diminta.)

## Jalur 2 (kalau form tidak muncul): Live Chat

1. Buka aplikasi Shopee → tab **Saya** → **Pusat Bantuan**.
2. Pilih kategori Affiliate / ketik "Shopee Affiliate" di pencarian.
3. Minta diarahkan ke formulir aktivasi / akses Open API.

Alamat yang sama sering hanya bisa dibuka dari link resmi di help center —
itulah kenapa sulit ditemukan dari pencarian manual.

## Cek status aktivasi

- Menu **Shopee Affiliate** di aplikasi (status akun).
- Email dengan subjek **"Selamat! Kamu Sudah Bergabung di Shopee Affiliate
  Program"** — cek juga folder **Spam** dan **Promotions**.

## Setelah akses aktif (untuk sistem ini)

1. Beri tahu operator: harga perlu masuk ke `products.price_min`.
2. Tabel `price_history` sudah siap — snapshot otomatis tinggal disambungkan
   ke sumber harga yang valid; panel dashboard langsung menampilkan
   `% total` dan `%/hari` begitu ada ≥2 snapshot per produk.
3. Konversi tetap lewat conversionReport (sudah jalan, tidak perlu diubah).

## Referensi

- Pusat Bantuan Shopee: https://help.shopee.co.id/
- S&K Program Afiliasi Individu: https://help.shopee.co.id/portal/4/article/71217
