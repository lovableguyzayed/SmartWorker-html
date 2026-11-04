"""Sending an OTP by text message, or saying plainly that it was not sent.

The app has had OTP sign-in and OTP registration since the beginning, and
neither has ever sent a message. The code was written into the server log
and the screen said "OTP has been sent to 98xxxxxxxx. (Check server logs
in demo mode)" — which is true for the developer and a lie to everybody
else, because the person holding the phone has no server log. A second
employer signing up for this app could not get in at all.

So: one function, `send_otp`, and a provider chosen by the environment.

    SMS_PROVIDER=msg91      MSG91_AUTH_KEY=...  MSG91_SENDER=SMRTWK
                            MSG91_TEMPLATE_ID=...   (optional, for DLT)
    SMS_PROVIDER=twilio     TWILIO_ACCOUNT_SID=...  TWILIO_AUTH_TOKEN=...
                            TWILIO_FROM=+1...
    SMS_PROVIDER unset   →  nothing is sent, and the caller is told so.

Two rules this module keeps, because the whole point of an OTP is that
only one person can read it:

  * the code is NEVER written to the log when a provider is configured. In
    development, with no provider, it is — that is the only way to test
    the flow without a phone, and the caller is told the message did not
    go anywhere so it can say so on screen.
  * nothing here invents a success. A provider that returns an error, times
    out, or is misconfigured comes back as not delivered, with the reason,
    and the screen says the message could not be sent rather than asking
    somebody to wait for a text that is not coming.

India-specific, and the reason `MSG91_TEMPLATE_ID` exists: transactional
SMS to an Indian number has to be sent against a DLT-registered template,
or the operator drops it silently. MSG91's flow API takes the template id
and the variables; its older sendhttp API takes the message text and is
what an unregistered sandbox account can use. Both are supported, the
template one is used when the id is set, and a dropped message is the one
failure this module cannot detect — the provider accepts it and the phone
never rings. Nothing in software can fix that; it is said here so that
whoever debugs it knows where to look.

No new dependency: urllib is in the standard library and this is two HTTP
requests. requests would be nicer and is not worth a wheel on a 512MB
instance.
"""
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

#: How long to wait for the provider before giving up. A person is staring
#: at a spinner on a phone, so this is short on purpose: a slow success is
#: worse than a quick "could not send, try again".
TIMEOUT = 8

log = logging.getLogger(__name__)


def provider() -> str:
    """Which provider is configured, lowercased. '' means none."""
    return (os.environ.get('SMS_PROVIDER') or '').strip().lower()


def is_configured() -> bool:
    """True when a real message can actually be sent."""
    name = provider()
    if name == 'msg91':
        return bool(os.environ.get('MSG91_AUTH_KEY'))
    if name == 'twilio':
        return bool(os.environ.get('TWILIO_ACCOUNT_SID')
                    and os.environ.get('TWILIO_AUTH_TOKEN')
                    and os.environ.get('TWILIO_FROM'))
    return False


def _msg91(mobile: str, text: str, code: str):
    key = os.environ['MSG91_AUTH_KEY']
    sender = (os.environ.get('MSG91_SENDER') or 'SMRTWK')[:6]
    template = (os.environ.get('MSG91_TEMPLATE_ID') or '').strip()

    if template:
        # The DLT-registered route. The variable name has to match the
        # template as registered; ##OTP## is MSG91's own convention and
        # what their sample templates use.
        body = json.dumps({
            'template_id': template,
            'sender': sender,
            'short_url': 0,
            'recipients': [{'mobiles': '91' + mobile, 'OTP': code}],
        }).encode()
        req = urllib.request.Request(
            'https://control.msg91.com/api/v5/flow/', data=body,
            headers={'Content-Type': 'application/json', 'authkey': key})
    else:
        query = urllib.parse.urlencode({
            'authkey': key, 'mobiles': '91' + mobile, 'message': text,
            'sender': sender, 'route': 4, 'country': 91,
        })
        req = urllib.request.Request(
            'https://api.msg91.com/api/sendhttp.php?' + query, method='GET')

    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        raw = res.read(2048).decode('utf-8', 'replace').strip()
    # The v5 API answers JSON with type=success; sendhttp answers a bare
    # request id, and the word "error" when it is unhappy.
    if 'error' in raw.lower() or '"type":"error"' in raw.replace(' ', ''):
        return False, 'msg91 refused it: %s' % raw[:120]
    return True, 'msg91 accepted it'


def _twilio(mobile: str, text: str, code: str):
    sid = os.environ['TWILIO_ACCOUNT_SID']
    token = os.environ['TWILIO_AUTH_TOKEN']
    body = urllib.parse.urlencode({
        'To': '+91' + mobile, 'From': os.environ['TWILIO_FROM'], 'Body': text,
    }).encode()
    url = ('https://api.twilio.com/2010-04-01/Accounts/%s/Messages.json' % sid)
    req = urllib.request.Request(url, data=body)
    import base64
    token_header = base64.b64encode(
        ('%s:%s' % (sid, token)).encode()).decode()
    req.add_header('Authorization', 'Basic ' + token_header)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
        payload = json.loads(res.read(4096).decode('utf-8', 'replace'))
    if payload.get('status') in ('queued', 'sending', 'sent', 'accepted'):
        return True, 'twilio %s' % payload['status']
    return False, 'twilio returned %s' % payload.get('status')


def message_for(code: str, purpose: str) -> str:
    """The text of the message. Short, because an SMS is 160 characters."""
    what = 'sign in' if purpose == 'login' else 'sign up'
    return ('%s is your SmartWorker code to %s. It is valid for 5 minutes. '
            'Do not share it with anyone.' % (code, what))


def send_otp(mobile: str, code: str, purpose: str = 'login'):
    """Send `code` to `mobile`. Returns (delivered, detail).

    `delivered` False is not an exception: the caller decides what to put
    on the screen, and in development there is deliberately no provider.
    `detail` is for the server log and for the caller to show a developer —
    it never contains the code.
    """
    name = provider()
    text = message_for(code, purpose)

    if not name:
        # Development. The code goes to the log because there is nowhere
        # else for it to go, and the caller is told nothing was sent so it
        # does not claim otherwise on screen.
        log.warning('SMS_PROVIDER is not set, so no message was sent. '
                    'The %s code for %s is %s', purpose, mobile, code)
        return False, 'no SMS provider is configured'

    if not is_configured():
        log.error('SMS_PROVIDER=%s but its keys are missing; nothing sent.',
                  name)
        return False, '%s is selected but its keys are not set' % name

    senders = {'msg91': _msg91, 'twilio': _twilio}
    if name not in senders:
        log.error('SMS_PROVIDER=%s is not one this app can use.', name)
        return False, 'unknown SMS provider %r' % name

    try:
        ok, detail = senders[name](mobile, text, code)
    except urllib.error.HTTPError as exc:
        detail = '%s returned HTTP %s' % (name, exc.code)
        ok = False
    except Exception as exc:                        # network, DNS, timeout
        detail = '%s could not be reached: %s' % (name, type(exc).__name__)
        ok = False

    # The code is not in `detail` and must not reach the log either way.
    (log.info if ok else log.error)('OTP to %s via %s: %s',
                                    mobile, name, detail)
    return ok, detail
