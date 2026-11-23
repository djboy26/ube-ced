// Vercel build step. Fetches the checked page from the public repo at a pinned commit, verifies it, stamps the public address
// into the share tags, and writes the result to public/. Nothing else is changed.
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';

const COMMIT = '92e12b990e5882fe6c966cc728b6baf987023b47';
const FILES = { 'index.html': '5c1fec1e2e08a8a987915be6bdae67c4716bcf4a865566684c5187a0bc692a9b', 'og.png': '1df98fef749cf9d194719055d151eabcf66f1f025f26ea09b2e89b83a0817046' };
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
    // AI-search fixes (24 Nov 2026): title under 70 characters, and schema.org JSON-LD saying what the page is.
    const oldTitle = '<title>How much energy does it take to keep you alive? · Universal Basic Energy</title>';
    if (s.split(oldTitle).length !== 2) throw new Error('title not found exactly once');
    s = s.replace(oldTitle, '<title>How much energy does it take to keep you alive? · UBE</title>');
    if (s.split('</head>').length !== 2) throw new Error('</head> not found exactly once');
    s = s.replace('</head>', '<script type="application/ld+json">' + JSON.stringify(jsonld()) + '</script>\n</head>');
    buf = Buffer.from(s, 'utf8');
  }
  await writeFile('public/' + name, buf);
  console.log('wrote', name, buf.length, 'bytes');
}

// Files for crawlers and AI answer engines. All crawlers are welcome, training crawlers included.
const today = new Date().toISOString().slice(0, 10);
const extra = {
  'robots.txt': `User-agent: *\nAllow: /\n\nSitemap: ${site}/sitemap.xml\n`,
  'sitemap.xml': `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n  <url><loc>${site}/</loc><lastmod>${today}</lastmod></url>\n</urlset>\n`,
  'llms.txt': [
    '# Universal Basic Energy (UBE)',
    '',
    '> How much energy does it take to keep a person alive? UBE measures a survival basket (food, heat, water, transport, everyday goods, healthcare) in kWh of primary energy a year, and proposes that every citizen owns an inalienable share of the energy their survival runs on.',
    '',
    'One person, one year, in Denmark: about 7,500 kWh of primary energy on the 2023 grid (model v5; healthcare is a provisional figure).',
    '',
    '## Pages',
    '',
    `- [Survival energy calculator](${site}/): pick a place in Denmark and a basket of survival goods, see the kWh need by need, and follow each supply chain to its roots`,
    '',
    '## Sources',
    '',
    '- [Model and data, open source](https://github.com/djboy26/ube-ced)',
    '- [Archived model with DOI](https://doi.org/10.5281/zenodo.23651855)',
    '',
  ].join('\n'),
};
for (const [name, text] of Object.entries(extra)) {
  await writeFile('public/' + name, text);
  console.log('wrote', name, Buffer.byteLength(text), 'bytes');
}

function jsonld() {
  const project = { '@type': 'Organization', '@id': `${site}/#ube`, name: 'Universal Basic Energy', alternateName: 'UBE', url: `${site}/`,
    sameAs: ['https://github.com/djboy26/ube-ced', 'https://doi.org/10.5281/zenodo.23651855'] };
  return { '@context': 'https://schema.org', '@graph': [
    project,
    { '@type': 'WebSite', '@id': `${site}/#site`, url: `${site}/`, name: 'Universal Basic Energy', publisher: { '@id': `${site}/#ube` }, inLanguage: 'en' },
    { '@type': 'WebApplication', '@id': `${site}/#calculator`, name: 'UBE survival energy calculator', url: `${site}/`,
      description: 'Calculates the primary energy, in kWh a year, that one person in Denmark needs to survive: food, heat, water, transport, everyday goods and healthcare, need by need, with each supply chain traced to its roots.',
      applicationCategory: 'EducationalApplication', operatingSystem: 'Any', isAccessibleForFree: true,
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'EUR' },
      creator: { '@id': `${site}/#ube` }, isBasedOn: 'https://doi.org/10.5281/zenodo.23651855', inLanguage: 'en' },
  ] };
}
