#!/usr/bin/env node
// Validasi struktural semua workflow n8n di workflows/.
// Cek: JSON valid, node unik, koneksi valid, sintaks jsCode, duplikat key connections.
const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '..', 'workflows');
let failures = 0;

for (const file of fs.readdirSync(dir).filter(f => f.endsWith('.json'))) {
  const full = path.join(dir, file);
  const raw = fs.readFileSync(full, 'utf8');
  const errors = [];

  let wf;
  try {
    wf = JSON.parse(raw);
  } catch (e) {
    console.error(`[FAIL] ${file}: JSON parse error: ${e.message}`);
    failures++;
    continue;
  }

  if (!wf.name) errors.push('missing workflow name');
  if (!Array.isArray(wf.nodes) || wf.nodes.length === 0) errors.push('no nodes');
  if (!wf.connections || typeof wf.connections !== 'object') errors.push('no connections');

  const names = new Set();
  const ids = new Set();
  for (const n of wf.nodes || []) {
    if (!n.name) errors.push('node without name');
    if (names.has(n.name)) errors.push(`duplicate node name: ${n.name}`);
    names.add(n.name);
    if (ids.has(n.id)) errors.push(`duplicate node id: ${n.id}`);
    ids.add(n.id);
    if (!n.type) errors.push(`node ${n.name}: missing type`);
    if (!Array.isArray(n.position)) errors.push(`node ${n.name}: missing position`);
    if (n.type === 'n8n-nodes-base.code') {
      const code = n.parameters && n.parameters.jsCode;
      if (!code) errors.push(`node ${n.name}: code node without jsCode`);
      else {
        try {
          new Function(code); // compile-only syntax check
        } catch (e) {
          errors.push(`node ${n.name}: jsCode syntax error: ${e.message}`);
        }
      }
    }
    if (n.type === 'n8n-nodes-base.postgres') {
      const cred = n.credentials && n.credentials.postgres;
      if (!cred) errors.push(`node ${n.name}: postgres node without credentials block`);
    }
  }

  for (const [src, conns] of Object.entries(wf.connections || {})) {
    if (!names.has(src)) errors.push(`connections from unknown node: ${src}`);
    for (const branch of Object.values(conns)) {
      for (const targets of Object.values(branch)) {
        for (const t of targets || []) {
          if (!names.has(t.node)) errors.push(`connection to unknown node: ${t.node}`);
        }
      }
    }
  }

  // deteksi duplicate key di bagian connections (JSON.parse menimpa diam-diam)
  const connIdx = raw.lastIndexOf('"connections"');
  if (connIdx >= 0) {
    const section = raw.slice(connIdx);
    const keyRe = /"([^"]+)":\s*\{\s*"(?:main)"\s*:/g;
    const seen = new Set();
    let m;
    while ((m = keyRe.exec(section)) !== null) {
      if (seen.has(m[1])) errors.push(`duplicate connection key: ${m[1]}`);
      seen.add(m[1]);
    }
  }

  if (errors.length) {
    failures++;
    console.error(`[FAIL] ${file} (${wf.name})`);
    for (const e of errors) console.error(`   - ${e}`);
  } else {
    console.log(`[ OK ] ${file} (${wf.name}) — ${wf.nodes.length} nodes`);
  }
}

if (failures) {
  console.error(`\n${failures} file(s) gagal validasi`);
  process.exit(1);
}
console.log('\nSemua workflow valid.');
