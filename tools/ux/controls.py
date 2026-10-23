"""Every control on every screen, and whether it leads anywhere.

A button that calls a function nobody defined, a link to a route that was
renamed, an icon wired to nothing at all — none of these look wrong. They
look exactly like the ones that work, right up until somebody presses them
on a site with no signal and a foreman waiting.

So this presses nothing. It reads every control the browser can see and
asks what it is attached to:

  * a link      -> is the href a real route, and does it answer?
  * a submit    -> does its form have an action that resolves?
  * an onclick  -> is that function actually defined on the page?
  * a listener  -> was addEventListener called on it?
  * none of the above -> it is reported

There is no DOM API that lists an element's listeners, and guessing from
the markup gets it wrong: the first version of this called five controls
dead that were all bound with addEventListener — the password eye, the
photo button, both OTP buttons. So addEventListener is wrapped before any
page script runs and marks the elements it is called on. Nothing is
reported dead that something is listening to.

Checking an onclick means reading the first identifier out of it and asking
the page whether it is a function. That catches the whole class of fault
where a handler is renamed or lives in a script that did not load.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from playwright.sync_api import sync_playwright
from app import app
import models as m

EXE = os.environ.get('UX_CHROME',
                     '/opt/pw-browsers/chromium-1194/chrome-linux/chrome')
B = os.environ.get('UX_BASE', 'http://127.0.0.1:5000')
# Results land in tools/ux/out/, which is not tracked.
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(OUT, exist_ok=True)

# Wrapped before any page script runs, so every binding is recorded.
WATCH_LISTENERS = r"""
(() => {
  const orig = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, fn, opts) {
    try {
      if (this instanceof Element) {
        const seen = this.getAttribute('data-ux-listeners') || '';
        if (seen.indexOf(type) === -1) {
          this.setAttribute('data-ux-listeners', (seen + ' ' + type).trim());
        }
      }
    } catch (e) { /* never let bookkeeping break the page */ }
    return orig.call(this, type, fn, opts);
  };
})();
"""

PROBE = r"""
() => {
  const rows = [];
  const sel = 'button, a, input[type=submit], input[type=button], ' +
              '[role=button], label[for], select, input[type=checkbox], ' +
              'input[type=radio], summary, details';
  for (const el of document.querySelectorAll(sel)) {
    if (!el.checkVisibility || !el.checkVisibility()) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;

    const tag = el.tagName.toLowerCase();
    const text = (el.innerText || el.value || '').trim().slice(0, 36);
    const aria = el.getAttribute('aria-label') || '';
    const onclick = el.getAttribute('onclick') || '';
    // Inline handlers are gone — the Content-Security-Policy forbids them —
    // so the question "what does this control call?" is now answered by
    // data-act, which static/js/actions.js dispatches on.
    const act = el.getAttribute('data-act') || '';
    const href = el.getAttribute('href') || '';
    const form = el.closest('form');

    // data-act names the function outright; the dispatcher's own verbs
    // (submit-form, print, remove-closest…) are not globals and are listed
    // here so they are not reported as missing.
    const VERBS = ['submit-form', 'submit-form-if-file', 'remove-closest',
                   'remove-target', 'print'];
    let handler = '', handlerOk = null;
    if (act) {
      handler = act;
      handlerOk = VERBS.indexOf(act) !== -1 || typeof window[act] === 'function';
    } else if (onclick) {
      const match = onclick.match(/^\s*(?:return\s+)?([A-Za-z_$][\w$.]*)\s*\(/);
      // `this.closest(...)`, `event.preventDefault()` and friends begin with
      // an identifier and a bracket, so they match — but the root is a
      // keyword bound at call time, not a global to look up, and reporting
      // them as undefined functions is a false alarm against code that
      // works. The flash toast's close button is one.
      const root = match ? match[1].split('.')[0] : '';
      if (match && root !== 'this' && root !== 'event') {
        handler = match[1];
        try {
          handlerOk = typeof window[root] === 'function'
                   || typeof window[root] === 'object';
        } catch (e) { handlerOk = false; }
      } else {
        handler = '(inline statement)';
        handlerOk = true;        // e.g. this.closest('.alert').remove()
      }
    }

    let kind;
    if (href && href !== '#' && !href.startsWith('javascript:')) kind = 'link';
    else if (act) kind = 'action';
    else if (el.hasAttribute('data-confirm')) kind = 'confirm';
    else if (onclick) kind = 'onclick';
    else if (tag === 'summary' || tag === 'details') kind = 'disclosure';
    else if (el.type === 'submit' || (tag === 'button' && !el.type && form)) kind = 'submit';
    else if (tag === 'select' || el.type === 'checkbox' || el.type === 'radio') kind = 'field';
    else if (tag === 'label') kind = 'label';
    else if (el.getAttribute('data-ux-listeners')) kind = 'listener';
    else if (el.closest('[data-ms-item]')) kind = 'selection-row';
    else if (el.dataset && Object.keys(el.dataset).length) kind = 'data-hook';
    else kind = 'NOTHING';

    rows.push({
      tag: tag, kind: kind, text: text, aria: aria,
      href: href, onclick: (act || onclick).slice(0, 60),
      handler: handler, handlerOk: handlerOk,
      formAction: form ? (form.getAttribute('action') || '(self)') : '',
      cls: (el.className || '').toString().slice(0, 44),
      listeners: el.getAttribute('data-ux-listeners') || '',
      data: el.dataset ? Object.keys(el.dataset).join(',') : ''
    });
  }
  return rows;
}
"""

SCREENS = [
    ('/', 'dashboard'), ('/workers', 'workers'), ('/attendance', 'attendance'),
    ('/payroll', 'payroll'), ('/payroll/preview', 'payroll-preview'),
    ('/transactions', 'transactions'), ('/closures', 'closures'),
    ('/assignments', 'assignments'), ('/scan', 'scan'),
    ('/settings', 'settings'), ('/profile', 'profile'),
    ('/notifications', 'notifications'), ('/add_worker', 'add-worker'),
    ('/worker/%d', 'worker-profile'), ('/edit_worker/%d', 'edit-worker'),
    ('/worker_attendance/%d', 'worker-attendance'),
    ('/worker/%d/report', 'worker-report'), ('/id_card/%d', 'id-card'),
    ('/payroll/slip/%d', 'payslip'), ('/worker/%d/login/powers', 'login-powers'),
]

# Settings hides most of itself behind tabs; each is opened in turn.
SETTINGS_TABS = ['company', 'sites', 'projects', 'tasks', 'departments',
                 'users', 'salary']

with app.app_context():
    WID = m.Worker.query.order_by(m.Worker.id).first().id

found = defaultdict(list)
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=EXE, args=['--no-sandbox'])
    ctx = br.new_context(viewport={'width': 390, 'height': 844},
                         is_mobile=True, has_touch=True,
                         service_workers='block')
    ctx.add_init_script(WATCH_LISTENERS)
    pg = ctx.new_page()
    pg.goto(B + '/login', wait_until='domcontentloaded')
    pg.wait_for_timeout(800)
    found['login'] = pg.evaluate(PROBE)
    pg.fill('input[name="username"]', 'demo@acme.test')
    pg.fill('input[name="password"]', 'demo12345')
    pg.click('#signin-form button[type="submit"]')
    # wait_for_url rather than a string predicate: Playwright
    # evaluates those with eval(), which the page's
    # Content-Security-Policy refuses.

    pg.wait_for_url(lambda u: '/login' not in u, timeout=20000)

    for path, slug in SCREENS:
        pg.goto(B + (path % WID if '%d' in path else path),
                wait_until='domcontentloaded')
        pg.wait_for_timeout(1600)
        if slug == 'settings':
            for tab in SETTINGS_TABS:
                pg.click('[data-tab="%s"]' % tab)
                pg.wait_for_timeout(500)
                found['settings:' + tab] = pg.evaluate(PROBE)
        else:
            found[slug] = pg.evaluate(PROBE)
        print('  probed %-20s %4d controls'
              % (slug, sum(len(v) for k, v in found.items() if k.startswith(slug))))
    br.close()

with open(os.path.join(OUT, 'controls.json'), 'w') as fh:
    json.dump(found, fh, indent=1)

allrows = [(s, r) for s, rows in found.items() for r in rows]
print('\n%d visible controls across %d screens' % (len(allrows), len(found)))

print('\n--- what each one is attached to ---')
for kind, n in Counter(r['kind'] for s, r in allrows).most_common():
    print('  %-16s %4d' % (kind, n))

dead = [(s, r) for s, r in allrows if r['kind'] == 'NOTHING']
print('\n--- controls attached to nothing: %d ---' % len(dead))
for s, r in dead[:40]:
    print('  %-20s <%s> %-26r %s' % (s, r['tag'], r['text'] or r['aria'], r['cls']))
if not dead:
    print('  none — every control is a link, a submit, a handler or a listener')

broken = [(s, r) for s, r in allrows if r['handlerOk'] is False]
print('\n--- data-act naming a function that is not defined: %d ---' % len(broken))
for s, r in broken[:40]:
    print('  %-20s %-22s %r' % (s, r['handler'], r['text'] or r['aria']))

# Every distinct href, so the next step can ask the server about each.
links = sorted({r['href'] for s, r in allrows
                if r['kind'] == 'link' and r['href'].startswith('/')})
with open(os.path.join(OUT, 'links.txt'), 'w') as fh:
    fh.write('\n'.join(links))
print('\n%d distinct internal links written to out/links.txt' % len(links))

handlers = sorted({r['handler'] for s, r in allrows if r['handler']
                   and r['handler'] != '(inline statement)'})
print('%d distinct actions: %s' % (len(handlers), ', '.join(handlers[:14])))
