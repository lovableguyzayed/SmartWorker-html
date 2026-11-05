"""What the app says when something goes wrong, in its own voice.

There were no error handlers at all. A phone that had been in a pocket
came back to Flask's:

    400 Bad Request
    The CSRF token is missing.

White, English, no bottom bar, nothing to press. For the mukadam holding
the phone at the gate that is the application being broken, whatever the
words say — and it is not even his fault. The login had survived (that is
a separate remember cookie); what died was the session cookie holding the
CSRF token, because Android reclaimed the WebView for memory while the
app sat unused.

Two things, and the first matters more than the second:

  * the session cookie is permanent now, thirty days, so the token usually
    outlives the app being closed and the error stops happening at all.
    Checked here, because a config line is easy to write and easy to have
    no effect.

  * and when it does happen — thirty-one days away, a cleared browser, a
    genuinely bad request — the app answers: JSON to a fetch, because the
    screens paint their own notices from it, and a redirect with a message
    to anything else. Same for a mistyped address, an upload over the
    limit, and a crash.

Every message is checked for a Hindi translation too. An error page is
exactly where somebody is already confused, and the worst possible moment
to switch languages on them.

Run from the project root:  python3 tests/test_error_pages.py
"""
import json
import os
import sys
from datetime import timedelta

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from app import app
import i18n
import routes  # noqa: F401  (registers the handlers)
import bulk    # noqa: F401

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-58s %r' % ('OK' if ok else 'FAIL', label, got))


# CSRF stays ON for this file. Switching it off would remove the very
# thing being tested.
app.config['TESTING'] = True

# ---------------------------------------------------------------------------
print('--- the session outlives the app being closed ---')

check('the cookie is given thirty days',
      app.config['PERMANENT_SESSION_LIFETIME'], timedelta(days=30))

with app.test_client() as client:
    client.get('/login')
    cookie = next((c for c in client.cookie_jar
                   if c.name == 'session'), None) \
        if hasattr(client, 'cookie_jar') else None
    # Werkzeug moved the jar around between versions; the config check
    # above is the one that cannot be fooled, and this one is skipped
    # rather than guessed at when the jar is not reachable.
    if cookie is not None:
        check('and the cookie really carries an expiry',
              bool(cookie.expires), True)
    else:
        print('        (cookie jar not reachable in this Werkzeug; '
              'the config check above stands)')

# ---------------------------------------------------------------------------
print('\n--- a save after the session went ---')

with app.test_client() as client:
    res = client.post('/transactions/save',
                      data={'worker_id': '1', 'amount': '100'})
    check('a form post is not left on a white page', res.status_code, 302)
    check('it goes somewhere the app owns',
          (res.headers.get('Location') or '').startswith(
              ('/dashboard', '/login', '/transactions')), True)

with app.test_client() as client:
    res = client.post('/api/worker_transaction',
                      data=json.dumps({'worker_id': 1, 'amount': '100'}),
                      content_type='application/json')
    body = res.get_json() or {}
    check('a fetch gets JSON, not HTML', res.status_code, 400)
    check('and is told it was the sleep, not a refusal',
          body.get('expired'), True)
    check('with something a screen can show',
          bool(body.get('message')), True)
    check('and it does not claim success', body.get('success'), False)

# ---------------------------------------------------------------------------
print('\n--- an address that is not a screen ---')

with app.test_client() as client:
    res = client.get('/this-is-not-a-screen')
    body = res.get_data(as_text=True)
    # The STATUS stays 404 and only the page changes. Redirecting instead
    # broke /__setup/<token>, which answers 404 on purpose so a wrong
    # guess cannot tell a stranger the route is there — and a redirect
    # whose destination depends on being signed in announces, to anybody
    # who asks for a junk URL, whether somebody is signed in.
    check('a browser gets a 404, not a redirect', res.status_code, 404)
    check('on a page with a way out of it', 'Back to the app' in body, True)
    check('and not on Flask\'s own', 'Not Found' in body, False)

with app.test_client() as client:
    res = client.get('/__setup/thisisnotthetoken0000')
    check('the hidden setup route is still hidden', res.status_code, 404)
with app.test_client() as client:
    res = client.get('/api/not-a-thing', headers={'Accept': 'application/json'})
    check('a fetch gets JSON', res.status_code, 404)
    check('and it is JSON, not a page',
          (res.get_json() or {}).get('success'), False)

# ---------------------------------------------------------------------------
print('\n--- and every one of them speaks Hindi ---')

# The flashes and the JSON messages, which go through the flash table.
MESSAGES = [
    'The app was asleep too long and that did not save. '
    'Please try it once more.',
    'The app was asleep too long. Please try that once more.',
    'That is not something this app has.',
    'That file is too big to upload.',
    'Something went wrong at our end. Please try again.',
]
# And the wording on the page itself, which goes through the ordinary one.
PAGE_WORDS = [
    'That screen does not exist.',
    'The address may be mistyped, or what it pointed at has been removed.',
    'That photo is too big to upload.',
    'Take it again at a lower size, or choose a smaller file.',
    'Something went wrong at our end.',
    'Nothing was saved. Please try again in a moment.',
    'Back to the app',
]
table = i18n.FLASH_MESSAGES.get('hi', {})
plain = {m: i18n.translate(m, 'hi') for m in PAGE_WORDS}
check('every word on the error page has Hindi',
      [m for m, hi in plain.items() if hi == m], [])
check('none of the error messages is left in English',
      [m for m in MESSAGES if m not in table], [])
check('and none of the translations is a copy of the English',
      [m for m in MESSAGES if table.get(m) == m], [])

# The handlers must raise exactly the strings above, or the table is
# translating something nobody says.
source = open(os.path.join(ROOT, 'routes.py')).read()
tail = source[source.index('def _wants_json():'):]


def flat(text):
    """Quotes out, whitespace collapsed.

    The handlers write these as implicitly concatenated string literals
    across two lines, so the source reads  '...too long. ' 'Please try...'
    — dropping the quotes leaves two spaces where the message has one.
    Comparing without collapsing reported every multi-line message as
    missing, which is the test being wrong about the source rather than
    the source being wrong.
    """
    return ' '.join(text.replace(chr(39), ' ').split())


haystack = flat(tail)
missing = [m for m in MESSAGES if flat(m) not in haystack]
check('and every one of them is really raised by a handler', missing, [])

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('   %s: got %r, want %r' % (label, got, want))
    sys.exit(1)
print('Nothing lands on a white English page any more.')
