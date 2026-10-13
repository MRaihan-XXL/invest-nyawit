#!/usr/bin/env python3
"""invest-nyawit trend scout — analisis tren pasar multi-sumber.

Mengambil data tren dari:
  1. Google Trends  — pencarian trending di Indonesia (per kota & nasional)
  2. TikTok Creative Center — hashtag & produk trending
  3. Shopee trending page  — produk populer (scrape publik)
  4. Tokopedia trending    — produk populer (scrape publik)

Hasil disimpan ke tabel `trends`, lalu produk yang match tren
otomatis dapat boost skor via tabel `trend_boosts`.

Modes:
  python trend_scout.py --once            # sekali, lalu exit
  python trend_scout.py --serve --port 8092  # HTTP service (n8n panggil via POST /run)
"""

import argparse
import gzip
import json
import os
import re
import sys
import time
import traceback
import urllib.request
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from typing import Any

# ─── CONFIG ─────────────────────────────────────────────────────────────────
PG_DSN = os.environ.get("DATABASE_URL", "")
HTTP_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ─── HTTP helpers ───────────────────────────────────────────────────────────

def http_get(url: str, headers: dict | None = None, timeout: int = HTTP_TIMEOUT) -> bytes:
    h = {"User-Agent": USER_AGENT, "Accept-Language": "id-ID,id;q=0.9"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data


def http_get_json(url: str, headers: dict | None = None) -> Any:
    data = http_get(url, headers)
    return json.loads(data)


# ─── DB helpers (psycopg via subprocess ke psql, atau direct) ───────────────
# Kita pakai psycopg2 kalau tersedia; fallback ke HTTP ke dashboard API.
# Untuk kemudahan, kita insert via HTTP ke dashboard /api/trends-ingest
# supaya tidak perlu dependensi psycopg di container ini.

DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://dashboard:8091")
INTERNAL_API_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "")

def insert_trends_batch(trends: list[dict]) -> dict:
    """Kirim batch tren ke dashboard untuk insert ke DB."""
    try:
        payload = json.dumps({"trends": trends}).encode()
        headers = {"Content-Type": "application/json"}
        if INTERNAL_API_TOKEN:
            headers["X-Internal-Token"] = INTERNAL_API_TOKEN
        req = urllib.request.Request(
            f"{DASHBOARD_URL}/api/trends-ingest",
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[WARN] insert_trends_batch gagal: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}


def update_product_scores() -> dict:
    """Minta dashboard update skor produk berdasarkan tren aktif."""
    try:
        headers = {"Content-Type": "application/json"}
        if INTERNAL_API_TOKEN:
            headers["X-Internal-Token"] = INTERNAL_API_TOKEN
        req = urllib.request.Request(
            f"{DASHBOARD_URL}/api/trends-score",
            data=b"{}",
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[WARN] update_product_scores gagal: {e}", file=sys.stderr)
        return {"ok": False, "error": str(e)}


# ─── SOURCE 1: Google Trends ────────────────────────────────────────────────

def fetch_google_trends() -> list[dict]:
    """Ambil pencarian trending di Indonesia dari Google Trends RSS."""
    results = []
    try:
        # Google Trends trending searches RSS (Indonesia)
        url = "https://trends.google.com/trending/rss?geo=ID"
        xml = http_get(url).decode("utf-8", errors="replace")
        # Parse RSS items: <item><title>..</title><ht:approx_traffic>..</ht:approx_traffic>
        items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
        for i, item in enumerate(items[:30]):
            title_m = re.search(r"<title>(.*?)</title>", item)
            traffic_m = re.search(r"<ht:approx_traffic>(.*?)</ht:approx_traffic>", item)
            news_m = re.search(r"<ht:news_item>(.*?)</ht:news_item>", item, re.DOTALL)
            if not title_m:
                continue
            keyword = title_m.group(1).strip()
            traffic = None
            if traffic_m:
                raw = traffic_m.group(1).replace("+", "").replace(",", "")
                try:
                    traffic = int(raw)
                except ValueError:
                    traffic = None
            results.append({
                "source": "google",
                "keyword": keyword,
                "region": "id",
                "volume": traffic,
                "rank": i + 1,
                "category": None,
            })
        print(f"[OK] Google Trends: {len(results)} keywords")
    except Exception as e:
        print(f"[WARN] Google Trends gagal: {e}", file=sys.stderr)
    return results


def fetch_google_trends_cities() -> list[dict]:
    """Ambil trending per kota besar Indonesia."""
    results = []
    cities = {"Jakarta": "ID-JK", "Surabaya": "ID-SU", "Bandung": "ID-BB", "Medan": "ID-SU2"}
    for city, geo in cities.items():
        try:
            url = f"https://trends.google.com/trending/rss?geo={geo}"
            xml = http_get(url).decode("utf-8", errors="replace")
            items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
            for i, item in enumerate(items[:10]):
                title_m = re.search(r"<title>(.*?)</title>", item)
                if not title_m:
                    continue
                results.append({
                    "source": "google",
                    "keyword": title_m.group(1).strip(),
                    "region": city.lower(),
                    "volume": None,
                    "rank": i + 1,
                    "category": None,
                })
        except Exception:
            pass
    if results:
        print(f"[OK] Google Trends kota: {len(results)} keywords")
    return results


# ─── SOURCE 2: TikTok Creative Center ───────────────────────────────────────

def fetch_tiktok_trends() -> list[dict]:
    """Ambil hashtag trending dari TikTok Creative Center (publik)."""
    results = []
    try:
        # TikTok Creative Center trending hashtags API (publik)
        url = (
            "https://ads.tiktok.com/creative_radar_api/v1/popular/hashtag/list"
            "?limit=30&period=7&country=ID"
        )
        data = http_get_json(url, headers={"Referer": "https://ads.tiktok.com/business/creativecenter/"})
        items = data.get("data", {}).get("list", []) or data.get("data", []) or []
        for i, item in enumerate(items[:30]):
            name = item.get("hashtag") or item.get("name") or item.get("title") or ""
            if not name:
                continue
            name = name.lstrip("#")
            views = item.get("video_count") or item.get("views") or item.get("publish_cnt")
            results.append({
                "source": "tiktok",
                "keyword": name,
                "region": "id",
                "volume": int(views) if views else None,
                "rank": i + 1,
                "category": item.get("industry") or item.get("category"),
            })
        print(f"[OK] TikTok trends: {len(results)} hashtags")
    except Exception as e:
        print(f"[WARN] TikTok trends gagal: {e}", file=sys.stderr)
    return results


# ─── SOURCE 3: Shopee trending (scrape publik) ──────────────────────────────

def fetch_shopee_trending() -> list[dict]:
    """Scrape halaman trending Shopee Indonesia (publik)."""
    results = []
    try:
        # Shopee discovery / trending page
        url = "https://shopee.co.id/mall/trending"
        html = http_get(url).decode("utf-8", errors="replace")
        # Cari pattern nama produk di HTML
        # Shopee biasanya menyimpan data di window.__INITIAL_STATE__ atau script JSON
        json_m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;?\s*</script>', html, re.DOTALL)
        if json_m:
            try:
                state = json.loads(json_m.group(1))
                # Navigasi ke item list (struktur bisa berubah, navigasi defensif)
                items = _deep_find_items(state)
                for i, item in enumerate(items[:20]):
                    name = item.get("name") or item.get("item_basic", {}).get("name") or ""
                    if not name:
                        continue
                    results.append({
                        "source": "shopee",
                        "keyword": name[:120],
                        "region": "id",
                        "volume": item.get("sold") or item.get("item_basic", {}).get("sold"),
                        "rank": i + 1,
                        "category": None,
                    })
            except (json.JSONDecodeError, KeyError):
                pass
        if not results:
            # Fallback: cari link produk di HTML
            links = re.findall(r'/[^"\']+-(\d{6,})', html)
            seen = set()
            for lid in links[:20]:
                if lid not in seen:
                    seen.add(lid)
                    results.append({
                        "source": "shopee",
                        "keyword": f"shopee_item_{lid}",
                        "region": "id",
                        "volume": None,
                        "rank": len(results) + 1,
                        "category": None,
                    })
        print(f"[OK] Shopee trending: {len(results)} items")
    except Exception as e:
        print(f"[WARN] Shopee trending gagal: {e}", file=sys.stderr)
    return results


def _deep_find_items(obj, depth=0) -> list[dict]:
    """Cari list item produk secara rekursif di JSON Shopee."""
    if depth > 8:
        return []
    if isinstance(obj, list):
        if obj and isinstance(obj[0], dict) and ("name" in obj[0] or "item_basic" in obj[0]):
            return obj
        for x in obj:
            r = _deep_find_items(x, depth + 1)
            if r:
                return r
    elif isinstance(obj, dict):
        for v in obj.values():
            r = _deep_find_items(v, depth + 1)
            if r:
                return r
    return []


# ─── SOURCE 4: Tokopedia trending ───────────────────────────────────────────

def fetch_tokopedia_trending() -> list[dict]:
    """Scrape halaman trending Tokopedia (publik)."""
    results = []
    try:
        url = "https://www.tokopedia.com/trending"
        html = http_get(url).decode("utf-8", errors="replace")
        # Cari JSON data di script tags
        scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        for script in scripts:
            if '"name"' in script and ('"price"' in script or '"sold"' in script):
                try:
                    # Coba parse sebagai JSON array atau object
                    data = json.loads(script)
                    items = _deep_find_items(data)
                    for i, item in enumerate(items[:20]):
                        name = item.get("name") or item.get("productName") or ""
                        if not name:
                            continue
                        results.append({
                            "source": "tokopedia",
                            "keyword": name[:120],
                            "region": "id",
                            "volume": item.get("sold") or item.get("itemCount"),
                            "rank": i + 1,
                            "category": None,
                        })
                    break
                except (json.JSONDecodeError, TypeError):
                    continue
        print(f"[OK] Tokopedia trending: {len(results)} items")
    except Exception as e:
        print(f"[WARN] Tokopedia trending gagal: {e}", file=sys.stderr)
    return results


# ─── MAIN COLLECTOR ─────────────────────────────────────────────────────────

def collect_all() -> dict:
    """Kumpulkan tren dari semua sumber, insert ke DB, update skor produk."""
    all_trends: list[dict] = []

    # Prioritas: Google > TikTok > Tokopedia > Shopee (Shopee paling riskan)
    for fetcher in [
        fetch_google_trends,
        fetch_google_trends_cities,
        fetch_tiktok_trends,
        fetch_tokopedia_trending,
        fetch_shopee_trending,
    ]:
        try:
            trends = fetcher()
            all_trends.extend(trends)
        except Exception as e:
            print(f"[ERROR] {fetcher.__name__}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    # Insert ke DB
    insert_result = {"ok": False, "count": 0}
    if all_trends:
        insert_result = insert_trends_batch(all_trends)

    # Update skor produk berdasarkan tren
    score_result = update_product_scores()

    summary = {
        "ok": True,
        "total_trends": len(all_trends),
        "by_source": {},
        "insert": insert_result,
        "score_update": score_result,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    for t in all_trends:
        s = t["source"]
        summary["by_source"][s] = summary["by_source"].get(s, 0) + 1

    # Top 5 lintas sumber: volume desc (null terakhir), rank asc
    ranked = sorted(all_trends, key=lambda t: (-(t.get("volume") or 0), t.get("rank") or 99))
    summary["top5"] = [
        {"keyword": t["keyword"], "source": t["source"], "volume": t.get("volume"), "rank": t.get("rank")}
        for t in ranked[:5]
    ]

    print(f"[DONE] {len(all_trends)} tren dari {len(summary['by_source'])} sumber")
    return summary


# ─── HTTP SERVER ────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[HTTP] {fmt % args}", file=sys.stderr)

    def _send_json(self, obj: dict, status: int = 200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send_json({"status": "ok"})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/run":
            try:
                summary = collect_all()
                self._send_json(summary)
            except Exception as e:
                traceback.print_exc(file=sys.stderr)
                self._send_json({"ok": False, "error": str(e)}, 500)
        else:
            self._send_json({"error": "not found"}, 404)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--serve", action="store_true", help="Run HTTP server")
    parser.add_argument("--port", type=int, default=8092)
    args = parser.parse_args()

    if args.once:
        summary = collect_all()
        print(json.dumps(summary, indent=2))
    elif args.serve:
        server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
        print(f"[LISTEN] trend_scout on :{args.port}")
        server.serve_forever()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
