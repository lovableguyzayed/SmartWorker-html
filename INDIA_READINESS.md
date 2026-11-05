# Launching this in India: what is ready, what is not, and what is somebody else's decision

Written while going through the application as an Indian employer and an
Indian labourer would use it, not as its author. Everything below was
checked by running it, not by reading it. Where a figure appears, it was
measured.

The list is in the order I would do it, which is by what breaks a real
person's day — not by what is quickest.

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
worse than either language. Down to 100, and most of what is left is data:
worker names, job titles, clock times.

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
| Aadhaar on screen | Masked to `XXXX XXXX 1234`, never on a payslip, not in any export |
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

## Needs a decision from you — I have not done these

These are not bugs. They are business and legal choices, and getting them
wrong in software is worse than not having them.

### A. PF and ESI — **the one I would settle before launch**

There is no statutory deduction anywhere in the app. For a stone crusher:

* **ESI** applies at **10 or more** employees, for wages up to ₹21,000/month.
  Employee 0.75%, employer 3.25%.
* **EPF** applies at **20 or more** employees. 12% and 12%, on wages up to
  ₹15,000/month.

You have 12 workers on the roster, so **ESI is very likely already due**.
I am not a lawyer and your registration status is something only you know,
but a payroll app for Indian labour that cannot show a PF or ESI line will
be asked for one the first time an inspector or an accountant looks at it.

Three ways to go, cheapest first:

1. **A configurable deduction** — a name, a percentage, a wage ceiling, on
   or off per worker. Represents ESI, EPF, labour welfare cess or anything
   else, and takes about a day. Does not file anything or produce ECR
   files; it puts the right line on the payslip and the right figure in the
   total.
2. **Proper EPF/ESI** — the statutory rates, both halves, the ceilings, and
   an ECR-format export for the EPFO portal. Several days, and worth it
   only if you are actually registered.
3. **Nothing**, deliberately, until an accountant asks. Legitimate for a
   small roster, and a decision rather than an oversight.

Say which and I will build it.

### B. Minimum wage floor

Uttarakhand notifies minimum wages by skill category, revised twice a year.
Nothing in the app knows them, so a daily rate below the floor can be saved
with no warning. A warning is easy; keeping a rate table current is not,
because the notifications change and nobody maintains a machine-readable
feed. My suggestion: one editable floor per category in Settings, and a
warning — not a block — when a rate is saved below it. You keep the
numbers up to date, the app stops you forgetting.

### C. Aadhaar at rest

Masked everywhere it is shown, which is the part that matters most. But the
full twelve digits sit in the database in plain text, and the edit form
sends them back to the browser every time a worker is opened.

Two options: **store only the last four digits** (enough to identify a
person against a document, nothing to leak), or **encrypt the column**.
The first is simpler and safer and loses nothing you actually use. It is
your data, so your call — I have not touched it.

### D. The database will expire

Render's free Postgres is deleted 30 days after creation, plus a 14-day
grace period, **with no backup**. If the live data is on it, there is a
date on which it goes. Check which database `DATABASE_URL` points at. This
is the item most likely to lose real work, and it needs nothing from me.

---

## Watching, not yet acted on

* **A worker who leaves with money owed drops off the dues screen**, which
  lists active workers only. Nobody is inactive today, so nothing is hidden
  right now — but the first time somebody is let go mid-month holding
  arrears, their debt disappears from the one screen that is supposed to
  show it. A filter would fix it; it needs a small decision about whether
  they appear by default.
* **Hindi on the remaining screens.** 100 runs left, mostly data. The ones
  that are not: a few page titles and composite phrases like
  "35 day(s) delayed" that need a placeholder rather than a dictionary
  entry.
* **Slow first load.** Render's free instance sleeps after 15 minutes and
  takes about a minute to wake, which is most of what you feel as
  slowness. Nothing in the code will fix that; a paid instance or a Mumbai
  VPS will.
