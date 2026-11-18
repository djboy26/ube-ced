// Vercel build step. Fetches the checked page from the public repo at a pinned commit, verifies it, stamps the public address
// into the share tags, and writes the result to public/. Nothing else is changed.
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';

const COMMIT = '__COMMIT__';
const FILES = { 'index.html': '__SHA_INDEX__', 'og.png': '__SHA_OG__' };
const base = `https://raw.githubusercontent.com/djboy26/ube-ced/${COMMIT}/`;
const host = process.env.VERCEL_PROJECT_PRODUCTION_URL || 'ube-calculator.vercel.app';
const site = 'https://' + host;
console.log('public address:', site, '| VERCEL_PROJECT_PRODUCTION_URL =', process.env.VERCEL_PROJECT_PRODUCTION_URL, '| VERCEL_ENV =', process.env.VERCEL_ENV);

await mkdir('public', { recursive: true });
for (const [name, want] of Object.entries(FILES)) {
  const r = await fetch(base + name);
  if (!r.ok) throw new Error(`${name}: HTTP ${r.status}`);
  let buf = Buffer.from(await r.arrayBuffer());
  const got = createHash('sha256').update(buf).digest('hex');
  if (got !== want) throw new Error(`${name}: sha256 is ${got}, expected ${want}`);
  if (name === 'index.html') {
    let s = buf.toString('utf8');
    const tag = '<meta property="og:image" content="og.png">';
    if (s.split(tag).length !== 2) throw new Error('share tag not found exactly once');
    s = s.replace(tag, [
      `<meta property="og:image" content="${site}/og.png">`,
      '<meta property="og:image:width" content="1200">',
      '<meta property="og:image:height" content="630">',
      `<meta property="og:url" content="${site}/">`,
      `<meta name="twitter:image" content="${site}/og.png">`,
      `<link rel="canonical" href="${site}/">`,
    ].join('\n'));
    buf = Buffer.from(s, 'utf8');
  }
  await writeFile('public/' + name, buf);
  console.log('wrote', name, buf.length, 'bytes');
}
