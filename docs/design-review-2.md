# SmartWorker — second design pass, and the printed documents

A designer's read of the interface after the first round of fixes, plus a
page-by-page check of every document the application produces. Small
corrections of copy and of one wrong timestamp are made here; everything
that changes a layout is written down and left alone.

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

### 5. The printed payslip and report still end on a near-empty page — OPEN

| document | pages | last page |
|---|---|---|
| worker report (Print) | 3 | 81% empty |
| payslip (Print) | 3 | 85% empty |

Pages one and two fill to 91–93%, so only about a tenth of a page spills.
What lands on page three is the signature strip and the generated-on line,
which are deliberately kept whole.

**Tried and reverted:** 9mm margins instead of 12mm. It reclaimed 6mm a
page and did not remove the sheet, so it went back — 12mm is the safer,
more conventional margin and the change bought nothing.

To actually fix this the document has to lose about 30mm: either smaller
type, a tighter attendance calendar, or letting the signature strip sit
beside the net-payable panel rather than under it. All three are design
decisions, so none has been made.

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

### 6. A Hindi screen is still substantially English — OPEN, and the worst of it

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

It is roughly a day's work and needs somebody who writes Hindi to check the
wording, not just a lookup table. `tools/ux/hindi_gaps.py` lists exactly
which strings, screen by screen, and skips worker and site names so the
list is only real gaps.

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

### 9. Notifications repeat themselves and carry no shape — OPEN

Title: *"Attendance: Gurpreet Singh Bhatia — present"*. Body: *"Site
Supervisor marked Gurpreet Singh Bhatia (CI005) as present on 20 Oct 2026
at Dwarka Expressway Package 3"*. The name and the status are in both. Five
cards in a column, identical icon, identical blue dot, roughly 140px each,
no grouping by day and no collapsing — twelve workers marked in one go
produce twelve near-identical cards.

**Proposal.** Group by day with "Today" and "Yesterday" separators; collapse
a run from the same action into one line — *"Site Supervisor marked 3
workers present at Dwarka Expressway Package 3"*; let the body carry only
what the title does not.

### 10. Assignments shows the same information three ways — OPEN

The filter chips say All · Assigned · Unassigned. Under them, two tiles
repeat **6 Assigned** and **6 Unassigned** — in green and rust, as though
unassigned were an error rather than a state. The tiles look pressable and
are not.

**Proposal.** Put the counts on the chips — *All (12) · Assigned (6) ·
Unassigned (6)* — and delete the tiles. That removes a row and a false
affordance in one move.

Also on that screen: the site and project line wraps mid-phrase
(*"Manesar Industrial / Corridor • Storm Water / Drainage"*), and the right
column holds two buttons on one row and one on the next, so card heights
and button widths change down the list.

### 11. The Add screen previews data that does not exist yet — OPEN

A hero card shows a large **N** avatar, *"Position • Department"*, *"ID:
Auto-Generated"* and a QR placeholder — about 210px of a screen given to
placeholders styled like real values, with "Auto-Generated" said twice.

**Proposal.** Show the card once there is a name to put in it; until then,
the form alone.

### 12. The frosted header pills remain below the contrast floor — OPEN

Carried over from the first review: the avatar initial and the "permanent"
badge sit on `bg-white/20` over the blue header at **2.56–2.87:1**. They
are a deliberate look, so changing them is a design decision.

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
