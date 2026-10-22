# SmartWorker — second design pass, and the printed documents

A designer's read of the interface after the first round of fixes, plus a
page-by-page check of every document the application produces. Small
corrections of copy and of one wrong timestamp were made as the review
went; everything that changed a layout was written down first and done
afterwards, in the order agreed.

**Where it stands: 12 of 13 findings fixed.** The one left open is #12,
the frosted header pills below the contrast floor, which is a deliberate
look rather than a defect.

What was measured is in `tools/ux/`: `documents.py` generates all eight
documents and reads every page, `hindi_gaps.py` renders each screen in
Hindi and reports what is still English.

---

## The documents

Eight: the payslip and the ID card through the PDF button, and the payslip
and the worker report through the browser's Print, each in both languages.
These go to a worker or to an inspector, which is a higher bar than a
screen — a page break through a pay table is not a cosmetic fault, it is
the document being wrong where somebody has to sign it.

### 1. The payslip printed four pages for a month that fits in three — FIXED

Two causes, both in the paginator.

**Salary Calculation is a 727px block and a page holds 786px.** As one
atomic piece it could never start on a page that had anything above it, so
it was pushed onto a sheet of its own and left the sheet before it 41%
empty. Its rows are cut points now, so it fills the page it starts on and
continues.

**The paginator preferred block boundaries to row boundaries.** It took the
lowest *coarse* cut and only fell back to fine ones when there were none —
so it ended a page at 59% full with legal row cuts sitting right below. It
now takes the lowest legal cut of either kind.

| | before | after |
|---|---|---|
| pages | 4 | **3** |
| fill per page | 72% · 59% · 94% · 39% | **72% · 96% · 95%** |
| cuts falling inside a block | 0 | **0** |

### 2. The payslip's own explanation printed raw floats — FIXED

A worker read **"Full monthly salary 38000.0 applies"** on the document
that tells him what he is owed, and **"₹1461.5385"** beside it. Every
template was moved onto the money filter earlier; this prose is built in
the salary engine and escaped the sweep. It reads `₹38,000` now.

Fixing it broke Hindi twice, and both are worth recording because neither
failed anything:

- The Hindi replacements put a `₹` in front of each captured amount, so an
  amount carrying its own came out **`₹₹38,000`**. The pattern matched, so
  nothing errored; it simply printed the symbol twice.
- Taking the `₹` out of the replacements fixed the new notes and silently
  **stripped the symbol from every note stored before today** — a payslip's
  explanation is kept as the audit record, and those still read `38000.0`.

`translate_note` collapses the double instead, so both shapes read properly
and the stored records are left exactly as they were written, which is what
an audit record is for.

### 3. The Hindi page number sat inside the printer's dead band — FIXED

It was pinned 286mm down the sheet and anchored by its *top*. A strip of
Devanagari is taller than Latin at the same size, so it ran to within
**3.6mm of the paper edge** — inside the ~5mm most printers cannot reach,
which would have shaved the page number off. Anchored by its bottom now,
level with where the English text sits.

### 4. A break rule had stopped working — FIXED

`.slip-wrapper h4 { break-after: avoid }` still pointed at `h4` after those
headings became `h2` in the headings change. It had been doing nothing
since, which lets a heading sit alone at the foot of a page with its table
overleaf.

### 5. The printed payslip and report still end on a near-empty page — FIXED

| document | pages before | pages now |
|---|---|---|
| worker report (Print) | 3, last 81% empty | **2** |
| payslip (Print) | 3, last 85% empty | **2** |

Both documents, both languages. `tools/ux/documents.py` reports 0 findings
across all eight.

**A correction to what this entry used to say.** It claimed the documents
had to lose about 30mm, and offered smaller type, a tighter calendar, or
moving the signature strip as the three ways to find it. That was wrong on
the measurement and therefore wrong on the remedy. Measured properly: the
payslip ran **9mm** over two sheets and the report **10mm**, against a
capacity of 534mm once the repeating running header is counted on each
sheet. Nothing needed redesigning. The space was already there, in the
wrong places.

**Where it came from.** All of it was white space set for a phone and
inherited by paper, and none of it was type:

- the Salary Calculation table — 212mm, 39% of the payslip — at 40px for a
  row holding one 12px line;
- the pay rows at 0.45rem above and below;
- the calendar's day cells, still carrying the 44px *tap target* minimum,
  on a sheet where nothing is ever tapped;
- the report's thirty-odd table rows at 5px of padding each, and its nine
  24px section gaps.

**The blank sheet was a different bug, and a real one.** `base.html`
declares the bottom-navigation clearance — 112px, about 30mm — with
`!important` in an inline `<style>`. `custom.css` carried a print reset for
it that **could never have worked**: both declarations are `!important` at
equal specificity, and `custom.css` is linked before that inline block, so
the reset lost on source order and had been dead since it was written.
Every printed screen in the application was padded with 30mm of clearance
for a navigation bar that paper does not have. The reset now lives beside
the declaration it undoes.

**Also fixed on the way:** the payslip printed its policy note in English
on a Hindi payslip, directly under the same sentences translated into
Hindi as bullets. The four screens that show that note all pass it through
`lnotes`; the payslip — the one document that goes to the worker — did not.

**Tried and reverted:** 9mm margins instead of 12mm. It reclaimed 6mm a
page and did not remove the sheet, so it went back.

`tests/test_print_pages.py` holds the line: it checks both documents in
both languages, rejects a sheet carrying only the running header, pins the
print stylesheets against ever setting a `font-size` — shrinking the
figures is the one way this must not be won — and asserts that the
bottom-nav reset stays in the file where it can win.

**A correction.** My first read of a 58dpi thumbnail said the calendar
legend was sliced in half across a page. It is not. Asking the paginator
directly showed every cut falling exactly on a block edge, and
`tools/ux/documents.py` now checks that on every page of all eight
documents.

### What the documents get right

- The ID card is one page at 83% ink in both languages.
- Both payslips carry a running header and a page number on every sheet.
- Devanagari renders correctly throughout, with no clipping.
- The raster payslip is ~550KB, not the 2.7MB it once was.

---

## The interface

### 6. A Hindi screen is still substantially English — FIXED as far as a lookup table can

**576 runs of English text across 19 screens** when the language is set to
Hindi. Half-translated reads as unfinished, and it is the first thing
anyone would call unprofessional.

| screen | runs still in English |
|---|---|
| Settings | 86 |
| Add a worker | 79 |
| A worker's profile | 77 |
| Edit a worker | 77 |
| Payroll preview | 43 |
| Attendance | 36 |
| One worker's attendance | 27 |
| Workers | 25 |
| Transactions | 24 |
| Assignments | 23 |
| everything else | under 22 each |

The pattern is clear: the screens a mukadam uses every day are translated,
and the deep administrative screens — settings, the worker forms, the
modals — are not. That is the right order to have done it in, and it is
also why this looks worse than it is.

**Done.** The table grew from ~507 strings to 830+, and the sweep now
reports **159 runs across 17 screens**, down from 576 across 19.

What is left is not a lookup-table problem and will not be fixed by adding
rows to one:

- sentences built around a number the engine composes at runtime
  (*"exact ₹1,461.54 · 26-day basis"*),
- notification and audit text stored in the database in English, which is
  the audit record and is deliberately not rewritten,
- data — worker names, site names, department names — which `hindi_gaps.py`
  already skips where it can recognise them.

A fluent reader should still check the wording; a lookup table cannot tell
you that a correct translation reads stiffly.

### 7. Notification times were labelled UTC — FIXED

Every notification read **"21 Oct 2026, 09:35 UTC"**. Stored timestamps are
naive IST — `timeutil.py` exists precisely because the server runs on UTC
and attendance was landing 5½ hours early — so the time was right and the
label was wrong. A foreman reading it adds five and a half hours and
believes the mark was made at 15:05. It reads `IST` now, and the date goes
through `ldate` so the month is in Hindi too.

### 8. The Add screen said "Update Profile Information" — FIXED

The title switched between Add and Edit; the line under it did not, so the
Add screen described updating a worker who did not exist yet. Both strings
were also raw English on a Hindi screen. Fixed and translated.

### 9. Notifications repeat themselves and carry no shape — FIXED

Title: *"Attendance: Gurpreet Singh Bhatia — present"*. Body: *"Site
Supervisor marked Gurpreet Singh Bhatia (CI005) as present on 20 Oct 2026
at Dwarka Expressway Package 3"*. The name and the status are in both. Five
cards in a column, identical icon, identical blue dot, roughly 140px each,
no grouping by day and no collapsing — twelve workers marked in one go
produce twelve near-identical cards.

**Done.** The body now carries only what the title does not — who marked
it, where, and how — and the date comes off the row entirely, because the
day separator above it already says so. The feed is grouped by day with
**Today** / **Yesterday** separators, and an unbroken run sharing a
category, a body and an outcome folds into one line: *"6 workers —
Present"* with the names underneath, four of them and then *"and 2 more"*.

Folding loses nothing. The folded line carries every id behind it, so
selecting it selects all six, and the selection bar counts records rather
than rows — a fold of six reads "6 notifications selected", not "1".

Two things turned up while doing it:

- **A site user's bulk marking notified nobody.** Marking one worker by
  hand wrote a notification; marking forty through the selection bar wrote
  none, so a whole day's attendance could be entered without a trace on a
  screen titled "Attendance activity from all sites". It now writes one
  line per bulk action — not forty.
- Rows stored before this change keep their old shape, which still reads
  repetitively. They are audit records and are not rewritten, the same
  decision taken over the doubled rupee sign. New rows read correctly.

18 seeded notifications render as 13 rows. Checked in `tests/test_notifications.py`.

### 10. Assignments shows the same information three ways — FIXED

The filter chips say All · Assigned · Unassigned. Under them, two tiles
repeat **6 Assigned** and **6 Unassigned** — in green and rust, as though
unassigned were an error rather than a state. The tiles look pressable and
are not.

**Done.** The counts are on the chips — *All (12) · Assigned (6) ·
Unassigned (6)* — and the two tiles are gone. The counts are computed
before the assigned/unassigned filter runs, so every chip states the whole
roster rather than whatever is currently showing.

Also on that screen: the site and project line wraps mid-phrase
(*"Manesar Industrial / Corridor • Storm Water / Drainage"*), and the right
column holds two buttons on one row and one on the next, so card heights
and button widths change down the list.

### 11. The Add screen previews data that does not exist yet — FIXED

A hero card shows a large **N** avatar, *"Position • Department"*, *"ID:
Auto-Generated"* and a QR placeholder — about 210px of a screen given to
placeholders styled like real values, with "Auto-Generated" said twice.

**Done.** The hero card is split: Edit keeps it in full, Add shows only the
photo button and one line of explanation. The phantom **N** avatar, the
*"Position • Department"* placeholder, the second *"Auto-Generated"* and
the QR placeholder are gone from the Add screen.

### 12. The frosted header pills remain below the contrast floor — OPEN

Carried over from the first review: the avatar initial and the "permanent"
badge sit on `bg-white/20` over the blue header at **2.56–2.87:1**. They
are a deliberate look, so changing them is a design decision.

### 13. The selection hint was under the floor — FIXED

`.ms-hint` — *"Press and hold a worker to select several at once."* — ran
`gray-500` on the page's off-white at **4.43:1**. It is the one line that
tells a first-time user the whole multi-selection feature exists, on eleven
screens. Darkened to the grey the navigation already uses.

The contrast sweep now reports **24 runs under the floor out of 1,026**
(2.3%, from 27). Every one of them is measured on a gradient, where the
tool takes the worst point under the text rather than where the glyphs
actually sit — they are findings #12 and the card-label greys, not solid
fills. Nothing on a solid fill fails.

### What the interface gets right

Worth saying, because this is the second pass and the ground has moved:

- Every control is attached to something: 612 controls, 0 dead, 0 broken
  handlers, all 72 links answering and all 64 form actions resolving.
- All 35 bulk actions across 11 lists do what their labels promise,
  verified against the database.
- Text on a solid fill is at the contrast floor everywhere — 259 failures
  to 0.
- Every screen names itself and lights exactly one tab.
- The attendance screen went 5,818px to 4,259px without losing a capability.
- Money reads as money: `₹1,95,438`, not `₹195438`.

---

## What to do next, in order

1. **Finish the Hindi** (#6). A day, plus somebody to check the wording. It
   is the largest visible gap and it is pure addition — no layout moves.
2. **Notifications** (#9) and **Assignments** (#10). Half a day each, both
   remove things rather than add them.
3. **The Add screen's phantom preview** (#11). Two hours.
4. **The third printed page** (#5) and **the header pills** (#12) — both
   need a design decision before anyone writes code.

Nothing in 1–4 has been started.
