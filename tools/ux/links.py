"""Does every link and every form go somewhere that answers?

controls.py establishes that each control is attached to something. This
asks the other half: that what it is attached to exists. A link to a route
that was renamed looks exactly like one that works until it is followed,
and a form whose action no longer resolves fails at the worst moment —
after somebody has typed everything in.

GET links are followed. Forms are not submitted, because submitting them
would write; instead the action is matched against the URL map, which is
what a 404 would have told us anyway.
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..'))
from app import app
import routes  # noqa: F401
import bulk    # noqa: F401
import models as m

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
app.config['WTF_CSRF_ENABLED'] = False

rows = json.load(open(os.path.join(OUT, 'controls.json')))

links, forms = defaultdict(set), defaultdict(set)
for screen, controls in rows.items():
    for c in controls:
        if c['kind'] == 'link' and c['href'].startswith('/'):
            links[c['href']].add(screen)
        if c['formAction'] and c['formAction'] not in ('(self)', ''):
            forms[c['formAction']].add(screen)

# Which rules the application actually has, for matching form actions.
with app.app_context():
    RULES = [(r.rule, sorted(r.methods - {'HEAD', 'OPTIONS'}))
             for r in app.url_map.iter_rules()]


def matches_a_rule(path):
    """A form action resolves if some rule matches it, placeholders and all."""
    clean = path.split('?')[0].rstrip('/') or '/'
    for rule, _methods in RULES:
        pattern = re.sub(r'<[^>]+>', '[^/]+', rule).rstrip('/') or '/'
        if re.fullmatch(pattern, clean):
            return True
    return False


bad_links, bad_forms = [], []
with app.test_client() as c:
    c.post('/login', data={'username': 'demo@acme.test',
                           'password': 'demo12345'}, follow_redirects=True)

    print('--- %d distinct links ---' % len(links))
    for href in sorted(links):
        if href.startswith('/logout'):
            continue                      # following it would end the session
        r = c.get(href, follow_redirects=False)
        ok = r.status_code in (200, 301, 302, 303, 307, 308)
        if not ok:
            bad_links.append((href, r.status_code, sorted(links[href])))
        print('  %-4s %-3d %-44s %s'
              % ('OK' if ok else 'FAIL', r.status_code, href[:44],
                 ','.join(sorted(links[href])[:3])))

print('\n--- %d distinct form actions ---' % len(forms))
for action in sorted(forms):
    ok = matches_a_rule(action)
    if not ok:
        bad_forms.append((action, sorted(forms[action])))
    print('  %-4s %-48s %s'
          % ('OK' if ok else 'FAIL', action[:48], ','.join(sorted(forms[action])[:3])))

print('\n%d links checked, %d failed' % (len(links), len(bad_links)))
for href, code, screens in bad_links:
    print('   FAIL %-44s %s  on %s' % (href, code, ', '.join(screens)))
print('%d form actions checked, %d do not resolve' % (len(forms), len(bad_forms)))
for action, screens in bad_forms:
    print('   FAIL %-44s on %s' % (action, ', '.join(screens)))

sys.exit(1 if (bad_links or bad_forms) else 0)
