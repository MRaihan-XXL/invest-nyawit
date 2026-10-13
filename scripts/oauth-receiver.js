// oauth-receiver.js — terima callback OAuth (TikTok/Meta), simpan code ke file, tampilkan pesan ramah.
// Dipanggil via Caddy: /oauth/* -> host.docker.internal:8099
const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8099;
const OUT = path.join(process.env.TEMP || '/tmp', 'oauth-callback.json');
const WELLKNOWN_DIR = path.join(__dirname, '..', 'well-known');

const server = http.createServer((req, res) => {
  const u = new URL(req.url, `http://${req.headers.host}`);
  if (u.pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('{"ok":true,"service":"oauth-receiver"}');
    return;
  }
  // TikTok URL verification: /.well-known/<file> -> serve dari folder well-known/
  if (u.pathname.startsWith('/.well-known/')) {
    const fname = path.basename(u.pathname);
    const fpath = path.join(WELLKNOWN_DIR, fname);
    if (fs.existsSync(fpath)) {
      const content = fs.readFileSync(fpath);
      res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end(content);
    } else {
      res.writeHead(404); res.end('not found');
    }
    return;
  }
  if (!u.pathname.startsWith('/oauth/')) {
    res.writeHead(404); res.end('not found'); return;
  }
  const provider = u.pathname.split('/')[2] || 'unknown';
  const params = Object.fromEntries(u.searchParams.entries());
  const payload = { provider, params, receivedAt: new Date().toISOString() };
  fs.writeFileSync(OUT, JSON.stringify(payload, null, 2));
  console.log('[oauth]', provider, JSON.stringify(params));

  const ok = params.code ? 'Kode diterima ✔' : 'Callback diterima (tanpa code)';
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(`<!DOCTYPE html><html lang="id"><body style="font-family:sans-serif;padding:40px;text-align:center">
    <h1>${ok}</h1>
    <p>Provider: <b>${provider}</b></p>
    <p>${params.code ? 'Kode sudah tersimpan. Tutup tab ini dan kembali ke terminal/PC.' : 'Tidak ada kode di URL. Coba lagi.'}</p>
  </body></html>`);
});

server.listen(PORT, '0.0.0.0', () => console.log(`[oauth-receiver] listening :${PORT}`));
