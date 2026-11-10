"""Inside the Android app the site's pages must reach the native plugins.

The APK opens the deployed site, and Cordova only lets its own launch page
use the native bridge. So on every real screen window.cordova was missing:
Save PDF / Excel / CSV fell back to a browser download the WebView ignores,
and the Back button never reached the app's own handling.

The fix has three parts that must agree, and this checks each:
  * the app marks its user agent (config.xml AppendUserAgent);
  * the server, seeing the mark, loads cordova.js from the APK and lets the
    Content-Security-Policy allow it - and does neither for a browser;
  * the remote-bridge plugin allows exactly the deployed origin, the same
    one config.xml navigates to and www/index.html loads.

Runs on a throwaway database of its own.
"""
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
os.environ['DATABASE_URL'] = 'sqlite:///' + _db.name
os.environ.setdefault('SESSION_SECRET', 'bridge-test')
os.environ.setdefault('ADMIN_DEFAULT_PASSWORD', 'bridge-test-admin')

from app import app  # noqa: E402
import routes  # noqa: E402,F401

failures = []


def check(label, got, want):
    if got == want:
        print('  PASS %-64s %s' % (label, repr(got)[:30]))
    else:
        failures.append(label)
        print('  FAIL %-64s got=%r want=%r' % (label, got, want))


config = open(os.path.join(ROOT, 'config.xml')).read()
shell = open(os.path.join(ROOT, 'www', 'index.html')).read()
mark = re.search(r'name="AppendUserAgent" value="([^"]+)"', config)
check('config.xml marks the app\'s user agent', bool(mark), True)
APP_UA = 'Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile ' + (mark.group(1) if mark else '')
BROWSER_UA = 'Mozilla/5.0 (Linux; Android 14) Chrome/130 Mobile Safari/537.36'

print('--- the server ---')
with app.test_client() as c:
    page = c.get('/login', headers={'User-Agent': APP_UA})
    html = page.get_data(as_text=True)
    csp = page.headers.get('Content-Security-Policy', '')
    check('in the app, the page loads cordova.js from the APK',
          'src="https://localhost/cordova.js"' in html, True)
    check('and the policy lets scripts come from there',
          bool(re.search(r"script-src [^;]*https://localhost", csp)), True)
    check('cordova.js comes before app.js',
          html.find('localhost/cordova.js') < html.find('js/app.js'), True)

    page = c.get('/login', headers={'User-Agent': BROWSER_UA})
    html = page.get_data(as_text=True)
    csp = page.headers.get('Content-Security-Policy', '')
    check('in a browser, no cordova.js', 'cordova.js' in html, False)
    check('and the policy does not mention localhost', 'localhost' in csp, False)
    check('responses say they depend on the user agent',
          'User-Agent' in page.headers.get('Vary', ''), True)

print('--- one origin, everywhere ---')
bridge = re.search(r'name="RemoteBridgeOrigin" value="([^"]+)"', config)
nav = re.search(r'<allow-navigation href="(https://[^"/]+)/\*"', config)
app_url = re.search(r"var APP_URL = '([^']+)'", shell)
check('the bridge origin is set', bool(bridge), True)
check('the bridge allows the origin the app navigates to',
      bridge and nav and bridge.group(1) == nav.group(1), True)
check('and the one www/index.html opens',
      bridge and app_url and bridge.group(1) == app_url.group(1).rstrip('/'), True)
check('the plugin is in config.xml',
      'spec="./cordova-plugins/smartworker-remote-bridge"' in config, True)

java = open(os.path.join(ROOT, 'cordova-plugins', 'smartworker-remote-bridge',
                         'src', 'android', 'RemoteBridge.java')).read()
check('the plugin matches on origin + "/", so look-alike hosts do not pass',
      'origin + "/"' in java, True)
plugin = open(os.path.join(ROOT, 'cordova-plugins', 'smartworker-remote-bridge',
                           'plugin.xml')).read()
check('the plugin loads at start-up (else it is never asked)',
      '<param name="onload" value="true" />' in plugin, True)

os.unlink(_db.name)
print()
if failures:
    print('FAILED %d: %s' % (len(failures), ', '.join(failures)))
    sys.exit(1)
print('all native-bridge checks passed')
