# SmartWorker — UI and UX review

Branch `claude/worker-management-app-e8mkqg`.

**Status.** The review below was findings only. Four of them — A, B, C and D
in the table at the end — were then approved and are done; each is marked
FIXED in place, with the measurement that proves it. The rest are still
proposals waiting on a decision, in keeping with the standing instruction
not to replace or modify the UI before approval.

This is a different question from the Phase 7 audit. That one asked whether
anything was broken — clipped text, content off the screen, overlapping bars,
tap targets under 44px — and the answer is now zero on all counts across 30
screen × language combinations. This one asks whether the twenty-four screens
look and behave like one product, and whether the person holding the phone —
often outdoors, often in sunlight, sometimes reading slowly, sometimes reading
only Devanagari — can actually use it.

## How it was measured

Every figure below came from the running application on a 390 × 844 phone
viewport, both languages, not from reading the source:

- **Design tokens** — the computed style of every visible element on 18
  screens, counted. A design system is only as real as the values that reach
  the screen. `tools/ux/design_tokens.py`
- **Contrast** — measured against the pixels, not the stylesheet. Walking
  up the DOM for a background colour gets the gradient header wrong, so each
  run of text is cropped out of a real screenshot and the most common colour
  in its own box is taken as what is behind it. The page is scrolled a screen
  at a time rather than photographed full-page, because Chromium reflows the
  layout to take a full-page shot and the coordinates stop matching the
  pixels. 374 runs where glyphs or a gradient left no clear majority colour
  are reported as unmeasurable rather than guessed at. `tools/ux/contrast.py`
- **Legibility** — the size of all 1,361 runs of visible text, in both
  languages. `tools/ux/legibility.py`
- **Wordless controls** — every control showing no text, and whether it
  carries a name for a screen reader or a long press. `tools/ux/wordless.py`
- **The screens themselves** — the 48 screenshots of the full tour, read by
  eye.

The four scripts live in `tools/ux/`, with a README; start the server and
run them and the figures below come back.

---

## The verdict

The application works and is, in places, well designed. The screens built
most recently — a worker's own home, a mukadam's roll — are calm, have one
clear number on them, one accent colour and one obvious action. They are the
best thing in the product and they are the model the rest should follow.

The older administrative screens were not built to the same idea, and the
measurements say so plainly: **46 distinct font size and weight combinations,
35 text colours, 42 surface fills, 14 corner radii, 15 card paddings and 52
button shapes.** That is not a design system, it is an accumulation. A person
moving from the dashboard to the workers list to attendance is not moving
through one product; the type gets smaller, the greys change, the corners
change, and the colour stops meaning anything.

Three findings are serious enough to act on regardless of taste. Money is
printed four different ways and never grouped. A quarter of the measurable
text fails the contrast floor. And the attendance screen — the screen this
application exists for — lists the same twelve workers **twice**, three
thousand pixels apart, with the same four status buttons on both, which is
most of why it runs to seven phone screens.

---

## Findings, worst first

### 1. Money is printed four different ways, and never grouped — FIXED

This is a wages application, and the wage is the thing everyone looks at.
Across the templates there are **73 places that print a rupee amount: 16 use
`%.0f`, 46 use `%.2f`, one uses `%.4f`, and 10 print the raw Python float
with no format at all.** Nothing anywhere groups the digits.

What that produces, all of it currently on screen:

| Screen | Shown | Should read |
|---|---|---|
| Payroll totals | `₹195438` | `₹1,95,438` |
| Workers list | `₹38000.0/month` | `₹38,000/month` |
| Workers list | `₹800.0/day` | `₹800/day` |
| Payroll row | `₹38000.00` | `₹38,000.00` |
| Preview | `₹-1100.00` | `−₹1,100.00` |

`₹38000.0` is not a rounding choice, it is `str(float)` reaching the page.
And `₹195438` asks a foreman to count six digits by eye to know whether it is
nineteen lakh or one lakh ninety-five thousand. India groups by lakh —
`₹1,95,438`, not `₹195,438`.

**Proposal.** One `money` Jinja filter, used at all 73 sites: Indian
grouping, two decimals only where paise exist, the minus sign before the
symbol. A dozen lines of our own alongside the existing filters in
`routes.py` — Babel would do it with `format_currency(x, 'INR',
locale='en_IN')`, but it is not currently a dependency and this does not
warrant adding one. One place to change it, and a test that no template
prints a bare `₹{{ value }}` again.

The one deliberate exception is the worker report's "Daily salary (exact)"
at four decimals, which exists to show how a monthly wage divides; that
should stay as it is.

**Done.** `money.py` does it once — Indian grouping, paise only where there
are paise, a real minus sign before the symbol, ROUND_HALF_UP on Decimal so
a figure cannot move by a paisa on its way to the screen. The printable
documents use the two-place form so their columns still line up, and the day
view gets the same rupee from `toLocaleString('en-IN')` rather than a second
convention. `tests/test_money.py` checks the formatting and then checks the
templates, with the guard pointed at the four shapes that were really in
these files.

Worth recording: a Jinja filter binds tighter than `or`, so
`worker.daily_rate or 0|money2` means `worker.daily_rate or (0|money2)` and
would have gone on printing the raw float for every worker who has a rate —
the exact bug being removed. Every expression carrying an operator is now
bracketed.

### 2. A quarter of the measurable text is below the contrast floor — FIXED

**242 of the 965 runs that could be measured fall below WCAG AA (25.1%).**
Not a theoretical concern: this phone is used on a building site, in sun,
often behind a screen protector with cement dust on it.

It is not spread thin across the product; a handful of colours account for
most of it:

| Ratio | Where | Runs |
|---|---|---|
| 2.54:1 | `text-gray-400` body text on white — payroll notes, worker meta lines | 73 |
| 2.43:1 | the same grey on the `gray-50` page background | 52 |
| 3.98:1 | `text-accent` — every **Assign**, **View All**, **Transfer** link | 33 |
| 3.15–3.30:1 | `text-green-600`/`green-500` — every wage on the workers list | 23 |
| 2.28:1 | white on `bg-green-500` — the **Mark Paid** button | 10 |
| 2.04:1 | `ep-extra` — the site and project name on an attendance row | 4 |
| 2.28–4.47:1 | white on the dashboard's four action tiles | 4 |

Those seven account for 199 of the 242.

Two things stand out. The **Mark Paid** button at 2.28:1 is the control that
tells a worker he has been paid. And the sentence on the mukadam's screen
that defines what he is allowed to do — *"You can mark present and late.
Absences, leave and any correction are the Administrator's to make."* — is
the faintest text on that screen.

**Proposal.** Three substitutions, no redesign: retire `gray-400` as a text
colour in favour of `gray-500` on white and `gray-600` on tinted backgrounds;
darken the accent from `#007bff` to about `#0062cc` for text and small
controls, leaving the brand blue for large fills; move the success green used
for text from `green-500`/`green-600` to `green-700`. That clears the great
majority of the 242 and changes the look of the product very little.

**Done, and the figure above was understated.** Two corrections came out of
doing it.

The first: the `large()` helper was more generous than WCAG, letting any
18.66px text through regardless of weight. The standard is 18pt regular
(24px) or 14pt bold (18.66px bold). Corrected, the baseline was **259, not
242** — 26.8%.

The second is worse, and the review did not know it had the problem. **A
gradient paints no `background-color`**, so the sweep walked up the DOM,
found nothing, and filed 374 runs as unmeasurable without looking at them.
Four of those were the dashboard's stat tiles — the biggest numbers on the
home screen — carrying white text at **2.27:1 to 3.43:1**. The tool now
scores text on a gradient against the worst point of the fill instead of
giving up, which is the only reason they were found.

**Result: 259 → 0 on solid fills.** `gray-400` and its hardcoded twin
`#9ca3af` go to `gray-500`; the accent moves to `#0062cc` as ink, fill,
border, focus ring and gradient stop; green, amber, orange, yellow and red
each move one step for text; the Mark Paid button goes from 2.28:1 to
5.02:1; the four stat-tile gradients move down a step or two.

A trap for next time: **the purged Tailwind build carries almost none of the
700-weight fills or gradient stops**, so writing `bg-green-700` in a template
does nothing at all, silently. Every fill this needed is written out in
`custom.css` with the ratio it buys, the way `.has-bottom-nav` already was.

What is left is 29 runs, none on a solid fill: 15 are the tool catching a
card's drop shadow at the edge of a text box, and **14 are the frosted
`bg-white/20` pills on the headers** — the avatar initial and the
"permanent" badge, at 2.56:1 to 2.87:1. Those are a deliberate look rather
than an oversight, so they are left for a decision rather than changed.

### 3. The attendance screen lists the same twelve workers twice — FIXED

The screen the whole application exists for is **5,818px tall — nearly seven
phone screens — for twelve workers**, and the reason is that it contains two
complete rosters of them.

The first, the day view, begins at **y=1,139** and gives each worker the four
status buttons plus two time fields and a **Save**. The second, the entry
panel, begins at **y=4,036** — three thousand pixels below — and gives each
worker the same four status buttons in a more compact row, with "Adjust
times" standing in for the time fields and a different interaction ("tap the
same status twice to check out and back in"). Twelve workers, twenty-four
rows, twenty-six time inputs, ninety-seven status buttons on one page.

Marking a man in the lower panel does reach the database and the upper
counter — marking *Feb Joiner* present took the stat strip from 1 PRESENT to
2 and survived a reload. (That test record has been deleted again; the demo
data is as it was.) **Whether the other list repaints without a reload was
not established** — so this is reported as duplication, not as a sync bug.

Even so, the two rosters are the problem. A mukadam who marks the roll in
the top list and then keeps scrolling meets the same twelve names again, in a
different layout, with the same buttons, and has no way to know he is not
looking at a second day's work.

Two further things make it taller than it needs to be. Every day-view row
carries its **two time fields and Save even before a status is chosen**, so
eleven unmarked workers cost eleven idle check-in boxes. And each row carries
up to **four lines of 11.8px grey meta** (ID · trade · site · project · "Not
marked"), which is taller than the part you tap.

**Proposal.** Pick one roster and delete the other — the compact entry-panel
row, with the status buttons and no inline time fields, is the better of the
two. Reveal the time fields only once a status is chosen, since an absent man
has no check-in time. Trim the meta to one line. Put the month calendar
behind a toggle; the date picker above it already does that job. Expected:
roughly four workers per screen instead of one and a half, on a page about a
third of its current length, without removing a single capability.

**Done — the day view is the report, the panel is the editor.** Each day-view
row carries one badge saying what happened instead of four buttons offering
to change it; the inline check-in boxes are gone, since times are adjusted
from the panel's "Adjust times", which was always the other way to do it; and
the bulk buttons go too, because All present, All absent and Close shifts are
already on the panel, word for word. Nothing can be done from the screen that
could not be done before. The name is now a link to the worker, so the report
still leads somewhere.

**5,818px → 4,571px, and 26 inline time inputs → 2** (the pair in the
Adjust-times dialog).

The part that needed care is that a report has to be true. While both halves
were editors each repainted itself and staleness never showed; now a man
marked in the panel must stop saying "Not marked" eight inches higher up, or
the screen invites marking him twice. Every one of those endpoints already
returned the whole day — the panel simply was not reading it — so the report
repaints from the response already on the wire, with no extra round trip, and
only when the day on screen is the day being written to.
`tests/test_attendance_dayview.py` holds both halves, and breaking the
refresh makes it fail.

**The calendar is folded too.** It cost about 370px above the roster and
marking today never needs it, so it is behind a fold that names the month, and
the choice of open or shut is remembered — the month arrows are ordinary
links, so a calendar that shut itself on every month change would be worse
than one that never folded. Browser storage throws outright in a private
window or with site data blocked, so the page works without it, and the test
denies storage and loads the screen again to prove it.

**The screen, end to end: 5,818px → 4,259px, and the first worker from
1,139px down to 747px.**

### 4. Seventy-five controls carry no word and no name — FIXED

**187 controls across the 17 screens show no text at all; 75 of those carry
no `aria-label` and no `title` either**, so they are unknowable until you
press one and find out what it did.

The attendance status buttons are the good case: ✓ ✗ 🕐 🏠 are wordless, but
all 97 of them are properly labelled for a screen reader. The bad case is the
workers list, where **38 of 39 wordless controls are unnamed** — three
mystery glyphs on every worker card (calendar, ID card, eye), repeated twelve
times. Transactions has the same problem with its pen and trash icons, and
the back arrow is unnamed on 14 of the 15 screens that have one.

**Proposal.** Labels under the three workers-list icons, as the dashboard
tiles already do; and an `aria-label` on every remaining wordless control.
The first is a design change and needs approval; the second is invisible and
could be done straight away.

**The invisible half is done: 75 → 0.** Every wordless control now carries a
name, through `_()` so it is in Hindi too — nineteen new strings. Nothing
moved on screen. `tests/test_control_names.py` drives the real pages rather
than reading the templates, because a label can be lost to a branch only one
role ever sees; pulling a single label out makes it fail.

**The visible half is done too.** The three glyphs on a worker card say
Attendance, ID card and Open; the one that opens the worker keeps the filled
accent so it still reads as the main action. The words cost height — a card
goes from about 235px to 269px, three to a screen instead of three and a
half — and on a list a foreman reads every day that is worth paying. All 36
targets measure 46 × 101px, nothing overflows, and in Hindi हाज़िरी,
पहचान पत्र and खोलें each still sit on one line with the matras whole.

One snag worth keeping: a link whose `href` holds a Jinja expression with a
bare `>` in it (`start_date.month > 1`) ends the attribute as far as any
regex is concerned, so it slipped the automated pass and was named by hand.

### 5. The date picker shows the date in American order — FAIL

The attendance screen shows **`10/21/2026`**. India writes 21/10/2026, and
the rest of this application is careful about it — `format_date` in
`i18n.py` produces
"21 अक्टूबर 2026" correctly on the same screen, two inches lower. The US
order comes from the native `<input type="date">` taking its format from the
browser locale, which in this container is `en-US`.

On a phone set to Indian English or Hindi it will render correctly, so this
may be a container artefact rather than a defect in the product — but it is
exactly the kind of thing that must be checked on a real handset before
anyone trusts a date on this screen. Marked FAIL rather than NEEDS REVIEW
because 10/21 and 21/10 are both plausible readings of the same string and
the cost of guessing wrong is a day's wage on the wrong date.

The AM/PM time fields beside it are **not** a defect — a 12-hour clock is
ordinary in India and needs no change.

### 6. The navigation does not match the product — FIXED

- **Payroll has no tab of its own and lights "Transactions"** instead. It is
  the money screen, reachable only through a banner on the dashboard, and
  while you are on it the bar tells you that you are somewhere else.
- **Assignments and Notifications light nothing**, so the bar goes blank.
- The **QR button is styled as a dark filled FAB** in the middle of the bar.
  On the dashboard the Home tab is active *and* the QR button is filled, so
  two items read as "you are here".
- **Quick Actions is half duplication, half the only way in.** Of its six
  tiles, three — Mark Attendance, QR Scanner, Transactions — are already one
  tap away in the bar below. The other three — Add Worker, Assignments,
  Closures — are *not reachable any other way*, which is why Assignments and
  Closures light no tab: the bar does not know about them.

**Proposal.** Give Payroll the tab it deserves in place of Transactions
(transactions are reachable from a worker and from payroll), and give the QR
button the same active treatment as the other tabs so only one thing reads as
current. Then let Quick Actions carry only what the bar cannot reach — Add
Worker, Assignments, Closures — and drop the three duplicates, which buys
back most of a screen on the dashboard.

**Done.** The bar is Home · Workers · Attendance · [Scan] · Payroll ·
Profile. Six tabs cannot hold a dozen screens, so every screen lights the
section it belongs to — transactions under Payroll, assignments under
Workers, notifications under Profile, the way closures already sat under
Attendance — and no screen leaves the bar blank.

The scanner is grey until you are on it. Not tinted: the active tab's chip
is a blue tint, so a tinted scanner would be the same signal again in a
different size. Grey keeps it prominent by shape and leaves blue meaning one
thing.

Quick Actions keeps Add Worker, Transactions, Assignments and Closures, and
drops Mark Attendance and QR Scanner. An attendance-role user has no screens
outside the bar at all, so the section is no longer rendered for them rather
than filled with two duplicates.

`tests/test_navigation.py` checks that every screen lights exactly one tab
and that it is the right one.

**One trade remains, honestly:** on Transactions the bar says Payroll. Six
slots for a dozen screens means something shares, and payroll is opened far
more often than transactions, so the label is right far more often than it
was before — but it is not right every time.

### 7. The page title is not a heading on any screen — FIXED

Every screen shows its name in the navy header — "Workers", "Attendance" —
but those are `<div class="text-xl font-semibold">`, not headings. The
consequence: **only 2 of the 18 screens have an `<h1>` at all** (sign-in and
payroll preview), **14 start their outline at `<h3>`**, and four —
attendance, transactions, assignments, notifications — have **no heading
element anywhere on the page**.

Nothing looks wrong, and that is why it has survived. But a screen reader
announces no title, and "skip to the heading" lands nowhere.

**Proposal.** Make the existing title text an `<h1>` and the section titles
`<h2>`. No visual change whatsoever — the classes stay as they are.

**Done.** Twenty screens now open with an `<h1>` and their sections sit at
`<h2>`, with no level skipped; the payslip's three section headings come up
from `<h4>`. "No visual change" was checked rather than asserted: the build's
preflight resets headings to inherit their font and carry no margin, and no
rule in `custom.css` targets a heading tag, so the dashboard, the workers
list and the payroll screen render **pixel for pixel as before — 0 of
1,316,640 pixels differ on each**. `tests/test_headings.py` holds it.

### 8. Thirteen per cent of all text is under 12px — NEEDS REVIEW

**188 of 1,361 runs are below 12px, and another 447 sit between 12 and 14px.**
The smallest are the six bottom-navigation labels at **9.92px** — 102
instances, the most-seen text in the product — at 2.45:1 contrast.

In Hindi this is worse than the number suggests. Devanagari carries matras
above and below the line that Latin does not; at 9.92px "दर्ज नहीं" has
roughly half the effective stroke height of "Unmarked". Nothing clips —
that was checked and is clean — but legible and readable are not the same
thing.

**Proposal.** A floor of 12px for anything a person must read, 11px for
decoration; nav labels to 11px with the darker ink from finding 2.

### 9. Colour is decoration, not meaning — NEEDS REVIEW

The dashboard shows four stat tiles in blue, green, purple and orange, then
four action tiles in blue, green, indigo and teal. Payroll shows four more in
blue, green, orange and purple. The colours do not encode anything: "Total
Workers" is as loud as "Absent Today", and 8.3% attendance — one man present
out of twelve — is rendered in friendly purple with no indication that it is
alarming.

Meanwhile the attendance calendar has **at least five colour states** (green,
pink, amber, white, outlined, plus orange dots) **and no legend anywhere**.

**Proposal.** Reserve saturated colour for meaning — green for present and
paid, amber for attention, red for absent and deductions — and render
neutral facts on white cards with dark type, as the worker's own home screen
already does. Add a one-line legend under the calendar.

### 10. Hindi stops at the interface; the data stays in English — NEEDS REVIEW

The translation itself is thorough and the layout holds: across 17 screens
the Hindi text is between 13% shorter and 3% longer than the English, and
nothing overflows. But on a fully Hindi attendance row the worker's name, his
trade, his site and his project are all still Latin — *"CI002 · Civil ·
Manesar Industrial Corridor · Storm Water Drainage"* above *"दर्ज नहीं"*. A
Hindi-only reader can read the status and not the site.

This is a decision, not a bug. Proper nouns reasonably stay as they are
entered. But **site and project names are what a mukadam navigates by**, so
one option is a Hindi name field on sites and projects, filled in by the
administrator, used when the interface is in Hindi.

### 11. Smaller things

- **Settings' seven tabs wrap onto three ragged rows**, leaving "Salary"
  alone on the third. A horizontal scroll strip would hold them in one line.
- **The company logo uses the browser's native "Choose File" button** — the
  only unstyled control in the application, and it looks like it.
- **Headers crowd at 390px.** "Workers / Manage Employee Records" wraps to
  two lines beside an "+ Add Worker" button that also wraps to two; same on
  the mukadam's screen, where the title, the date and the "My Attendance &
  Pay" button all wrap at once.
- **The sign-in field is labelled "Username or Email"**, but a worker signs
  in with a phone number, and the button says "Sign In to Dashboard" when a
  worker is not going to a dashboard.
- **Form control heights vary** — 48, 50, 52, 60px for ordinary single-line
  inputs — at three different font sizes (12.8, 14, 16px).
- **The flash toast is fixed over the header.** It is pinned `top-4 right-4`
  and auto-hides after five seconds, so on the powers screen it sits on top
  of the back button for those first five seconds.

---

## What is already right

Worth saying plainly, because it is the ground to build on:

- **Tap targets: 217 of 218 buttons are 44px or larger.** This was fixed
  earlier and has held. The one exception is the **×** that dismisses the
  flash toast, at 9 × 24px — it was missed because a toast is only on screen
  when there is a message to show. It auto-hides after five seconds, so it
  matters little, but it should be brought up with the rest.
- **No layout defects.** Zero clipping, zero overflow, zero off-screen
  content, zero nav overlap, in both languages.
- **Hindi does not break the layout** anywhere, and Devanagari renders
  cleanly at every size used.
- **The worker's home screen is the best screen in the product**: one number
  — ₹800.00 net payable — a status pill, four small stat chips, a calendar
  and a single blue button. Quiet, obvious, one accent colour.
- **The mukadam's roll is the second best**, and shows only the two statuses
  he is allowed to set.
- **The payroll "Generate / Refresh" card has a real hierarchy**: a ghost
  preview, a solid primary, a quiet export. That is the button system the
  other 52 shapes should collapse into.

---

## What this would take

Grouped so they can be approved separately. Nothing here has been started.

| | Change | Visible? | Rough size | |
|---|---|---|---|---|
| A | One `money` filter at all 73 sites | yes, everywhere | half a day | **DONE** |
| B | Contrast: colour substitutions | slight | half a day | **DONE** |
| C | `aria-label` on 75 unnamed controls | no | 2 hours | **DONE** |
| D | Titles become `<h1>`/`<h2>` | no | 1 hour | **DONE** |
| E | Attendance: day view becomes a report, times collapse | yes, large | 1–2 days | **DONE** |
| E2 | The month calendar behind a toggle | yes | 2 hours | **DONE** |
| F | Labels under the workers-list icons | yes | 2 hours | **DONE** |
| G | Navigation: payroll tab, FAB state, Quick Actions | yes | half a day | **DONE** |
| H | Type and spacing scale, one button system | yes, everywhere | 2–3 days | waiting |
| I | Colour given meaning; calendar legend | yes | 1 day | waiting |
| J | Hindi names for sites and projects | yes, Hindi only | 1 day + data entry | waiting |
| K | The frosted `bg-white/20` header pills, 2.56:1 | slight | 2 hours | new, waiting |

A, B, C, D, E, E2, F and G are done. C and D changed nothing a person can see; A and B
were corrections rather than redesigns; E and E2 took the attendance screen
from 5,818px to 4,259px without removing a single capability. **H, I, J and
K have not been started.**

Of what is left, H is the largest and the least urgent: the type and button
system is untidy, but it is not stopping anyone, and three days spent on it
now would be three days spent before anyone has watched a mukadam use this
on a real phone. I — giving colour a meaning and the calendar a legend —
is the one most likely to be worth doing next. J is mostly data entry for
the company rather than code. K is two hours whenever the frosted header
pills are looked at again.

---

## Selecting several at once: where it is, and where it is not

Asked separately, and worth recording because the feature is better than it
looks: **press and hold any item** and a selection bar appears. It is live on
eight screens and twelve lists, all served by one endpoint,
`POST /api/bulk/<scope>` in `bulk.py`, which re-queries every id through the
tenant-scoped session and checks the permission server-side rather than
trusting a hidden button.

| Screen | What can be selected | What you can then do |
|---|---|---|
| Workers | workers | Activate · Deactivate · Delete |
| Attendance | workers on the chosen date | Present · Late · Check Out, and for an administrator Absent · Half Day · Leave |
| Payroll | workers | Generate · Mark Paid · Mark Pending |
| Transactions | transactions | Cancel · Restore · Delete |
| Assignments | workers | Assign / Transfer · End Assignment |
| Closure days | closure days | Allow Attendance · Lock Attendance · Delete |
| Notifications | notifications | Mark Read · Mark Unread · Delete |
| Settings | sites, projects, tasks, departments | Archive · Restore · Delete |
| Settings | attendance users | Enable · Disable · Delete |

### Where it should also be

**1. The mukadam's roll (`/me/team`) — much the most valuable, and not free.**
He marks two to twenty men one by one, every working day; nobody in the
product would save more taps. The screen has no selection at all today.

Two things have to happen first, and the second is a security change, so this
is not the half-hour job it looks like. `bulk_action` is in neither
`WORKER_ENDPOINTS` nor `SUPERVISOR_ENDPOINTS`, so a worker login that reaches
it is redirected to its own page — the deny-by-default rule holding exactly
as intended, and **there is no hole today**. But opening it is not enough:
`worker_visible_to_user` only knows about site- and project-scoped attendance
users, and for a mukadam — who has neither list — it falls through to
`return True`, meaning *every* worker in the tenant. Opening the endpoint
without first teaching that function about `supervisor_team_ids` would let a
mukadam post the id of a man who is not his and mark him. The guard belongs
in that one function, where the rest of the rules already live, with a test
that removing it fails.

**2. One worker's month (`/worker_attendance/<id>`).** An administrator
correcting five days to Leave does it five times. The calendar cells are not
selectable. This needs a new scope — attendance for one worker across several
dates — rather than reusing the existing one, which is keyed to a single date.

**3. A worker's transactions, on the worker's own profile.** Several advances
to cancel in a row is a real errand, and the Transactions screen already has
the bar; the profile list does not.

**4. The payroll preview** could have it, but the payroll screen beside it
already does, so this one is close to pointless.

---

## What was not examined

- **No real device.** All of it on Chromium at 390 × 844. Sunlight
  legibility, the real size of a thumb, and how the native date input
  formats on an Indian handset are all still unknown.
- **No real people.** Nobody has watched a mukadam mark a roll on this
  screen. Every usability claim here is inference from the artefact, not
  observation.
- **The printable documents** (payslip, report, ID card) were reviewed under
  Phase 9 and are not re-examined here.
