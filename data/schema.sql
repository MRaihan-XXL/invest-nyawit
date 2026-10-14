-- invest-nyawit — skema database (auto-load oleh Postgres di docker-compose)

CREATE TABLE IF NOT EXISTS products (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,                    -- 'shopee' | 'seed_en'
    ext_id          TEXT NOT NULL,                    -- itemId (shopee) / seed key
    track           TEXT NOT NULL DEFAULT 'id',       -- 'id' | 'en'
    title           TEXT NOT NULL,
    image_url       TEXT,
    product_url     TEXT,
    offer_url       TEXT,                             -- link afiliasi asli
    price_min       NUMERIC(14,2),
    price_max       NUMERIC(14,2),
    discount_rate   INT,
    sales           INT,
    rating_star     NUMERIC(3,2),
    commission_rate NUMERIC(6,4),                     -- 0.25 = 25%
    commission_amt  NUMERIC(14,2),
    shop_name       TEXT,
    score           NUMERIC(6,2) NOT NULL DEFAULT 0,  -- skor kurasi (feedback loop)
    status          TEXT NOT NULL DEFAULT 'new',      -- new|used|exhausted
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, ext_id)
);

CREATE TABLE IF NOT EXISTS scripts (
    id           BIGSERIAL PRIMARY KEY,
    product_id   BIGINT REFERENCES products(id),
    track        TEXT NOT NULL DEFAULT 'id',
    language     TEXT NOT NULL DEFAULT 'id',
    voice        TEXT,
    title        TEXT,
    hook         TEXT,
    scenes_json  JSONB NOT NULL,                      -- [{text,image,style}]
    caption      TEXT,
    hashtags     TEXT,
    ai_score     NUMERIC(5,2),                        -- nilai gate AI 0-100
    ai_verdict   JSONB,                               -- {score,reasons,compliant}
    status       TEXT NOT NULL DEFAULT 'pending',     -- pending|rendered|approved|rejected|posted|failed|dropped
    media_file   TEXT,                                -- nama file .mp4 di /media
    media_bytes  BIGINT,                              -- ukuran file video (byte)
    render_seconds NUMERIC(8,2),                      -- waktu render nyata (detik)
    error        TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_scripts_status ON scripts(status);
CREATE INDEX IF NOT EXISTS idx_scripts_product ON scripts(product_id);

CREATE TABLE IF NOT EXISTS posts (
    id           BIGSERIAL PRIMARY KEY,
    script_id    BIGINT REFERENCES scripts(id),
    platform     TEXT NOT NULL,                       -- 'tiktok' | 'instagram'
    external_id  TEXT,                                -- publish_id / ig media id
    status       TEXT NOT NULL DEFAULT 'submitted',   -- submitted|published|failed
    error        TEXT,
    posted_at    TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Satu post per (script, platform) — cegah publish dobel.
ALTER TABLE posts ADD CONSTRAINT uq_posts_script_platform UNIQUE (script_id, platform);
CREATE INDEX IF NOT EXISTS idx_posts_script ON posts(script_id);

CREATE TABLE IF NOT EXISTS conversions (
    id           BIGSERIAL PRIMARY KEY,
    checkout_id  TEXT,
    commission   NUMERIC(14,2),
    ts           TIMESTAMPTZ,
    raw          JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- jendela tarik harian tumpang tindih 7 hari => cegah duplikat
CREATE UNIQUE INDEX IF NOT EXISTS uq_conversions_checkout_ts
    ON conversions(checkout_id, ts) WHERE checkout_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS tokens (
    platform      TEXT PRIMARY KEY,                   -- 'tiktok' | 'instagram'
    access_token  TEXT,
    refresh_token TEXT,
    expires_at    TIMESTAMPTZ,
    extra         JSONB,                              -- ig_user_id, open_id, dll
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- seed kosong; EN affiliate offers diisi manual via CSV/SQL (tidak ada API publik)
CREATE TABLE IF NOT EXISTS seed_en_offers (
    id           BIGSERIAL PRIMARY KEY,
    name         TEXT NOT NULL,
    program      TEXT NOT NULL,                       -- 'impact' | 'partnerstack' | 'direct'
    commission   TEXT,                                -- deskripsi: "30% recurring"
    url          TEXT NOT NULL,                       -- link afiliasi EN
    demo_image   TEXT,                                -- screenshot/gambar utk video
    active       BOOLEAN NOT NULL DEFAULT true
);

-- strategi AI (hasil analis mingguan; aktif hanya setelah approval Telegram)
CREATE TABLE IF NOT EXISTS strategy (
    id            BIGSERIAL PRIMARY KEY,
    version       INT NOT NULL DEFAULT 1,
    active        BOOLEAN NOT NULL DEFAULT false,
    analysis      JSONB,                              -- narasi analis
    changes       JSONB NOT NULL DEFAULT '{}'::jsonb, -- keywords_id, hook_style, posting_times, track_ratio, quota_per_day, product_filters
    hypotheses    JSONB,                              -- uji A/B berikutnya
    health_score  NUMERIC(5,2),                       -- kesehatan akun 0-100
    approved_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- seed baris default aktif (changes kosong = eksekutor pakai fallback hardcoded)
INSERT INTO strategy (active, analysis, changes)
SELECT true, '{}'::jsonb, '{}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM strategy);

-- performa konten (IG Insights; TikTok insights butuh approval terpisah)
CREATE TABLE IF NOT EXISTS post_metrics (
    id         BIGSERIAL PRIMARY KEY,
    post_id    BIGINT REFERENCES posts(id) ON DELETE CASCADE,
    source     TEXT NOT NULL DEFAULT 'ig',
    plays      BIGINT,
    likes      BIGINT,
    comments   BIGINT,
    saves      BIGINT,
    shares     BIGINT,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (post_id, source)
);
CREATE INDEX IF NOT EXISTS idx_post_metrics_post ON post_metrics(post_id);

-- ─── TREN PASAR (Google Trends / TikTok / Shopee / Tokopedia) ──────────────
CREATE TABLE IF NOT EXISTS trends (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,                    -- 'google'|'tiktok'|'shopee'|'tokopedia'
    keyword     TEXT NOT NULL,                    -- kata kunci yang sedang tren
    region      TEXT NOT NULL DEFAULT 'id',       -- kode wilayah / 'nationwide'
    volume      INT,                              -- volume indeks 0-100 / jumlah
    rank        INT,                              -- peringkat saat ini
    category    TEXT,                             -- kategori produk terkait
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_trends_keyword ON trends(keyword);
CREATE INDEX IF NOT EXISTS idx_trends_captured ON trends(captured_at);

-- boost skor produk yang match tren aktif (auto-update oleh trend_scout)
CREATE TABLE IF NOT EXISTS trend_boosts (
    product_id BIGINT REFERENCES products(id) ON DELETE CASCADE,
    trend_id   BIGINT REFERENCES trends(id) ON DELETE CASCADE,
    boost      NUMERIC(6,2) NOT NULL DEFAULT 0,
    matched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, trend_id)
);

-- RIWAYAT HARGA (snapshot per produk; terisi otomatis begitu akses harga tersedia)
CREATE TABLE IF NOT EXISTS price_history (
    id          BIGSERIAL PRIMARY KEY,
    product_id  BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price_min   NUMERIC(12,2),
    price_max   NUMERIC(12,2),
    source      TEXT NOT NULL DEFAULT 'shopee',
    captured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id, captured_at);
