// oauth-receiver.js v4 — OAuth 1-klik-OK untuk TikTok + Instagram.
// - GET /health                     → healthcheck (watchdog)
// - GET /.well-known/<file>         → file verifikasi URL TikTok
// - GET /oauth/start/tiktok         → 302 ke authorize TikTok (redirect_uri = GitHub Pages permanen)
// - GET /oauth/start/meta           → 302 ke dialog Facebook (redirect_uri = localhost:8099)
// - GET /oauth/tiktok               → terima ?code= → auto-tukar token → INSERT tokens → halaman sukses + Telegram
// - GET /oauth/meta                 → terima ?code= → long-lived → page token → IG id → INSERT tokens → halaman sukses + Telegram
// - GET /oauth/capture              → penerima halaman fragment-capture (param dari URL #hash)
// Log append-only: %TEMP%\oauth-callbacks.log (JSONL, tidak pernah menimpa).
// DB via docker exec psql (tanpa dependensi npm).
const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const PORT = 8099;
const ROOT = 'D:\\FlyEnv-Data\\server\\www\\invest-nyawit';
const ENVF = path.join(ROOT, '.env');
const WELLKNOWN_DIR = path.join(ROOT, 'well-known');
const LOG = path.join(process.env.TEMP || '/tmp', 'oauth-callbacks.log');
const STATE_F = path.join(process.env.TEMP || '/tmp', 'oauth-state.json');

function env(name) {
  try {
    const line = fs.readFileSync(ENVF, 'utf8').split(/\r?\n/).find(l => l.startsWith(name + '='));
    return line ? line.slice(name.length + 1).trim() : '';
  } catch { return ''; }
}
function logJson(obj) {
  try { fs.appendFileSync(LOG, JSON.stringify({ ts: new Date().toISOString(), ...obj }) + '\n'); } catch {}
}
function esc(s) { return String(s ?? '').replace(/'/g, "''"); }
function psql(sql) {
  return execFileSync('docker', ['exec', '-i', 'invest-nyawit-postgres-1', 'psql', '-U', 'nyawit', '-d', 'investnyawit', '-v', 'ON_ERROR_STOP=1', '-f', '-'],
    { input: sql, encoding: 'utf8', timeout: 20000 });
}
function upsertToken(platform, access, refresh, expiresAtIso, extraObj) {
  const extra = esc(JSON.stringify(extraObj || {}));
  const exp = expiresAtIso ? `'${esc(expiresAtIso)}'` : 'NULL';
  psql(`INSERT INTO tokens (platform, access_token, refresh_token, expires_at, extra)
VALUES ('${esc(platform)}', '${esc(access)}', '${esc(refresh || '')}', ${exp}, '${extra}'::jsonb)
ON CONFLICT (platform) DO UPDATE SET
  access_token = EXCLUDED.access_token,
  refresh_token = EXCLUDED.refresh_token,
  expires_at = EXCLUDED.expires_at,
  extra = EXCLUDED.extra,
  updated_at = now();`);
}
function tgSend(text) {
  const tok = env('TELEGRAM_BOT_TOKEN'), chat = env('TELEGRAM_CHAT_ID');
  if (!tok || !chat) return;
  const body = JSON.stringify({ chat_id: chat, text });
  const req = https.request({ hostname: 'api.telegram.org', path: `/bot${tok}/sendMessage`, method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) }, timeout: 15000 },
    res => { res.resume(); });
  req.on('error', () => {});
  req.write(body); req.end();
}
function fetchJson(url, opts = {}) {
  return fetch(url, { ...opts, signal: AbortSignal.timeout(25000) }).then(async r => {
    const j = await r.json().catch(() => ({}));
    return { status: r.status, body: j };
  });
}
function html(res, code, title, lines) {
  const lis = lines.map(l => `<li>${l}</li>`).join('');
  res.writeHead(code, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(`<!DOCTYPE html><html lang="id"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<body style="font-family:system-ui,sans-serif;max-width:480px;margin:60px auto;padding:0 20px;text-align:center">
<h1 style="font-size:22px">${title}</h1><ul style="text-align:left;line-height:1.6">${lis}</ul>
<p style="color:#666;font-size:13px">Tutup tab ini lalu kembali ke PC/Telegram.</p></body></html>`);
}
function makeState() {
  const s = crypto.randomBytes(16).toString('hex');
  fs.writeFileSync(STATE_F, JSON.stringify({ state: s, at: Date.now() }), 'utf8');
  return s;
}
function checkState(got) {
  try {
    const { state } = JSON.parse(fs.readFileSync(STATE_F, 'utf8'));
    return state === got;
  } catch { return false; }

}
// Redirect URI TikTok yang PERMANEN (GitHub Pages) — tidak berubah saat tunnel restart.
// Halaman docs/oauth-tiktok.html meneruskan ?code=&state= ke receiver lokal (/oauth/tiktok).
const TIKTOK_REDIRECT_URI = 'https://mraihan-xxl.github.io/invest-nyawit/oauth-tiktok.html';

// Page "Prime Finds ID" yang sudah tersambung ke IG Business @primefinds.id.
// Dipakai sebagai CADANGAN ketika /me/accounts mengembalikan kosong (umum terjadi pada
// Facebook Login for Business — Page disembunyikan dari /me/accounts padahal ada & valid).
const KNOWN_PAGE_ID = '1394674410394276';

// ── auto-exchange TikTok ──
async function handleTikTok(code, res) {
  const key = env('TIKTOK_CLIENT_KEY'), sec = env('TIKTOK_CLIENT_SECRET');
  const redirect = TIKTOK_REDIRECT_URI;
  if (!key || !sec) return html(res, 500, 'TikTok gagal ❌', ['TIKTOK_CLIENT_KEY/SECRET kosong di .env']);
  const body = new URLSearchParams({ client_key: key, client_secret: sec, code, grant_type: 'authorization_code', redirect_uri: redirect });
  const ex = await fetchJson('https://open.tiktokapis.com/v2/oauth/token/', {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: body.toString() });
  logJson({ provider: 'tiktok_exchange', status: ex.status, resp: ex.body });
  const b = ex.body;
  if (!b.access_token) return html(res, 400, 'TikTok gagal tukar token ❌',
    [`HTTP ${ex.status}`, JSON.stringify(b).slice(0, 300), 'Screenshot halaman ini lalu kirim ke chat.']);
  const exp = new Date(Date.now() + (Number(b.expires_in) || 86400) * 1000).toISOString();
  upsertToken('tiktok', b.access_token, b.refresh_token || '', exp,
    { open_id: b.open_id, scope: b.scope, refresh_expires_in: b.refresh_expires_in });
  tgSend(`TikTok terhubung ✅\nscope: ${b.scope}\nopen_id: ${b.open_id}\nexpire akses: jam\nRefresh token: 365 hari (auto tiap 18 jam)`);
  html(res, 200, 'TikTok terhubung ✅', [`scope: ${b.scope}`, 'Token tersimpan otomatis. Publish berikutnya pakai token ini.']);
}
// ── auto-exchange Meta (code → short → long-lived → page token → IG id) ──
async function handleMeta(code, res) {
  const appId = env('IG_APP_ID'), sec = env('IG_APP_SECRET');
  const redirect = 'http://localhost:8099/oauth/meta';
  if (!appId || !sec) return html(res, 500, 'Instagram gagal ❌', ['IG_APP_ID/IG_APP_SECRET kosong di .env']);
  const u1 = new URLSearchParams({ client_id: appId, redirect_uri: redirect, client_secret: sec, code });
  const r1 = await fetchJson('https://graph.facebook.com/v21.0/oauth/access_token?' + u1);
  const shortTok = r1.body.access_token;
  logJson({ provider: 'meta_short', status: r1.status, has_token: !!shortTok });
  if (!shortTok) return html(res, 400, 'Instagram gagal ❌',
    ['Tukar code gagal:', JSON.stringify(r1.body).slice(0, 300), 'Screenshot halaman ini.']);
  const r2 = await fetchJson('https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=' +
    encodeURIComponent(appId) + '&client_secret=' + encodeURIComponent(sec) + '&fb_exchange_token=' + encodeURIComponent(shortTok));
  const longTok = r2.body.access_token;
  logJson({ provider: 'meta_long', status: r2.status, has_token: !!longTok });
  if (!longTok) return html(res, 400, 'Instagram gagal ❌',
    ['Tukar long-lived gagal:', JSON.stringify(r2.body).slice(0, 300)]);

  // ── DIAGNOSTIC: identitas akun yang baru authorize + scope yang benar-benar ter-grant ──
  try {
    const me = await fetchJson('https://graph.facebook.com/v21.0/me?fields=id,name&access_token=' + encodeURIComponent(longTok));
    logJson({ provider: 'meta_me', id: me.body.id, name: me.body.name, status: me.status });
  } catch (e) { logJson({ provider: 'meta_me', err: String(e) }); }
  try {
    const dv = await fetchJson('https://graph.facebook.com/v21.0/debug_token?input_token=' +
      encodeURIComponent(longTok) + '&access_token=' + encodeURIComponent(appId + '|' + sec));
    const d = dv.body && dv.body.data;
    logJson({ provider: 'meta_debug', status: dv.status, scopes: (d && d.scopes) || (d && d.granular_scopes) || null,
      is_valid: d && d.is_valid, app_id: d && d.app_id });
  } catch (e) { logJson({ provider: 'meta_debug', err: String(e) }); }
  // ── DIAGNOSTIC + CADANGAN: probe langsung ke Page ID yang diketahui ──
  //    Membedakan "Page tak terlihat di /me/accounts (portofolio/bisnis)" vs "Page memang tidak ada".
  //    Hasilnya dipakai sebagai fallback penyimpanan token bila /me/accounts kosong.
  let directPage = null;
  try {
    const dg = await fetchJson('https://graph.facebook.com/v21.0/' + KNOWN_PAGE_ID +
      '?fields=name,instagram_business_account&access_token=' + encodeURIComponent(longTok));
    logJson({ provider: 'meta_direct_page', status: dg.status, body: dg.body });
    if (dg.body && dg.body.id) directPage = dg.body;
  } catch (e) { logJson({ provider: 'meta_direct_page', err: String(e) }); }

  const r3 = await fetchJson('https://graph.facebook.com/v21.0/me/accounts?fields=id,name,access_token&access_token=' + encodeURIComponent(longTok));
  const pages = r3.body.data || [];
  logJson({ provider: 'meta_pages', status: r3.status, count: pages.length, pages: pages.map(p => ({ id: p.id, name: p.name })) });

  // Cek SEMUA Page (bukan hanya yang pertama) — pilih yang sudah tersambung IG Business/Creator.
  const checked = [];
  let page = null, igId = null;
  for (const p of pages) {
    const r4 = await fetchJson('https://graph.facebook.com/v21.0/' + p.id +
      '?fields=instagram_business_account,connected_instagram_account&access_token=' + encodeURIComponent(p.access_token));
    const iba = r4.body.instagram_business_account;
    const cia = r4.body.connected_instagram_account;
    const id = (iba && iba.id) || (cia && cia.id) || null;
    checked.push({ page: p.name, page_id: p.id, http: r4.status, ig_user_id: id, raw: r4.body });
    if (id && !page) { page = p; igId = id; }
  }
  logJson({ provider: 'meta_ig', found: !!igId, checked });

  // ── CADANGAN: /me/accounts kosong ATAU tak ada Page tersambung IG.
  //    Probe langsung ke KNOWN_PAGE_ID tetap bisa mengembalikan instagram_business_account.
  //    Tanpa fallback ini token BERHASIL di-exchange tapi tidak pernah tersimpan (bug 14-10-2026).
  let pageId = page && page.id, pageName = page && page.name, pageTok = page && page.access_token;
  if (!igId && directPage) {
    const iba = directPage.instagram_business_account;
    const cia = directPage.connected_instagram_account;
    const id = (iba && iba.id) || (cia && cia.id) || null;
    if (id) {
      igId = id;
      pageId = pageId || directPage.id;
      pageName = pageName || directPage.name;
      logJson({ provider: 'meta_fallback', via: 'direct_page_probe', page_id: pageId, page_name: pageName, ig_user_id: igId });
    }
  }

  if (!igId) {
    const names = pages.length
      ? 'Page di akun ini: ' + pages.map(p => '"' + p.name + '"').join(', ') + ' (belum ada yang tersambung IG).'
      : '/me/accounts kosong dan probe langsung tidak menemukan instagram_business_account.';
    return html(res, 400, 'Instagram gagal ❌',
      ['Token OK, tapi tidak bisa menemukan IG Business yang tersambung.', names,
        'Langkah (urut): (1) IG harus akun profesional — IG: Pengaturan → Akun → Beralih ke akun profesional → Business.',
        '(2) Sambungkan: di Page: Pengaturan → Akun Tertaut → Instagram → Sambungkan akun.',
        '(3) Atau dari IG: Pengaturan → Pusat Akun → Profil → Tambah akun Facebook → pilih Page tadi.',
        'Setelah tersambung, ulangi link authorize.']);
  }

  // Dokumen resmi Meta (media_publish): "Requires a USER access token with instagram_basic
  // dan instagram_content_publish, dan app user harus punya task MANAGE/CREATE_CONTENT di Page tersambung."
  // -> simpan user long-lived token, bukan Page token.
  const exp = new Date(Date.now() + 365 * 86400 * 1000).toISOString();
  upsertToken('instagram', longTok, '', exp,
    { ig_user_id: igId, page_id: pageId, page_name: pageName, page_access_token: pageTok || null, user_long_lived: longTok });

  // Self-check: buktikan token benar-benar bisa membaca IG account yang dituju.
  try {
    const v = await fetchJson('https://graph.facebook.com/v21.0/' + igId +
      '?fields=id,username,account_type&access_token=' + encodeURIComponent(longTok));
    logJson({ provider: 'meta_ig_verify', status: v.status, body: v.body });
  } catch (e) { logJson({ provider: 'meta_ig_verify', err: String(e) }); }

  tgSend(`Instagram terhubung ✅\nPage: ${pageName}\nIG id: ${igId}\n(user long-lived token — instagram_content_publish)`);
  html(res, 200, 'Instagram terhubung ✅', [`Page: ${pageName}`, `IG user id: ${igId}`, 'Token tersimpan otomatis.']);
}

// ── halaman fragment-capture: gabungkan #hash ke query lalu redirect balik ──
function fragPage(provider) {
  return `<!DOCTYPE html><html lang="id"><meta charset="utf-8"><script>
(function(){
  var p = new URLSearchParams(location.search);
  var h = location.hash.replace(/^#/,'');
  if (h && !p.get('code')) {
    new URLSearchParams(h).forEach(function(v,k){ if(!p.has(k)) p.set(k,v); });
    location.replace('/oauth/${provider}?' + p.toString() + '&_frag=1');
  } else if (!p.get('code')) {
    document.write('<body style="font-family:sans-serif;padding:40px;text-align:center"><h1>Tidak ada kode</h1><p>Callback kosong (tanpa ?code=). Pastikan kamu membuka link dari /oauth/start/${provider}, lalu screenshot pesan error di TikTok/Facebook.</p></body>');
  } else { location.replace('/oauth/${provider}?' + p.toString()); }
})();
</script><body>Memproses…</body></html>`;
}

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, `http://${req.headers.host}`);
  const p = u.pathname;

  if (p === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end('{"ok":true,"service":"oauth-receiver"}');
  }
  if (p.startsWith('/.well-known/')) {
    const f = path.join(WELLKNOWN_DIR, path.basename(p));
    if (fs.existsSync(f)) { res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' }); return res.end(fs.readFileSync(f)); }
    res.writeHead(404); return res.end('not found');
  }

  // start endpoints → 302 ke platform
  if (p === '/oauth/start/tiktok') {
    const st = makeState();
    const q = new URLSearchParams({
      client_key: env('TIKTOK_CLIENT_KEY'), scope: 'video.upload',
      response_type: 'code', redirect_uri: TIKTOK_REDIRECT_URI, state: st });
    logJson({ action: 'start_tiktok', redirect_uri: TIKTOK_REDIRECT_URI });
    res.writeHead(302, { Location: 'https://www.tiktok.com/v2/auth/authorize/?' + q });
    return res.end();
  }
  // diagnostic: authorize tanpa scope (isolasi client_key vs scope video.upload)
  if (p === '/oauth/start/tiktok-test') {
    const st = makeState();
    const q = new URLSearchParams({
      client_key: env('TIKTOK_CLIENT_KEY'), scope: 'user.info.basic',
      response_type: 'code', redirect_uri: TIKTOK_REDIRECT_URI, state: st });
    logJson({ action: 'start_tiktok_test', redirect_uri: TIKTOK_REDIRECT_URI });
    res.writeHead(302, { Location: 'https://www.tiktok.com/v2/auth/authorize/?' + q });
    return res.end();
  }
  if (p === '/oauth/start/meta') {
    const st = makeState();
    const q = new URLSearchParams({
      client_id: env('IG_APP_ID'),
      redirect_uri: 'http://localhost:8099/oauth/meta',
      scope: 'instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement',
      // Facebook Login for Business: "all permissions must be granted or NONE" —
      // tanpa rerequest, Facebook menolak memberi izin ulang dan memakai setelan lama yang cacat.
      auth_type: 'rerequest',
      response_type: 'code', state: st });
    logJson({ action: 'start_meta' });
    res.writeHead(302, { Location: 'https://www.facebook.com/v21.0/dialog/oauth?' + q });
    return res.end();
  }
  if (p === '/oauth/capture') {
    // dipanggil halaman fragment (opsional) — teruskan ke handler utama
    const prov = u.searchParams.get('provider') || 'tiktok';
    u.searchParams.delete('provider');
    res.writeHead(302, { Location: '/oauth/' + prov + '?' + u.searchParams.toString() });
    return res.end();
  }

  // callback utama
  if (p === '/oauth/tiktok' || p === '/oauth/meta') {
    const provider = p.split('/')[2];
    const params = Object.fromEntries(u.searchParams.entries());
    logJson({ callback: provider, params, frag: u.searchParams.get('_frag') || null });
    // kompat: file lama tetap ditulis (overwrite) agar tool lama tidak rusak
    try { fs.writeFileSync(path.join(process.env.TEMP || '/tmp', 'oauth-callback.json'),
      JSON.stringify({ provider, params, receivedAt: new Date().toISOString() }, null, 2)); } catch {}

    if (u.searchParams.has('error')) {
      return html(res, 400, `${provider} error ❌`,
        [`error: ${params.error}`, `description: ${params.error_description || '-'}`,
          'Kalau "URL Blocked": tambahkan http://localhost:8099/oauth/meta ke Valid OAuth Redirect URIs di app settings Facebook (untuk Meta), atau daftarkan ulang redirect URI tunnel di console TikTok.']);
    }
    if (!params.code) {
      // kemungkinan param ada di #hash → halaman capture
      return res.end(fragPage(provider));
    }
    if (params.state && !checkState(params.state)) {
      logJson({ state_mismatch: provider, got: params.state });
      // tetap proses (satu user) tapi catat
    }
    try {
      if (provider === 'tiktok') return await handleTikTok(params.code, res);
      return await handleMeta(params.code, res);
    } catch (e) {
      logJson({ exchange_error: provider, err: String(e) });
      return html(res, 500, `${provider} gagal ❌`, [String(e).slice(0, 300)]);
    }
  }

  res.writeHead(404); res.end('not found');
});

server.listen(PORT, '0.0.0.0', () => console.log(`[oauth-receiver v2] listening :${PORT}`));
