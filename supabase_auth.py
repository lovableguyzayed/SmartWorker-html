"""Server-side Supabase Authentication (GoTrue) client.

Supabase is the identity provider: it stores credentials, verifies passwords,
and sends password-recovery / email-confirmation mail. This module talks to the
GoTrue REST API from the Flask backend using stdlib urllib (no extra deps).

The app keeps its own server-rendered pages and Flask-Login session cookie; a
successful Supabase sign-in is mapped to a local ``User`` row (looked up by the
Supabase uid) which is what Flask-Login persists in the session.

Environment:
  SUPABASE_URL          e.g. https://<project>.supabase.co   (already used)
  SUPABASE_ANON_KEY     the project's anon/public API key      (NEW)
  SUPABASE_SERVICE_KEY  service_role key, server-side only     (already used)
"""
import json
import logging
import os
import urllib.error
import urllib.request

SUPABASE_URL = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY') or ''
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY') or ''

_AUTH = '/auth/v1'


def enabled():
    """True when Supabase Auth is configured. When False the app falls back to
    its legacy local password auth (development / preview environments)."""
    return bool(SUPABASE_URL and SUPABASE_ANON_KEY)


def _call(method, path, body=None, bearer=None, apikey=None, timeout=20):
    url = SUPABASE_URL + _AUTH + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        'Content-Type': 'application/json',
        'apikey': apikey or SUPABASE_ANON_KEY,
    }
    if bearer:
        headers['Authorization'] = f'Bearer {bearer}'
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode() or '{}'
            return True, json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode() or '{}')
        except Exception:
            payload = {}
        msg = (payload.get('msg') or payload.get('error_description')
               or payload.get('message') or payload.get('error')
               or f'Authentication service error ({e.code}).')
        logging.warning('Supabase auth %s %s failed: %s', method, path, msg)
        return False, {'error': msg, 'status': e.code}
    except Exception as e:
        logging.warning('Supabase auth %s %s unreachable: %s', method, path, e)
        return False, {'error': 'Could not reach the authentication service. '
                                'Please try again.'}


def sign_up(email, password, full_name=None):
    """Register a new Supabase user. Depending on the project's "Confirm email"
    setting, a session may or may not be returned immediately."""
    body = {'email': email, 'password': password}
    if full_name:
        body['data'] = {'full_name': full_name}
    ok, res = _call('POST', '/signup', body)
    if not ok:
        return {'ok': False, 'error': res.get('error')}
    # With email confirmation ON, GoTrue returns the user but access_token=None.
    user = res.get('user') or res
    session = res if res.get('access_token') else None
    return {
        'ok': True,
        'user': user,
        'session': session,
        'needs_confirmation': session is None,
    }


def sign_in(email, password):
    """Verify credentials via the password grant. Returns the user + tokens."""
    ok, res = _call('POST', '/token?grant_type=password',
                    {'email': email, 'password': password})
    if not ok:
        return {'ok': False, 'error': res.get('error') or 'Invalid email or password.'}
    return {'ok': True, 'user': res.get('user'), 'session': res}


def send_recovery(email, redirect_to=None):
    """Trigger Supabase's password-recovery email."""
    path = '/recover'
    if redirect_to:
        from urllib.parse import quote
        path += '?redirect_to=' + quote(redirect_to, safe='')
    ok, res = _call('POST', path, {'email': email})
    if not ok:
        return {'ok': False, 'error': res.get('error')}
    return {'ok': True}


def update_password(access_token, new_password):
    """Set a new password using a recovery/access token (from the reset link)."""
    ok, res = _call('PUT', '/user', {'password': new_password}, bearer=access_token)
    if not ok:
        return {'ok': False, 'error': res.get('error')}
    return {'ok': True, 'user': res}


def get_user(access_token):
    """Resolve the Supabase user for an access token."""
    ok, res = _call('GET', '/user', bearer=access_token)
    if not ok:
        return {'ok': False, 'error': res.get('error')}
    return {'ok': True, 'user': res}


def admin_create_user(email, password, full_name=None, email_confirm=True):
    """Create a confirmed user via the admin API (service key). Used when an
    account owner invites a staff member so they can sign in immediately."""
    if not SUPABASE_SERVICE_KEY:
        return {'ok': False, 'error': 'Service key not configured.'}
    body = {'email': email, 'password': password, 'email_confirm': email_confirm}
    if full_name:
        body['user_metadata'] = {'full_name': full_name}
    ok, res = _call('POST', '/admin/users', body,
                    bearer=SUPABASE_SERVICE_KEY, apikey=SUPABASE_SERVICE_KEY)
    if not ok:
        return {'ok': False, 'error': res.get('error')}
    return {'ok': True, 'user': res}
