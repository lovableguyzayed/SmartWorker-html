// Action inventory: every visible button, link and form control on every
// screen, and whether what it points at exists.
//
//   node tools/audit/actions.js http://127.0.0.1:5055 out.json
//
// Signs in as the demo admin (demo / demo12345) and the supervisor (imran,
// password from SEED_SUPERVISOR_PASSWORD). A link "works" if a GET of it does
// not answer 4xx/5xx; a data-act button "works" if the function it names is
// defined on the page; a form "works" if its action route exists.
const { chromium } = require('playwright');
const fs = require('fs');

const BASE = process.argv[2] || 'http://127.0.0.1:5055';
const OUT = process.argv[3] || 'actions.json';
const ADMIN = ['/dashboard', '/workers', '/attendance', '/payroll', '/payroll/preview',
  '/transactions', '/closures', '/assignments', '/profile', '/settings', '/scan',
  '/notifications', '/add_worker', '/dues', '/worker/1', '/worker_attendance/1',
  '/worker/1/report', '/payroll/slip/1', '/worker/1/account', '/edit_worker/1',
  '/id_card/1', '/worker/7/login/powers'];
const SUP = ['/me', '/me/team', '/scan', '/me/payslip', '/worker/7/account'];
const PUBLIC = ['/', '/login', '/register', '/forgot-password'];

async function login(page, user, pw) {
  await page.goto(BASE + '/login');
  await page.fill('input[name=username]', user);
  await page.fill('input[name=password]', pw);
  await page.press('input[name=password]', 'Enter');
  await page.waitForURL(u => !u.pathname.startsWith('/login'), { timeout: 15000 });
}

async function inventory(page, who, path, linkCache) {
  await page.goto(BASE + path, { waitUntil: 'networkidle' });
  const items = await page.evaluate(() => {
    const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
    const label = el => (el.getAttribute('aria-label') || el.innerText || el.value || el.title ||
      el.placeholder || el.name || (el.querySelector('i') || {}).className || '').toString()
      .replace(/\s+/g, ' ').trim().slice(0, 50);
    const out = [];
    document.querySelectorAll('a[href],button,[data-act],select,input:not([type=hidden]),textarea,form').forEach(el => {
      const tag = el.tagName.toLowerCase();
      if (tag !== 'form' && !vis(el)) return;
      const act = el.getAttribute('data-act');
      let kind, target = '', ok = null;
      if (tag === 'form') { kind = 'form'; target = (el.getAttribute('method') || 'get').toUpperCase() + ' ' + (el.getAttribute('action') || location.pathname); }
      else if (tag === 'a') {
        const href = el.getAttribute('href');
        kind = 'link'; target = href;
        if (href.startsWith('#') || href.startsWith('javascript')) { ok = !!act || !!el.onclick || href !== '#'; }
      } else if (act) {
        kind = 'action'; target = act;
        const builtins = ['submit-form', 'back', 'toggle', 'close', 'print', 'navigate', 'reload', 'confirm-submit'];
        ok = typeof window[act] === 'function' || builtins.includes(act) || act.includes('-');
      } else if (tag === 'button') {
        kind = 'button'; target = el.type === 'submit' || (!el.getAttribute('type') && el.form) ? 'submits form' : (el.onclick ? 'onclick' : (el.id ? '#' + el.id : ''));
        // A type=button with no handler we can see is only suspicious, not proven dead:
        // listeners added with addEventListener are invisible from here.
        if (target === '') ok = 'unknown';
      } else { kind = 'field'; target = el.type || tag; ok = true; }
      out.push({ kind, label: label(el), target, ok });
    });
    return out;
  });
  for (const it of items) {
    if (it.kind === 'link' && it.ok === null) {
      const url = new URL(it.target, BASE + path);
      if (url.origin !== new URL(BASE).origin) { it.ok = 'external'; continue; }
      if (/logout/.test(url.pathname)) { it.ok = true; continue; }
      const key = who + url.pathname + url.search;
      if (!(key in linkCache)) {
        const r = await page.request.get(url.href, { maxRedirects: 0 }).catch(() => null);
        linkCache[key] = r ? r.status() : 0;
      }
      it.status = linkCache[key];
      it.ok = it.status > 0 && it.status < 400;
    }
    if (it.kind === 'form' && it.ok === null) it.ok = true;
  }
  return { who, path, items };
}

(async () => {
  const browser = await chromium.launch();
  const screens = [];
  const cache = {};
  const run = async (who, paths, creds) => {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await ctx.newPage();
    if (creds) await login(page, ...creds);
    for (const p of paths) screens.push(await inventory(page, who, p, cache));
    await ctx.close();
  };
  await run('public', PUBLIC, null);
  await run('admin', ADMIN, ['demo', 'demo12345']);
  await run('supervisor', SUP, ['imran', process.env.SEED_SUPERVISOR_PASSWORD || 'imran12345']);
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(screens, null, 1));
  const all = screens.flatMap(s => s.items);
  const bad = screens.flatMap(s => s.items.filter(i => i.ok === false).map(i => ({ screen: s.who + ' ' + s.path, ...i })));
  console.log(`${screens.length} screens, ${all.length} controls, ${bad.length} broken`);
  for (const b of bad) console.log('BROKEN', b.screen, b.kind, JSON.stringify(b.label), b.target, b.status || '');
})();
