# Launching this in India: what is ready, what is not, and what is somebody else's decision

Written while going through the application as an Indian employer and an
Indian labourer would use it, not as its author. Everything below was
checked by running it, not by reading it. Where a figure appears, it was
measured.

The list is in the order I would do it, which is by what breaks a real
person's day — not by what is quickest.

**Where it stands now:** 61 test files, all passing. No English left on
any Hindi screen. PF/ESI, a minimum wage floor, Aadhaar masked at rest and
a backup you can take yourself are all built and merged — the statutory
rules and the wage floor sit silent until you fill them in.

**Three things are still yours and I cannot do them from here:** check
which database `DATABASE_URL` points at before the free one expires, make
the repository private, and change the two passwords that are in its
history. They are at the end, under *Still needs a decision from you*.

---

## Already fixed, in this pass

### 1. A mobile number written the way Indians write it — **was breaking sign-in**

The number is how people get in: it is what an OTP goes to and what a
worker's own login is called. It was handled by "keep the digits and
stop":

```
+91 98765 43210  ->  919876543210   ->  "No account found with this mobile number."
09876543210      ->  09876543210    ->  "No account found with this mobile number."
98765 43210      ->  9876543210     ->  found
```

Most people write their own number with +91 or a leading zero. They were
told their account did not exist. This is the single worst thing I found,
because it hits a new user on their first screen and looks like the app
not knowing them.

Also: it accepted a Dehradun landline (`0135 2345678`), a number starting
with 5 which cannot exist in India, and `1234567890`. Now: ten digits
beginning 6, 7, 8 or 9 — the whole range, 6 included, because a check
written for "starts with 9" locks out every Jio number.

Rows written in the old shape are still found, so fixing the input did not
break sign-in for the people it was meant to help.

### 2. The OTP was never sent to anybody

Six digits were generated, written to the **server log**, and the screen
said "OTP has been sent to 98xxxxxxxx. (Check server logs in demo mode)" —
true for whoever runs the server, a lie to the person holding the phone.
A second employer signing up could not get in at all.

Now sent through MSG91 or Twilio (`SMS_PROVIDER`), with `SMS_SETUP.md`
covering the **DLT registration** that Indian transactional SMS needs —
including the failure no software can detect, where an unregistered
template is accepted by the provider and dropped by the operator.

Plus three holes in the same path: the guesses were not counted (five now
spend the code), the codes came from `random` rather than `secrets`, and
the comparison returned early on the first wrong digit.

### 3. Paise in payments

Rounding only governed the monthly salary. An hourly worker at ₹118.75/hour
came out at **₹22,712.50** and a daily worker on ₹512.33 at **₹9,976.66** —
not amounts anybody hands over at a crusher gate. Now every computed figure
is rounded by the policy's own rule, in all four pay structures, while
amounts somebody **typed in** are left exactly as typed.

### 4. Hindi screens showing English

148 runs of Latin text on the Hindi screens; **19 of them already had a
Hindi translation that the template never asked for** — the whole salary
policy, every dropdown on Settings, every "Policy in force" row. Two
sentences were half-translated ("Generate payroll for नवंबर"), which reads
worse than either language.

This got to zero in a later pass — see **Hindi: finished** at the end,
which also explains why the honest before-figure is smaller than the one
this section quotes.

### 5. The live account's passwords were in a public repository

`tools/seed_uttaranchal.py` carried the admin's and the mukadam's passwords
in plain text. They come from the environment now.

**This is not fixed by that change.** Git keeps every version and the
repository is public, so those passwords are still readable in the history.
**They have to be changed in the app.** Nothing I can do from here does
that.

---

## Checked, and found correct

Worth saying, because these are the usual places an app written elsewhere
gets India wrong:

| Thing | State |
|---|---|
| Rupee grouping | `₹22,69,214` — lakh/crore, not `2,269,214` |
| Dates | `07 Aug 2026`, month names in the interface language. Never `08/07/2026`, which half the world reads as 8 July |
| Currency symbol | One `money` filter, 73 sites, no hardcoded `Rs.` |
| Aadhaar on screen | Masked to `XXXX XXXX 1234`, never on a payslip, not in any export — and since round three, only those four digits are stored at all |
| Hindi numerals | Latin digits kept, which is what Indian users expect for money |
| Night shift | 20:00–08:00 no longer counted as twelve hours late |
| Weekly off | An unmarked day is paid by default, so Sundays nobody marks cost nothing |
| Festival closures | The closure calendar covers Holi, Diwali and a plant shutdown, with or without pay |

---

## Round two: measured, then fixed

### 6. A cold start was 1,240 KB over 22 requests

Measured through a browser against a real server, counting what the
network carries. On 2G that is **254 seconds of transfer** before Render's
cold start even begins.

The icon fonts had been subsetted long ago — 147 KB down to 9.6 KB for the
111 icons this app draws. **The stylesheet never was.** It still named all
2,452 icons in 102 KB, and 2,336 of those names pointed at glyphs that had
already been removed from the font. Every first-time visitor downloaded
it.

```
all.min.css                 99.6 KB  ->  19.1 KB
fa-regular + fa-brands      375 KB in the repo  ->  deleted (never drawn)
QR scanner library          loaded in <head>    ->  loaded on demand
```

Cold start is 1,159 KB now. `tools/subset_icons.py` cuts the stylesheet as
well as the fonts, and keeps the complete originals in
`tools/fontawesome-full/` so it can be re-run after adding an icon without
narrowing a little more each time.

**Still open, and deliberately not done:** the QR library is 367 KB — a
third of what is left, and 73 seconds of 2G on its own. Modern Android
Chrome has a built-in `BarcodeDetector` that would make it unnecessary for
most phones. **This test environment does not have that API, so I cannot
verify it works**, and the scanner is a core feature — putting an untested
second camera path into it would be guessing. It needs trying on a real
Android phone.

### 7. The offline queue could sit full against a good connection

The queue drained on the `online` event and on startup. That covers the
signal returning while somebody is watching the screen, and opening the
app the next morning. It did not cover the way this app is actually used:

> mark attendance at the gate where there are no bars → pocket the phone →
> walk up to the office where there are → open the app again

The WebView was asleep for that walk, and does not reliably raise `online`
for a connection that came back while it slept. A whole shift's attendance
could wait in a phone for no reason. It now drains on `resume` and on
`visibilitychange` too.

Proven both ways: without the listener the queue stays full and three
checks fail; with it the row lands exactly once.

### 8. A debt disappeared when the man stopped coming in

The dues screen listed workers with status `active`. A labourer let go
mid-month holding three months of arrears is marked inactive — correctly —
and his debt vanished from the one screen that exists to show debts.

Everybody who has left is now walked too, and the ones who are square are
dropped. A departed worker who is still owed is labelled **"Has left ·
still owed"**, so nobody rings a man who left in August to ask why he is
not at the gate.

### 9. Two workers could be given one phone number, in silence

That number is how you ring a man, and it is the username of his own
login — so only the first of the two can ever have one, and that surfaces
much later, on a different screen.

It warns now and does **not** refuse: a family on a site shares one phone,
and blocking it would make an honest employer invent a fake number.

### What was checked here and held

An 11.8 MB photo off a phone camera is accepted and compressed in under a
second. A text file renamed `.jpg` is refused. The worker ID is generated
rather than typed, so it cannot collide. The offline queue sends exactly
once, never twice.

One rough edge worth knowing: when the session expires while the app sits
in a pocket, the next save returns Flask's own `400 Bad Request — The CSRF
token is missing` page, in English, with no way back to the login screen.
It is not wrong, but it is not an answer either. Small, and not yet fixed.

---

## Round three: the four you handed back to me

These four had been sitting in this document as *your* decisions. You said
to build what I had recommended, so I did. Each is off or silent until you
use it, and each has its own test file.

### A. PF and ESI — built, and switched off until you switch it on

The whole difficulty is that the figure attached to each one behaves in two
opposite ways, and getting them the wrong way round is a real amount of
somebody's money:

| | What the figure means | A man on ₹30,000 |
|---|---|---|
| **ESI** 0.75% / 3.25%, ₹21,000 | an **eligibility line** — above it he is out of the scheme | nothing is deducted |
| **EPF** 12% / 12%, ₹15,000 | a **cap on the base** | 12% of ₹15,000 = **₹1,800** |

Treat ESI's figure as a cap and that man loses ₹157 he does not owe. Treat
EPF's as an eligibility line and he keeps ₹1,800 he does. Both are checked
from both sides of each figure.

Nothing is hardcoded — the rates change by notification, so you type in
your own, and **every rule is off until you switch it on**. An employer who
is not registered must not have money taken off his men's wages because an
application assumed he was.

The employer's share is recorded as your cost and never deducted from the
worker. Each line is named on the payslip with its percentage, because
"Deductions ₹1,800" with no name is a figure a man cannot check, and it is
the number he will be asked about at home.

Settings → Salary → Statutory deductions. `tests/test_statutory.py`, 23
checks.

### B. Minimum wage floor — a warning, never a block

Settings → Salary → Minimum wage. Your figures, against the position names
you already use ("Helper", "Operator"), plus one for everybody. A floor set
for a position beats the general one. Blank checks nothing.

It **warns and saves anyway**, and the third reason is the real one:

1. a floor the app enforced would be a floor from the wrong year the moment
   a notification lapsed, and you would be locked out of saving a correct
   wage by a stale number;
2. apprentices, part days, piece work and a man kept on his old rate
   pending arrears are all real, and none of them are a form error;
3. refused, an employer types in a figure he does not mean in order to get
   past the screen — and then the rate on record is a lie. A warning you
   read and override leaves the truth in the database.

A monthly man is judged on the monthly figure, never the daily one. An
hourly man is judged on the hours in *your* working day (eight unless you
say otherwise — a crusher on a ten-hour shift should not be measured
against somebody else's day). Piece rate is not judged at all.

`tests/test_min_wage.py`, 29 checks.

### C. Aadhaar — only the last four digits are kept now

A full Aadhaar is not needed to pay anybody: a bank account and IFSC, or a
UPI id, is what moves the money. It was held only so you could recognise
which card a man showed you, and four digits do that.

**Your existing numbers have not been touched.** Rows already holding
twelve digits are read correctly and will be replaced with four the next
time that worker is saved. Destroying data you entered is not mine to do —
if you want the old ones cleared now, say so.

One thing worth knowing, because it is the kind of change that quietly
eats data: once the form stops showing the full number, the Aadhaar box is
**empty**. An empty box that meant "delete" would wipe a man's Aadhaar
every time you opened him to change his wage. So an empty box leaves what
is on file alone, and removing one is a checkbox you tick on purpose.

`tests/test_aadhaar.py`, 24 checks.

### D. A backup, in your own hands

Settings → Company → **Download a backup**. One zip, one spreadsheet per
kind of record, a README inside in Hindi and English. Measured on the demo
data: 20 CSVs, 15 KB.

Not in it, and verified absent: password hashes, Supabase ids,
photographs and QR images (they would turn 15 KB into tens of megabytes
over 2G), and all but the last four digits of an Aadhaar.

It is one workspace's data and only that. `users` and `accounts` sit
outside the app's automatic tenant filter on purpose — the login layer
scopes them itself — and a backup is exactly where that exception would
quietly become one employer downloading another employer's workers and
their bank accounts. Every query is scoped by hand, and the test proves
it: written the careless way, another workspace's row and another
employer's login end up in the file.

A supervisor cannot take one. He can mark attendance; he cannot walk out
with the wage book.

`tests/test_backup.py`, 32 checks.

---

## Still needs a decision from you

### The database will expire

Render's free Postgres is deleted 30 days after creation, plus a 14-day
grace period, **with no backup**. If the live data is on it, there is a
date on which it goes. Check which database `DATABASE_URL` points at.

The backup button above means you can now protect yourself whatever you
decide — take one every month. But where this thing is hosted is your
call, not mine, and it is still the item most likely to lose real work.

### The repository is public, and the old passwords are in its history

Two things I have flagged before and cannot do for you:

* **Make the repository private.** It is public today.
* **Change the passwords for Javed and imran.** They were committed once.
  Removing them from the current files, which is done, does not remove
  them from git history — and a child's photograph is in there too.

Rotating a password takes a minute and makes the leaked one worthless.
Until then it is a live credential sitting in a public place.

### The QR scanner's fallback — I recommend against it

There is a faster camera API (`BarcodeDetector`) some phones have. I am
**not** changing the scanner to use it, because there is no such API in
this environment to test against, and the scanner is how attendance gets
marked at the gate. An untested change to a core path is worse than a
slightly slower one that works.

---

## Watching, not yet acted on

* **Slow first load.** Render's free instance sleeps after 15 minutes and
  takes about a minute to wake, which is most of what you feel as
  slowness. Nothing in the code will fix that; a paid instance or a Mumbai
  VPS will.
* **Notifications written before they were reworked.** Six rows in the demo
  database are in the old shape. They now read correctly in Hindi, by
  pattern, because your live database may hold the same ones — but they are
  stale rows, not something the app writes any more.

---

## Hindi: finished, and the measuring tool was lying first

Measured with `tools/ux/hindi_gaps.py`, which renders every screen in
Hindi and reports runs of Latin text. The same tool against the old code
and the new:

| | English runs on Hindi screens |
|---|---|
| Before | **65** across 13 screens |
| After | **0** |

It first reported 92. Twenty-seven of those were the tool's own false
positives — it read the arrow entity `&rarr;` as the word "rarr", did not
know PNG, ESI and EPF were acronyms that stay, and did not treat staff
names, site addresses or email addresses as data the way it already
treated worker names. Fixing those is honest measurement, not translation,
which is why the before-figure here is 65 and not 92.

What was genuinely in English: keywords the app had written itself and
printed raw (`permanent`, `active`, `daily`, `pending`, `not marked`) in
the middle of Hindi on the worker list and profile; composites where the
English is glued to a figure in the markup (`₹800/day`, `20 min`,
`36 day(s) delayed`, `Gross ₹1,33,000`); four paragraphs never wrapped for
translation at all; and one label that *could never* have been translated,
because it is assembled in the template — so the dictionary entry somebody
wrote for it was dead the day it was written.

Two real bugs surfaced on the way:

* a worker called **Augustine** appeared as "अगस्तine" — his own name,
  half rewritten, on the screen his employer reads out to him. The month
  swapper was matching substrings instead of whole words.
* the one word that says what actually happened — present, absent, late —
  came through in English inside otherwise-Hindi notifications, because a
  pattern can reorder a sentence but cannot look a captured group up in
  the dictionary.
