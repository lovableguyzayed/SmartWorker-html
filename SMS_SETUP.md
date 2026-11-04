# Turning on the text messages

The app signs people in by mobile number, and lets a new employer sign up
the same way. Both send a six-digit code. **Until one of the providers
below is configured, no message is sent** — the code goes to the server log
and the screen says so in as many words. That is deliberate: it is the only
way to test the flow without a phone, and it is better than telling somebody
to wait for a text that is not coming.

Password sign-in works regardless. Nothing here is needed for that.

## What to set

Set these as environment variables on the server (on Render: the service's
**Environment** page; they are secrets, so they do not go in the repository).

### MSG91 — the usual choice for Indian numbers

```
SMS_PROVIDER=msg91
MSG91_AUTH_KEY=<from MSG91 → Settings → API>
MSG91_SENDER=SMRTWK            # six letters, approved with your DLT header
MSG91_TEMPLATE_ID=<optional>   # see below — you will need this
```

### Twilio — easier to start, dearer per message in India

```
SMS_PROVIDER=twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=<from the Twilio console>
TWILIO_FROM=+1xxxxxxxxxx
```

Nothing else changes. Restart the service and the next code goes by SMS.

## The part that catches everybody: DLT

Transactional SMS to an Indian mobile has to be registered with DLT
(TRAI's Distributed Ledger Technology registry) before any operator will
carry it. Three things get registered, in this order:

1. **Entity** — your business, with its PAN or GST.
2. **Header** — the six-letter sender id, e.g. `SMRTWK`.
3. **Template** — the exact text, with the variable marked:

   ```
   {#var#} is your SmartWorker code to sign in. It is valid for 5 minutes.
   Do not share it with anyone.
   ```

   Register a second one with "sign up" in place of "sign in", because the
   app sends both wordings (`sms.message_for`).

Put the registered template's id in `MSG91_TEMPLATE_ID`. Without it the app
falls back to MSG91's older `sendhttp` route, which works on a sandbox
account and is dropped silently on real traffic.

**"Silently" is the whole problem.** An unregistered message is accepted by
the provider, returns success, and never reaches the phone. Nothing in this
application can detect that. If codes stop arriving and the server log shows
`msg91 accepted it`, the message is being dropped downstream — check the DLT
template, not the code.

## Checking it works

```
SMS_PROVIDER=msg91 MSG91_AUTH_KEY=... python - <<'EOF'
import sms
print(sms.send_otp('98XXXXXXXX', '123456', 'login'))
EOF
```

It prints `(True, 'msg91 accepted it')` or the reason it failed. The code
is never written to the log once a provider is configured — only the
outcome.

## What the app does on its own

* **One code per minute per session.** A held-down Resend button cannot run
  up a bill (`OTP_RESEND_SECONDS`).
* **Five wrong guesses and the code is dead.** A six-digit code has a
  million values, which is plenty against five tries and nothing at all
  against unlimited ones — a script would walk the whole range inside the
  five minutes the code is valid (`OTP_MAX_ATTEMPTS`).
* **Codes come from `secrets`**, not `random`. The one is a CSPRNG; the
  other is the Mersenne Twister, whose next output is predictable from
  enough previous ones.
* **The code is never in an HTTP response.** It lives in the session, and
  `tests/test_otp.py` fails if it ever appears in the JSON.
* **Codes expire in five minutes** and are compared with
  `hmac.compare_digest`, so the time a wrong guess takes says nothing about
  how many of its digits were right.
