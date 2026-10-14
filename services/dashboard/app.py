#!/usr/bin/env python3
"""invest-nyawit dashboard.

Rute:
  GET /stats      — halaman statistik (KPI, diagram, tabel; auto-refresh 30 dtk)
  GET /api/stats  — JSON data untuk halaman di atas
  GET /bio        — halaman link-in-bio (PUBLIK, tanpa auth)
  GET /health     — cek hidup

Auth:
  /stats, /api/stats, /api/trends — basic auth (STATS_USER + BASIC_AUTH_HASH)
  /api/trends-ingest, /api/trends-score — internal token (X-Internal-Token)
  /bio, /health — publik
"""

import base64
import html
import hmac
import json
import os
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import bcrypt
import psycopg
from psycopg.rows import dict_row

PORT = int(os.environ.get("PORT", "8091"))
SITE_HANDLE = os.environ.get("SITE_HANDLE", "@primefinds.id")
PUBLIC_MEDIA_URL = os.environ.get("PUBLIC_MEDIA_URL", "")

STATS_USER = os.environ.get("STATS_USER", "")
BASIC_AUTH_HASH = os.environ.get("BASIC_AUTH_HASH", "")
INTERNAL_API_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "")


def _conn():
    # psycopg.connect() tanpa argumen memakai env libpq standar
    # (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD) — diatur di docker-compose.
    return psycopg.connect(row_factory=dict_row)


def _check_basic_auth(handler) -> bool:
    """Verifikasi HTTP Basic Auth terhadap STATS_USER + BASIC_AUTH_HASH (bcrypt)."""
    if not STATS_USER or not BASIC_AUTH_HASH:
        return False  # belum dikonfigurasi → TOLAK (default-deny)
    hdr = handler.headers.get("Authorization", "")
    if not hdr.startswith("Basic "):
        return False
    try:
        user, pw = base64.b64decode(hdr[6:]).decode("utf-8").split(":", 1)
    except Exception:
        return False
    if not hmac.compare_digest(user, STATS_USER):
        return False
    return bcrypt.checkpw(pw.encode("utf-8"), BASIC_AUTH_HASH.encode("utf-8"))


def _check_internal_token(handler) -> bool:
    """Verifikasi X-Internal-Token header (dipakai trend_scout → dashboard)."""
    if not INTERNAL_API_TOKEN:
        return False  # belum dikonfigurasi → TOLAK (default-deny)
    hdr = handler.headers.get("X-Internal-Token", "")
    return hmac.compare_digest(hdr, INTERNAL_API_TOKEN)


def _num(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _iso(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def fetch_stats():
    out = {}
    with _conn() as conn, conn.cursor() as cur:
        # ---- KPI ----
        cur.execute(
            """
            SELECT
              COALESCE(SUM(commission) FILTER (WHERE ts >= date_trunc('day', now())), 0) AS income_today,
              COALESCE(SUM(commission) FILTER (WHERE ts >= now() - interval '7 days'), 0) AS income_7d,
              COALESCE(SUM(commission) FILTER (WHERE ts >= now() - interval '14 days' AND ts < now() - interval '7 days'), 0) AS income_prev_7d,
              COALESCE(SUM(commission) FILTER (WHERE ts >= now() - interval '30 days'), 0) AS income_30d,
              COUNT(*) FILTER (WHERE ts >= now() - interval '30 days') AS orders_30d,
              COUNT(*) FILTER (WHERE ts >= date_trunc('day', now())) AS orders_today
            FROM conversions
            """
        )
        kpi = dict(cur.fetchone())

        # Catatan: posted_at hanya ada di tabel posts — jangan disentuh di skrip.
        cur.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM posts WHERE posted_at >= date_trunc('day', now())) AS posts_today,
              (SELECT COUNT(*) FROM scripts WHERE status = 'rendered') AS queue_approval,
              COALESCE((SELECT AVG(ai_score) FROM scripts
                        WHERE ai_score IS NOT NULL AND updated_at >= now() - interval '7 days'), 0) AS avg_score,
              COALESCE((SELECT AVG(render_seconds) FROM scripts WHERE render_seconds IS NOT NULL), 0) AS avg_render_s,
              COALESCE((SELECT AVG(EXTRACT(EPOCH FROM (p.posted_at - s.created_at)) / 3600)
                        FROM posts p JOIN scripts s ON s.id = p.script_id
                        WHERE p.posted_at >= now() - interval '30 days'), 0) AS avg_lag_h,
              (SELECT MAX(updated_at) FROM scripts) AS last_activity
            """
        )
        kpi.update(cur.fetchone())

        # ---- Series: income harian 30 hari ----
        cur.execute(
            """
            SELECT date_trunc('day', ts)::date AS d,
                   COALESCE(SUM(commission), 0) AS v,
                   COUNT(*) AS orders
            FROM conversions
            WHERE ts >= now() - interval '30 days'
            GROUP BY 1 ORDER BY 1
            """
        )
        out["income_daily"] = [
            {"d": _iso(r["d"]), "v": _num(r["v"]), "orders": int(r["orders"])}
            for r in cur.fetchall()
        ]

        # ---- Series: post per hari per platform (7 hari) ----
        cur.execute(
            """
            SELECT date_trunc('day', posted_at)::date AS d, platform, COUNT(*) AS n
            FROM posts
            WHERE posted_at >= now() - interval '7 days'
            GROUP BY 1, 2 ORDER BY 1
            """
        )
        posts_daily = {}
        for r in cur.fetchall():
            d = _iso(r["d"])
            posts_daily.setdefault(d, {"d": d, "tiktok": 0, "instagram": 0})
            if r["platform"] in ("tiktok", "instagram"):
                posts_daily[d][r["platform"]] = int(r["n"])
        out["posts_daily"] = [posts_daily[k] for k in sorted(posts_daily)]

        # ---- Funnel status script ----
        cur.execute("SELECT status, COUNT(*) AS n FROM scripts GROUP BY status ORDER BY 2 DESC")
        out["funnel"] = [{"status": r["status"], "n": int(r["n"])} for r in cur.fetchall()]

        # ---- Rasio track (post 30 hari) ----
        cur.execute(
            """
            SELECT s.track, COUNT(*) AS n
            FROM posts p JOIN scripts s ON s.id = p.script_id
            WHERE p.posted_at >= now() - interval '30 days'
            GROUP BY s.track
            """
        )
        out["tracks"] = [{"track": r["track"], "n": int(r["n"])} for r in cur.fetchall()]

        # ---- Tabel: 10 post terakhir ----
        cur.execute(
            """
            SELECT s.title, p.platform, p.status, p.posted_at, s.ai_score
            FROM posts p JOIN scripts s ON s.id = p.script_id
            ORDER BY p.created_at DESC LIMIT 10
            """
        )
        out["recent_posts"] = [
            {
                "title": (r["title"] or "")[:70],
                "platform": r["platform"],
                "status": r["status"],
                "posted_at": _iso(r["posted_at"]),
                "ai_score": _num(r["ai_score"]),
            }
            for r in cur.fetchall()
        ]

        # ---- Tabel: konversi terakhir ----
        cur.execute(
            "SELECT checkout_id, commission, ts FROM conversions ORDER BY ts DESC LIMIT 10"
        )
        out["recent_conversions"] = [
            {
                "checkout_id": (r["checkout_id"] or "")[:24],
                "commission": _num(r["commission"]),
                "ts": _iso(r["ts"]),
            }
            for r in cur.fetchall()
        ]

        # ---- Tabel: top produk ----
        cur.execute(
            """
            SELECT title, track, score, offer_url, price_min, commission_rate, commission_amt
            FROM products
            WHERE status <> 'exhausted' AND COALESCE(offer_url, '') <> ''
            ORDER BY score DESC LIMIT 10
            """
        )
        out["top_products"] = [
            {
                "title": (r["title"] or "")[:70],
                "track": r["track"],
                "score": _num(r["score"]),
                "offer_url": r["offer_url"],
                "price_min": _num(r["price_min"]),
                "commission_rate": _num(r["commission_rate"]),
                "commission_amt": _num(r["commission_amt"]),
            }
            for r in cur.fetchall()
        ]

        # ---- Tabel: error terakhir ----
        cur.execute(
            """
            SELECT id, title, error, updated_at FROM scripts
            WHERE error IS NOT NULL AND error <> ''
            ORDER BY updated_at DESC LIMIT 10
            """
        )
        out["errors"] = [
            {
                "id": int(r["id"]),
                "title": (r["title"] or "")[:40],
                "error": (r["error"] or "")[:160],
                "updated_at": _iso(r["updated_at"]),
            }
            for r in cur.fetchall()
        ]

        # ---- Strategi aktif ----
        cur.execute(
            """
            SELECT version, health_score, approved_at FROM strategy
            WHERE active = true ORDER BY id DESC LIMIT 1
            """
        )
        row = cur.fetchone()
        out["strategy"] = {
            "version": int(row["version"]) if row else None,
            "health": _num(row["health_score"]) if row and row["health_score"] is not None else None,
            "approved_at": _iso(row["approved_at"]) if row else None,
        }

        # ---- Riwayat strategi (8 versi terakhir) ----
        cur.execute(
            """
            SELECT version, health_score, active, approved_at, created_at
            FROM strategy ORDER BY version DESC LIMIT 8
            """
        )
        out["strategy_history"] = [
            {
                "version": int(r["version"]),
                "health": _num(r["health_score"]) if r["health_score"] is not None else None,
                "active": bool(r["active"]),
                "approved_at": _iso(r["approved_at"]),
                "created_at": _iso(r["created_at"]),
            }
            for r in cur.fetchall()
        ]

    out["kpi"] = {k: (_num(v) if k != "last_activity" else _iso(v)) for k, v in kpi.items()}
    for k in ("posts_today", "queue_approval", "orders_30d", "orders_today"):
        out["kpi"][k] = int(_num(out["kpi"].get(k)))
    out["generated_at"] = datetime.now().isoformat(timespec="seconds")
    return out


def fetch_trends():
    """Ambil tren terbaru per sumber untuk dashboard."""
    with _conn() as conn, conn.cursor() as cur:
        # Top trends per sumber (12 jam terakhir)
        cur.execute(
            """
            SELECT source, keyword, region, volume, rank, captured_at
            FROM trends
            WHERE captured_at >= now() - interval '12 hours'
            ORDER BY source, rank ASC
            """
        )
        by_source = {}
        for r in cur.fetchall():
            s = r["source"]
            by_source.setdefault(s, [])
            if len(by_source[s]) < 15:
                by_source[s].append({
                    "keyword": r["keyword"],
                    "region": r["region"],
                    "volume": int(r["volume"]) if r["volume"] else None,
                    "rank": int(r["rank"]),
                    "captured_at": _iso(r["captured_at"]),
                })

        # Produk yang kena boost tren
        cur.execute(
            """
            SELECT p.title, p.score, tb.boost, t.keyword, t.source
            FROM trend_boosts tb
            JOIN products p ON p.id = tb.product_id
            JOIN trends t ON t.id = tb.trend_id
            WHERE tb.matched_at >= now() - interval '12 hours'
            ORDER BY tb.boost DESC, p.score DESC
            LIMIT 15
            """
        )
        boosted = [
            {
                "title": (r["title"] or "")[:60],
                "score": _num(r["score"]),
                "boost": _num(r["boost"]),
                "keyword": r["keyword"],
                "source": r["source"],
            }
            for r in cur.fetchall()
        ]

        # Ringkasan: total tren aktif per sumber
        cur.execute(
            """
            SELECT source, COUNT(*) AS n, MAX(captured_at) AS last
            FROM trends
            WHERE captured_at >= now() - interval '12 hours'
            GROUP BY source ORDER BY n DESC
            """
        )
        summary = [
            {"source": r["source"], "count": int(r["n"]), "last": _iso(r["last"])}
            for r in cur.fetchall()
        ]

    return {"by_source": by_source, "boosted_products": boosted, "summary": summary}


def fetch_price_history():
    """Riwayat snapshot harga per produk + % perubahan.

    Angka hanya muncul bila akses harga tersedia — saat ini Shopee memblokir
    endpoint harga tanpa login (error 90309999), jadi tabel bisa kosong.
    Panel dashboard menampilkan status jujur, bukan angka karangan.
    """
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT ph.product_id, p.title, p.offer_url,
                   count(*) AS snaps,
                   (array_agg(ph.price_min ORDER BY ph.captured_at))[1] AS first_price,
                   (array_agg(ph.price_min ORDER BY ph.captured_at DESC))[1] AS last_price,
                   min(ph.captured_at) AS first_at,
                   max(ph.captured_at) AS last_at
            FROM price_history ph
            JOIN products p ON p.id = ph.product_id
            GROUP BY ph.product_id, p.title, p.offer_url
            ORDER BY max(ph.captured_at) DESC
            LIMIT 20
            """
        )
        items = []
        for row in cur:
            d = dict(row)
            first = _num(d["first_price"], 0.0)
            last = _num(d["last_price"], 0.0)
            pct = ((last - first) / first * 100.0) if first > 0 and d["snaps"] >= 2 else None
            f_at, l_at = d["first_at"], d["last_at"]
            days = 0.0
            if isinstance(f_at, datetime) and isinstance(l_at, datetime):
                days = max((l_at - f_at).total_seconds() / 86400.0, 0.0)
            per_day = (pct / days) if pct is not None and days >= 1.0 else None
            items.append({
                "product_id": d["product_id"],
                "title": d["title"],
                "offer_url": d["offer_url"],
                "snaps": d["snaps"],
                "first_price": float(first) if first > 0 else None,
                "last_price": float(last) if last > 0 else None,
                "first_at": _iso(f_at),
                "last_at": _iso(l_at),
                "pct": round(pct, 2) if pct is not None else None,
                "per_day": round(per_day, 2) if per_day is not None else None,
            })
    return {"items": items}


def ingest_trends(trends: list[dict]) -> dict:
    """Insert batch tren ke DB. Dipanggil oleh trend_scout via POST."""
    if not trends:
        return {"ok": True, "inserted": 0}
    with _conn() as conn, conn.cursor() as cur:
        inserted = 0
        for t in trends:
            cur.execute(
                """
                INSERT INTO trends (source, keyword, region, volume, rank, category)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    t.get("source", "unknown"),
                    t.get("keyword", "")[:200],
                    t.get("region", "id"),
                    t.get("volume"),
                    t.get("rank"),
                    t.get("category"),
                ),
            )
            inserted += 1
        # Bersihkan tren lama (> 7 hari)
        cur.execute("DELETE FROM trends WHERE captured_at < now() - interval '7 days'")
    return {"ok": True, "inserted": inserted}


def score_products_from_trends() -> dict:
    """Skor komposit multi-faktor + boost tren (12 jam terakhir).

    base_score (0-80): sales (log) + rating + komisi + diskon + kelengkapan.
    trend_boost (0-20): keyword tren muncul di judul produk (arah diperbaiki:
    judul produk MENGANDUNG keyword, bukan keyword mengandung judul).
    score akhir = LEAST(100, base_score + trend_boost) — baseline stabil,
    boost tidak menumpuk antar run.
    """
    with _conn() as conn, conn.cursor() as cur:
        # pastikan kolom base_score ada (migrasi ringan tanpa alembic)
        cur.execute("""
            ALTER TABLE products ADD COLUMN IF NOT EXISTS base_score numeric(6,2) DEFAULT 0;
        """)

        # 1. hitung base_score komposit untuk semua produk aktif
        cur.execute(
            """
            UPDATE products
            SET base_score = LEAST(80,
                  COALESCE(LEAST(30, ln(GREATEST(COALESCE(sales,0),0)+1) * 8), 0)
                + COALESCE(LEAST(20, (COALESCE(rating_star,0) / 5.0) * 20), 0)
                + COALESCE(LEAST(15,
                    CASE
                      WHEN commission_rate IS NOT NULL THEN commission_rate * 100 * 1.5
                      WHEN commission_amt   IS NOT NULL THEN commission_amt / 100.0
                      ELSE 0
                    END), 0)
                + COALESCE(LEAST(10, COALESCE(discount_rate,0) / 10.0), 0)
                + CASE WHEN COALESCE(image_url,'')<>'' AND COALESCE(offer_url,'')<>'' THEN 5 ELSE 0 END
            ),
            updated_at = now()
            WHERE status <> 'exhausted'
            """
        )

        # 2. hapus boost lama
        cur.execute("DELETE FROM trend_boosts")

        # 3. boost tren: judul produk mengandung keyword (arah benar)
        cur.execute(
            """
            INSERT INTO trend_boosts (product_id, trend_id, boost)
            SELECT p.id, t.id,
                   LEAST(20, 5 * (SELECT COUNT(*) FROM trends t2
                                  WHERE p.title ILIKE '%' || t2.keyword || '%'
                                    AND t2.captured_at >= now() - interval '12 hours'
                                    AND LENGTH(t2.keyword) >= 3))
            FROM products p
            JOIN trends t ON p.title ILIKE '%' || t.keyword || '%'
            WHERE t.captured_at >= now() - interval '12 hours'
              AND p.status <> 'exhausted'
              AND LENGTH(t.keyword) >= 3
            ON CONFLICT (product_id, trend_id) DO NOTHING
            """
        )
        boosted = cur.rowcount

        # 4. score akhir = base_score + total_boost (baseline stabil, tidak numpuk)
        cur.execute(
            """
            UPDATE products p
            SET score = LEAST(100, COALESCE(p.base_score, 75) + COALESCE((
                    SELECT SUM(tb.boost) FROM trend_boosts tb WHERE tb.product_id = p.id
                ), 0)),
                updated_at = now()
            WHERE p.status <> 'exhausted'
            """
        )
        updated = cur.rowcount

    return {"ok": True, "boosted": boosted, "updated": updated}


def fetch_bio_products():
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT title, image_url, offer_url, price_min, track, score,
                   commission_rate, commission_amt, shop_name
            FROM products
            WHERE status IN ('new', 'used') AND COALESCE(offer_url, '') <> ''
            ORDER BY score DESC, updated_at DESC LIMIT 12
            """
        )
        return [
            {
                "title": r["title"],
                "image_url": r["image_url"] or "",
                "offer_url": r["offer_url"],
                "price_min": _num(r["price_min"]),
                "track": r["track"],
                "score": _num(r["score"]),
                "commission_rate": _num(r["commission_rate"]),
                "commission_amt": _num(r["commission_amt"]),
                "shop_name": r["shop_name"] or "",
            }
            for r in cur.fetchall()
        ]


# --------------------------------------------------------------------- HTML

STATS_HTML = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>invest-nyawit — Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root { --bg:#0b0f17; --card:#131a26; --line:#1f2a3d; --txt:#e6edf7; --mut:#8aa0bf;
          --up:#22c55e; --down:#ef4444; --acc:#38bdf8; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt);
         font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width:1200px; margin:0 auto; padding:20px; }
  h1 { font-size:20px; margin:4px 0 2px; }
  .sub { color:var(--mut); font-size:13px; margin-bottom:16px; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fill,minmax(170px,1fr)); gap:10px; }
  .kpi { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }
  .kpi .l { color:var(--mut); font-size:12px; }
  .kpi .v { font-size:22px; font-weight:700; margin-top:2px; }
  .kpi .v.green { color:var(--up); } .kpi .v.blue { color:var(--acc); } .kpi .v.red { color:var(--down); }
  .grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:14px; }
  @media (max-width:900px){ .grid { grid-template-columns:1fr; } }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }
  .card h2 { font-size:14px; margin:0 0 10px; color:var(--mut); font-weight:600; text-transform:uppercase; letter-spacing:.04em; }
  .wide { grid-column:1 / -1; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th,td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); }
  th { color:var(--mut); font-weight:600; }
  td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
  a { color:var(--acc); text-decoration:none; }
  .badge { display:inline-block; padding:1px 8px; border-radius:999px; font-size:11px; border:1px solid var(--line); }
  .badge.ok { color:var(--up); border-color:var(--up); } .badge.err { color:var(--down); border-color:var(--down); }
  .empty { color:var(--mut); font-style:italic; padding:8px 0; }
  footer { color:var(--mut); font-size:12px; margin-top:16px; }
  canvas { max-height:260px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>📈 invest-nyawit — Dashboard</h1>
  <div class="sub">Auto-refresh tiap 30 detik · data: Shopee Affiliate conversionReport + pipeline n8n ·
    <span id="gen">memuat…</span></div>

  <div class="kpis" id="kpis"></div>

  <div class="grid">
    <div class="card wide"><h2>Komisi harian (30 hari)</h2><canvas id="cIncome"></canvas></div>
    <div class="card"><h2>Post per hari per platform (7 hari)</h2><canvas id="cPosts"></canvas></div>
    <div class="card"><h2>Funnel konten</h2><canvas id="cFunnel"></canvas></div>
    <div class="card"><h2>Track ID vs EN (post 30 hari)</h2><canvas id="cTracks"></canvas></div>
    <div class="card"><h2>Strategi aktif</h2><div id="strat"></div></div>

    <div class="card wide"><h2>🔥 Tren Pasar (update tiap 3 jam)</h2><div id="tTrends"></div></div>
    <div class="card wide"><h2>🚀 Produk Boost Tren</h2><div id="tBoost"></div></div>
    <div class="card wide"><h2>📉 Riwayat Harga</h2><div id="tPrice"></div></div>
    <div class="card wide"><h2>10 post terakhir</h2><div id="tPosts"></div></div>
    <div class="card"><h2>Konversi terakhir</h2><div id="tConv"></div></div>
    <div class="card"><h2>Top produk (skor kurasi)</h2><div id="tProd"></div></div>
    <div class="card wide"><h2>Log error</h2><div id="tErr"></div></div>
  </div>

  <footer>invest-nyawit · link-in-bio publik: <a href="/bio">/bio</a> · semua hak dilindungi</footer>
</div>

<script>
const rp = n => 'Rp' + Math.round(n).toLocaleString('id-ID');
const fmt = s => { if(!s) return '-'; try { return new Date(s).toLocaleString('id-ID',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'}); } catch(e){ return s; } };
const esc = s => String(s??'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let charts = {};

const KPI_DEFS = [
  ['income_today','Income hari ini','green',rp],
  ['income_7d','Income 7 hari','green',rp],
  ['income_30d','Income 30 hari','green',rp],
  ['orders_30d','Order 30 hari','',n=>n],
  ['posts_today','Post hari ini','blue',n=>n],
  ['queue_approval','Menunggu approval','blue',n=>n],
  ['avg_score','Skor AI rata2 (7h)','',n=>n.toFixed(1)],
  ['avg_render_s','Render rata2 (dtk)','',n=>n.toFixed(1)],
  ['avg_lag_h','Publish → tayang (jam)','',n=>n.toFixed(1)],
];

function renderKpis(k){
  const prev = Number(k.income_prev_7d || 0);
  const now7 = Number(k.income_7d || 0);
  const delta = prev > 0 ? Math.round(100 * (now7 - prev) / prev) : null;
  const deltaHtml = delta === null ? '-'
    : `<div class="l">vs minggu lalu</div><div class="v ${delta >= 0 ? 'green' : 'red'}" style="font-size:15px">${delta >= 0 ? '+' : ''}${delta}%</div>`;
  document.getElementById('kpis').innerHTML =
    KPI_DEFS.map(([key,label,cls,fmtf]) =>
      `<div class="kpi"><div class="l">${label}</div><div class="v ${cls}">${fmtf(Number(k[key]||0))}</div></div>`
    ).join('') +
    `<div class="kpi">${deltaHtml}</div>`;
}

function mkChart(id, cfg){
  const el = document.getElementById(id);
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(el, cfg);
}

function renderCharts(d){
  Chart.defaults.color = '#8aa0bf';
  Chart.defaults.borderColor = '#1f2a3d';

  mkChart('cIncome', { type:'line',
    data:{ labels:d.income_daily.map(x=>x.d.slice(5)),
      datasets:[
        { label:'Komisi (Rp)', data:d.income_daily.map(x=>x.v), borderColor:'#22c55e',
          backgroundColor:'rgba(34,197,94,.15)', fill:true, tension:.3, yAxisID:'y' },
        { label:'Order', data:d.income_daily.map(x=>x.orders), borderColor:'#38bdf8',
          tension:.3, yAxisID:'y1' } ] },
    options:{ maintainAspectRatio:false,
      scales:{ y:{ position:'left', ticks:{ callback:v=>rp(v) } },
               y1:{ position:'right', grid:{drawOnChartArea:false}, ticks:{ precision:0 } } } } });

  mkChart('cPosts', { type:'bar',
    data:{ labels:d.posts_daily.map(x=>x.d.slice(5)),
      datasets:[
        { label:'TikTok', data:d.posts_daily.map(x=>x.tiktok), backgroundColor:'#38bdf8' },
        { label:'Instagram', data:d.posts_daily.map(x=>x.instagram), backgroundColor:'#a78bfa' } ] },
    options:{ maintainAspectRatio:false, scales:{ x:{stacked:true}, y:{stacked:true, ticks:{precision:0}} } } });

  const FUNNEL_LABEL = { pending:'Proses AI', rendered:'Menunggu approval', approved:'Disetujui',
    rejected:'Ditolak', posted:'Tayang', failed:'Gagal render', dropped:'Dibuang AI' };
  mkChart('cFunnel', { type:'bar',
    data:{ labels:d.funnel.map(x=>FUNNEL_LABEL[x.status]||x.status),
      datasets:[{ data:d.funnel.map(x=>x.n), backgroundColor:'#38bdf8' }] },
    options:{ indexAxis:'y', maintainAspectRatio:false, plugins:{legend:{display:false}},
      scales:{ x:{ ticks:{precision:0} } } } });

  mkChart('cTracks', { type:'doughnut',
    data:{ labels:d.tracks.map(x=>x.track.toUpperCase()),
      datasets:[{ data:d.tracks.map(x=>x.n), backgroundColor:['#22c55e','#a78bfa'] }] },
    options:{ maintainAspectRatio:false, plugins:{ legend:{ position:'bottom' } } } });
}

function table(rows, cols){
  if (!rows.length) return '<div class="empty">Belum ada data.</div>';
  return '<table><thead><tr>' + cols.map(c=>`<th class="${c.num?'num':''}">${c.h}</th>`).join('') +
    '</tr></thead><tbody>' + rows.map(r=>'<tr>' +
      cols.map(c=>`<td class="${c.num?'num':''}">${c.f(r)}</td>`).join('') + '</tr>').join('') +
    '</tbody></table>';
}

function renderTables(d){
  // Tren pasar
  const tr = d.trends || { by_source: {}, boosted_products: [], summary: [] };
  const SRC_LABEL = { google:'🔍 Google', tiktok:'🎵 TikTok', shopee:'🛍 Shopee', tokopedia:'🛒 Tokopedia' };
  let trendHtml = '';
  if (tr.summary && tr.summary.length) {
    trendHtml += '<div style="margin-bottom:10px">' + tr.summary.map(s =>
      `<span class="badge" style="margin-right:6px">${SRC_LABEL[s.source]||s.source}: ${s.count} keywords</span>`
    ).join('') + '</div>';
  }
  const sources = Object.keys(tr.by_source || {});
  if (sources.length) {
    trendHtml += '<table><thead><tr><th>Sumber</th><th>#</th><th>Keyword</th><th>Volume</th><th>Wilayah</th></tr></thead><tbody>';
    for (const src of sources) {
      const items = tr.by_source[src] || [];
      for (let i = 0; i < Math.min(items.length, 8); i++) {
        const t = items[i];
        const vol = t.volume ? t.volume.toLocaleString('id-ID') : '-';
        trendHtml += `<tr><td>${SRC_LABEL[src]||src}</td><td class="num">${t.rank}</td><td>${esc(t.keyword)}</td><td class="num">${vol}</td><td>${esc(t.region)}</td></tr>`;
      }
    }
    trendHtml += '</tbody></table>';
  } else {
    trendHtml = '<div class="empty">Belum ada tren — tunggu update berikutnya (tiap 3 jam).</div>';
  }
  document.getElementById('tTrends').innerHTML = trendHtml;

  // Produk boost tren
  let boostHtml = '';
  if (tr.boosted_products && tr.boosted_products.length) {
    boostHtml = '<table><thead><tr><th>Produk</th><th>Match Tren</th><th>Sumber</th><th>Boost</th><th>Skor</th></tr></thead><tbody>' +
      tr.boosted_products.map(b =>
        `<tr><td>${esc(b.title)}</td><td>${esc(b.keyword)}</td><td>${SRC_LABEL[b.source]||b.source}</td><td class="num" style="color:#22c55e">+${b.boost.toFixed(0)}</td><td class="num">${b.score.toFixed(1)}</td></tr>`
      ).join('') + '</tbody></table>';
  } else {
    boostHtml = '<div class="empty">Belum ada produk yang match tren aktif.</div>';
  }
  document.getElementById('tBoost').innerHTML = boostHtml;

  // Riwayat harga (honest: tanpa akses harga = tampil status, bukan angka karangan)
  const ph = d.price_history || { items: [] };
  let phHtml = '';
  if (ph.items && ph.items.length) {
    phHtml = '<table><thead><tr><th>Produk</th><th class="num">Snapshot</th><th class="num">Harga awal</th><th class="num">Harga terbaru</th><th class="num">% total</th><th class="num">%/hari</th><th>Terakhir</th></tr></thead><tbody>' +
      ph.items.map(r => {
        const pctTxt = r.pct == null ? '-'
          : `<span style="color:${r.pct >= 0 ? 'var(--up)' : 'var(--down)'}">${r.pct >= 0 ? '+' : ''}${r.pct.toFixed(1)}%</span>`;
        const dayTxt = r.per_day == null ? '-' : r.per_day.toFixed(1) + '%';
        const rp2 = v => v ? ('Rp' + Math.round(v).toLocaleString('id-ID')) : '-';
        return `<tr><td><a href="${esc(r.offer_url || '#')}" target="_blank" rel="noopener">${esc(r.title)}</a></td>` +
          `<td class="num">${r.snaps}</td><td class="num">${rp2(r.first_price)}</td><td class="num">${rp2(r.last_price)}</td>` +
          `<td class="num">${pctTxt}</td><td class="num">${dayTxt}</td><td>${fmt(r.last_at)}</td></tr>`;
      }).join('') + '</tbody></table>' +
      (ph.items.every(r => r.pct == null)
        ? '<div class="empty" style="margin-top:8px">Belum cukup snapshot (&ge;2) untuk hitung % perubahan.</div>' : '');
  } else {
    phHtml = '<div class="empty">Belum ada data harga — Shopee memblokir harga tanpa login (error 90309999) dan API afiliasi belum aktif. Panel terisi otomatis begitu akses harga tersedia.</div>';
  }
  document.getElementById('tPrice').innerHTML = phHtml;

  document.getElementById('tPosts').innerHTML = table(d.recent_posts, [
    { h:'Judul', f:r=>esc(r.title) },
    { h:'Platform', f:r=>`<span class="badge">${esc(r.platform)}</span>` },
    { h:'Status', f:r=>`<span class="badge ${r.status==='posted'?'ok':(r.status==='failed'||r.status==='rejected'?'err':'')}">${esc(r.status)}</span>` },
    { h:'Waktu', f:r=>fmt(r.posted_at) },
    { h:'Skor', num:true, f:r=>r.ai_score?r.ai_score.toFixed(1):'-' } ]);

  document.getElementById('tConv').innerHTML = table(d.recent_conversions, [
    { h:'Checkout', f:r=>esc(r.checkout_id) },
    { h:'Komisi', num:true, f:r=>rp(r.commission) },
    { h:'Waktu', f:r=>fmt(r.ts) } ]);

  document.getElementById('tProd').innerHTML = table(d.top_products, [
    { h:'Produk', f:r=>`<a href="${esc(r.offer_url)}" target="_blank" rel="noopener">${esc(r.title)}</a>` },
    { h:'Track', f:r=>`<span class="badge">${r.track.toUpperCase()}</span>` },
    { h:'Harga', num:true, f:r=>r.price_min?('Rp'+Math.round(r.price_min).toLocaleString('id-ID')):'-' },
    { h:'Komisi', num:true, f:r=>rp(r.commission_amt) },
    { h:'Skor', num:true, f:r=>r.score.toFixed(1) } ]);

  document.getElementById('tErr').innerHTML = table(d.errors, [
    { h:'ID', num:true, f:r=>r.id },
    { h:'Judul', f:r=>esc(r.title) },
    { h:'Error', f:r=>`<span style="color:#ef4444">${esc(r.error)}</span>` },
    { h:'Waktu', f:r=>fmt(r.updated_at) } ]);

  const s = d.strategy || {};
  document.getElementById('strat').innerHTML =
    `<table><tbody>
      <tr><th>Versi</th><td>${s.version??'-'}</td></tr>
      <tr><th>Health score</th><td>${s.health!=null?s.health.toFixed(0):'-'}</td></tr>
      <tr><th>Disetujui</th><td>${fmt(s.approved_at)}</td></tr>
    </tbody></table>
    <h2 style="margin-top:12px">Riwayat strategi</h2>` +
    table(d.strategy_history || [], [
      { h:'v', num:true, f:r=>'v'+r.version },
      { h:'Health', num:true, f:r:r.health!=null?r.health.toFixed(0):'-' },
      { h:'Status', f:r=>`<span class="badge ${r.active?'ok':''}">${r.active?'aktif':'arsip'}</span>` },
      { h:'Disetujui', f:r=>fmt(r.approved_at) } ]);
}

async function load(){
  try {
    const res = await fetch('/api/stats', { cache:'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const d = await res.json();
    renderKpis(d.kpi);
    renderCharts(d);
    renderTables(d);
    document.getElementById('gen').textContent = 'diperbarui ' + fmt(d.generated_at);
  } catch (e) {
    document.getElementById('gen').textContent = 'GAGAL memuat: ' + e.message;
  }
}
load();
setInterval(load, 30000);
</script>
</body>
</html>
"""

BIO_HTML = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rekomendasi Pilihan — __HANDLE__</title>
<style>
  :root { --bg:#0b0f17; --card:#131a26; --line:#1f2a3d; --txt:#e6edf7; --mut:#8aa0bf; --acc:#38bdf8; --up:#22c55e; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt); font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
  .wrap { max-width:760px; margin:0 auto; padding:24px 16px 48px; }
  .hd { text-align:center; margin-bottom:22px; }
  .hd h1 { font-size:22px; margin:8px 0 4px; }
  .hd p { color:var(--mut); font-size:13px; margin:0; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:12px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; overflow:hidden;
          display:flex; flex-direction:column; transition:transform .15s; }
  .card:hover { transform:translateY(-3px); }
  .thumb { width:100%; aspect-ratio:1; object-fit:cover; background:#0e1522; display:block; }
  .thumbph { width:100%; aspect-ratio:1; background:linear-gradient(135deg,#1e293b,#0f172a);
             display:flex; align-items:center; justify-content:center; color:var(--mut); font-size:32px; }
  .body { padding:10px 12px 14px; display:flex; flex-direction:column; gap:6px; flex:1; }
  .t { font-size:13.5px; font-weight:600; line-height:1.35; }
  .price { color:var(--acc); font-weight:700; font-size:15px; }
  .meta { color:var(--mut); font-size:11.5px; }
  .btn { margin-top:auto; display:block; text-align:center; background:var(--up); color:#04150a;
         font-weight:700; padding:9px; border-radius:10px; text-decoration:none; font-size:14px; }
  .btn.en { background:var(--acc); color:#04121c; }
  footer { text-align:center; color:var(--mut); font-size:12px; margin-top:26px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="hd">
    <div style="font-size:34px">🛒</div>
    <h1>Rekomendasi Pilihan __HANDLE__</h1>
    <p>Produk terkurasi — komisi belanja lewat link ini (harga tetap sama buat kamu).</p>
  </div>
  <div class="grid">__CARDS__</div>
  <footer>Diperbarui otomatis · invest-nyawit</footer>
</div>
</body>
</html>
"""

BIO_CARD = """
<a class="card" href="{url}" target="_blank" rel="noopener nofollow">
  {img}
  <div class="body">
    <div class="t">{title}</div>
    <div class="price">{price}</div>
    <div class="meta">{meta}</div>
    <span class="btn{en}">Lihat & beli →</span>
  </div>
</a>"""


def stats_page():
    return STATS_HTML.encode("utf-8")


def bio_page():
    cards = []
    for p in fetch_bio_products():
        title = html.escape(p["title"])
        if p["image_url"]:
            img = f'<img class="thumb" src="{html.escape(p["image_url"], quote=True)}" alt="" loading="lazy">'
        else:
            img = '<div class="thumbph">📦</div>'
        price = "Rp" + format(int(round(p["price_min"])), ",d").replace(",", ".") if p["price_min"] else "Lihat harga"
        if p["commission_rate"]:
            meta = f"Komisi s.d. {p['commission_rate']*100:.1f}%"
        elif p["commission_amt"]:
            meta = "Komisi s.d. Rp" + format(int(round(p["commission_amt"])), ",d").replace(",", ".")
        else:
            meta = html.escape(p["shop_name"] or p["track"].upper())
        if p["track"] == "en":
            meta = "🌍 " + meta + " · English"
        cards.append(BIO_CARD.format(
            url=html.escape(p["offer_url"], quote=True), img=img, title=title,
            price=price, meta=meta, en=" en" if p["track"] == "en" else ""))
    body = BIO_HTML.replace("__HANDLE__", html.escape(SITE_HANDLE)).replace("__CARDS__", "".join(cards))
    return body.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[dash] %s - %s" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        try:
            if path == "/health":
                return self._send(200, b'{"ok":true,"service":"invest-nyawit-dashboard"}',
                                  "application/json")
            if path == "/bio":
                return self._send(200, bio_page(), "text/html; charset=utf-8")
            # ── rute yang butuh basic auth ──
            if path in ("/stats", "/index.html", "/", "/api/stats", "/api/trends"):
                if not _check_basic_auth(self):
                    body401 = b'{"ok":false}'
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="invest-nyawit"')
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body401)))
                    self.end_headers()
                    self.wfile.write(body401)
                    return
            if path in ("/stats", "/index.html", "/"):
                return self._send(200, stats_page(), "text/html; charset=utf-8")
            if path == "/api/stats":
                data = fetch_stats()
                try:
                    data["trends"] = fetch_trends()
                except Exception:
                    data["trends"] = {"by_source": {}, "boosted_products": [], "summary": []}
                try:
                    data["price_history"] = fetch_price_history()
                except Exception:
                    data["price_history"] = {"items": []}
                return self._send(200, json.dumps(data).encode("utf-8"), "application/json; charset=utf-8")
            if path == "/api/trends":
                data = json.dumps(fetch_trends()).encode("utf-8")
                return self._send(200, data, "application/json; charset=utf-8")
            self._send(404, b'{"ok":false,"error":"not found"}', "application/json")
        except Exception as e:  # noqa: BLE001 — laporkan apa adanya
            traceback_print()
            msg = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
            self._send(500, msg, "application/json")

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        try:
            # ── rute internal (trend_scout) butuh token ──
            if path in ("/api/trends-ingest", "/api/trends-score"):
                if not _check_internal_token(self):
                    body403 = b'{"ok":false}'
                    self.send_response(403)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body403)))
                    self.end_headers()
                    self.wfile.write(body403)
                    return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else b"{}"
            payload = json.loads(body) if body else {}

            if path == "/api/trends-ingest":
                trends = payload.get("trends", [])
                result = ingest_trends(trends)
                return self._send(200, json.dumps(result).encode("utf-8"), "application/json")

            if path == "/api/trends-score":
                result = score_products_from_trends()
                return self._send(200, json.dumps(result).encode("utf-8"), "application/json")

            self._send(404, b'{"ok":false,"error":"not found"}', "application/json")
        except Exception as e:
            traceback_print()
            msg = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
            self._send(500, msg, "application/json")


def traceback_print():
    import traceback
    traceback.print_exc()


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("[dashboard] listening on :%d  (/stats, /api/stats, /bio)" % PORT)
    srv.serve_forever()


if __name__ == "__main__":
    main()
