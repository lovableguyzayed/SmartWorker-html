"""The Content-Security-Policy is real, and the application obeys it.

A policy is only worth the directive that does the work. `script-src`
without `'unsafe-inline'` is what stops an injected <script>, or an
onclick= an attacker gets into a page, from running — and the moment one
inline handler is added back, the easy fix is to loosen the policy and the
protection is gone with it. So this checks both halves:

  * the header is sent, and script-src allows neither 'unsafe-inline' nor
    'unsafe-eval';
  * no template contains an inline handler for it to have to allow.

The second half is the one that rots. Ninety handlers were moved out to
get here, into the declarative data-act form that static/js/actions.js
dispatches; writing a new onclick= is the natural thing to do and it will
not work, so the failure needs to say why.

The browser half — that no screen actually trips the policy — lives in
test_no_script_errors.py, which listens for the console error a violation
raises.
"""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')

from app import app
import routes  # noqa: F401  (registers the routes this asks for)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-52s %r%s' % ('OK' if ok else 'FAIL', label, got,
                                 '' if ok else '  (want %r)' % (want,)))


client = app.test_client()
response = client.get('/login')
csp = response.headers.get('Content-Security-Policy', '')
directives = dict(
    (part.strip().split(' ', 1) + [''])[:2]
    for part in csp.split(';') if part.strip())

print('--- the header is sent, and says what it should ---')
check('Content-Security-Policy is present', bool(csp), True)
script_src = directives.get('script-src', '')
check("script-src forbids 'unsafe-inline'", "'unsafe-inline'" in script_src, False)
check("script-src forbids 'unsafe-eval'", "'unsafe-eval'" in script_src, False)
check("script-src is limited to 'self' plus a nonce",
      bool(re.fullmatch(r"'self' 'nonce-[\w-]+'", script_src.strip())), True)
for directive, expected in (('default-src', "'self'"),
                            ('object-src', "'none'"),
                            ('base-uri', "'self'"),
                            ('form-action', "'self'"),
                            ('frame-ancestors', "'self'")):
    check('%-16s is %s' % (directive, expected),
          directives.get(directive, '').strip(), expected)

print('\n--- the nonce is per-request, and matches the page ---')
nonce = re.search(r"'nonce-([\w-]+)'", csp)
check('the header carries a nonce', bool(nonce), True)
body = response.get_data(as_text=True)
in_page = re.findall(r'<script[^>]*nonce="([^"]+)"', body)
check('every inline block on the page carries it',
      set(in_page) == {nonce.group(1)} if (nonce and in_page) else False, True)
second = client.get('/login')
other = re.search(r"'nonce-([\w-]+)'",
                  second.headers.get('Content-Security-Policy', ''))
check('a second request gets a different one',
      bool(other) and other.group(1) != nonce.group(1), True)

print('\n--- the other headers ---')
check('X-Content-Type-Options',
      response.headers.get('X-Content-Type-Options'), 'nosniff')
check('X-Frame-Options', response.headers.get('X-Frame-Options'), 'SAMEORIGIN')
check('Referrer-Policy', response.headers.get('Referrer-Policy'), 'same-origin')
check('Permissions-Policy is set',
      bool(response.headers.get('Permissions-Policy')), True)
# HSTS only where TLS is actually terminated; announcing it over plain http
# would lock a developer out of their own machine.
check('no HSTS over plain http',
      'Strict-Transport-Security' in response.headers, False)
with app.test_request_context('/', base_url='https://example.test'):
    secure = client.get('/login', base_url='https://example.test')
check('HSTS over https',
      'max-age' in secure.headers.get('Strict-Transport-Security', ''), True)

print('\n--- nothing in the application needs what the policy forbids ---')
inline = []
for path in sorted(glob.glob(os.path.join(ROOT, 'templates', '*.html'))):
    text = open(path).read()
    for m in re.finditer(r'\son(click|change|submit|load|input|focus|blur)\s*=',
                         text):
        inline.append((os.path.basename(path), m.group(0).strip()))
check('inline event handlers in templates', inline, [])

bare = []
for path in sorted(glob.glob(os.path.join(ROOT, 'templates', '*.html'))):
    text = open(path).read()
    for m in re.finditer(r'<script(?![^>]*\bsrc=)([^>]*)>', text):
        if 'nonce=' not in m.group(1):
            bare.append((os.path.basename(path), m.group(0)[:50]))
check('inline <script> blocks without a nonce', bare, [])

evals = []
for path in (sorted(glob.glob(os.path.join(ROOT, 'static', 'js', '*.js')))
             + sorted(glob.glob(os.path.join(ROOT, 'templates', '*.html')))):
    text = open(path).read()
    for m in re.finditer(r'(?<![\w.])(eval\(|new Function\()', text):
        # actions.js explains in a comment why it does neither.
        line = text[:m.start()].count('\n') + 1
        if os.path.basename(path) == 'actions.js':
            continue
        evals.append((os.path.basename(path), line, m.group(1)))
check('eval / new Function in first-party code', evals, [])

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('All Content-Security-Policy checks passed.')
