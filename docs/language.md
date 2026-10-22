# Interface language (English / हिन्दी)

The app ships in English and Hindi. A supervisor picks the language from the
**Profile** screen, or from the login screen before signing in.

## How to add or fix a translation

Everything lives in one file: [`i18n.py`](../i18n.py). It is a plain Python
dict keyed by the English string, so anyone who reads Hindi can edit it with no
toolchain and nothing to compile:

```python
TRANSLATIONS = {
    'hi': {
        'Mark Attendance': 'हाज़िरी लगाएँ',
        ...
    },
}
```

Deliberately not flask-babel: that wants `.po` files compiled with `pybabel`
as a build step, and this app deploys by pushing to Render with no build stage
beyond `pip install`.

A string with no entry falls back to English, so a missing translation shows
English rather than a blank or a key — a half-translated screen is usable, a
screen full of `nav.workers` is not.

In a template:

```jinja
{{ _('Mark Attendance') }}          {# text, attributes, inline JS #}
{{ selected_date|ldate('%d %b %Y') }}   {# dates with Hindi day/month names #}
{{ note|lnote }}                    {# one generated salary note #}
{{ pay.policy_note|lnotes }}        {# a paragraph of them #}
```

Run `python3 tests/test_i18n.py` after editing. It checks the table for empty
values, for stray quotes that would break an inline `<script>`, and for a
**repeated key** — a duplicate is legal Python, the later entry silently wins,
and that is how a payroll badge quietly changes wording.

## Where the language is stored

In the Flask session, not on the user record. A shared site phone can be set
to Hindi while the office stays in English, and the choice survives logout so
the next shift's supervisor does not have to find the setting again.

`/language/<code>` is **not** login-required, on purpose: someone who only
reads Hindi has to be able to switch before they can read the login screen. It
writes one whitelisted value into the session and reads nothing.

## Two traps worth knowing about

**`{% set _ = list.append(x) %}`** is a common Jinja throwaway, and it shadows
the `_()` helper with `None` for the rest of the block. That took the whole
attendance screen down with a 500 once. The test suite now fails if any
template does it; use `_discard` instead.

**The service worker caches pages by URL**, and the language comes from the
session, so after a switch every cached page is in the old language.
`app.js` notices `<html lang>` change and posts `{type: 'purge-pages'}` to the
service worker, which drops the cached HTML (and puts the `/login` offline
shell back, since every cache miss falls through to it).

## Dates

`strftime` only knows the server's C locale, so a date header reading
"Tuesday, October 20, 2026" on an otherwise Hindi screen is the most visible
place a translation gives up. `i18n.format_date` substitutes `%A %a %B %b` and
also reorders a few patterns, because Hindi word order differs:

| | |
|---|---|
| `en` | Tuesday, October 20, 2026 |
| `hi` | 20 अक्टूबर 2026, मंगलवार |

A format with no name directives is handed straight to `strftime`, and an
untranslated language comes out exactly as it does today.

## Salary notes

The salary engine writes its working out as English prose and stores it in the
payroll snapshot — that is the audit record, and it must not change language
depending on who opens it. The prose is translated **on the way to the
screen** by `translate_note`, which pattern-matches each sentence shape and
keeps the numbers. Snapshots saved months ago translate too.

A note shape with no pattern comes back in English rather than being dropped,
and `tests/test_i18n.py` fails if the engine or the payroll route grows a note
that has no Hindi pattern.

## Messages that never pass through a template

Most notices are `flash()`ed and translated where they are shown, by the
`lflash` filter. Two kinds skip templates entirely and need looking after:

**Messages returned as JSON.** The scanner and the attendance day view paint
their own markup, so a message in a response body lands on the screen
verbatim. `_translate_json_messages` (an `after_request` in `routes.py`) walks
any JSON `messages` list — and the lone `message` the worker lookup answers
with — running each through the same translator, so the English in `routes.py`
stays the one canonical wording and a message added later is covered without
touching the endpoint.

**Messages raised in JavaScript.** `'No connection — the payment was not
recorded.'` never reaches the server at all; it is raised by the browser when
the request fails. Those strings are handed to the script already translated:

```jinja
toast({{ _('No connection — the payment was not recorded.')|tojson }}, 'error');
```

`|tojson` and not plain interpolation, because a Hindi sentence containing an
apostrophe would otherwise close the JavaScript string literal. (The test
suite also fails on a translation containing a quote, for the same reason.)

A string used on **both** sides — `'Amount must be greater than zero.'` is
raised in JavaScript when the amount box is empty, and returned by the
endpoint when a post arrives with a zero in it — lives in `TRANSLATIONS`, not
`FLASH_MESSAGES`: only `TRANSLATIONS` is readable from a template's `_()`.
`translate_flash` falls back to `TRANSLATIONS` after its own table and its
shapes, so the JSON path still finds it and there is one Hindi sentence rather
than two that drift apart.

## A shape whose captured group is itself translatable

`'Advance Salary ₹250 recorded for Arvind Kejriwal.'` has a translatable word
*inside* it: `Advance Salary` is a transaction type with a Hindi name of its
own, the one the dropdown on the same screen shows. A replacement string would
leave the English word sitting in the middle of a Hindi sentence. So those
three money shapes use `_hi_money`, which makes the replacement a function
(`re.subn` takes either) and looks the label up:

```python
(r'^(.+?) (₹\S+) recorded for (.+?)\.$',
 _hi_money('{2} के लिए {0} {1} दर्ज कर लिया गया।')),
```

A transaction type with no Hindi name still comes through, in English, rather
than vanishing — the same fall-through as everywhere else.

## What is *not* translated, and why

| | |
|---|---|
| Worker names, IDs, departments, positions, site and project names | Employer-entered data. Someone who typed "Munsi" expects to read "Munsi". |
| Stored dropdown values (`employee_type`, e.g. `permanent`) | Stored as the English string on the record; translating the display without a value-mapping layer would make the list and the filter disagree. |
| `am` / `pm`, `₹` amounts, `GST No.`, `Reg. No.` | Read the same way in both languages in India. |
| Stored transaction *descriptions* | The type shown in a list is translated; the sentence written onto the record when it was created stays as it was saved. Changing it would rewrite history. |
| The brand name "SmartWorker" | A name. |

## The printable documents

The payslip is translated in both of its output paths, and the generated
files were opened and read back rather than assumed:

**Print Slip** uses the browser's own renderer, so Hindi there is ordinary
text — 2104 characters extract cleanly out of the printed file.

**Save PDF** is the awkward one. The slip body is rasterised by html2canvas,
which handles Devanagari fine, but each page's running header and footer were
drawn with `pdf.text()` in jsPDF's built-in helvetica — a Latin-1 font that
cannot encode Devanagari at all. Embedding a Devanagari TTF would have added
roughly 300KB to a bundle that gets downloaded over 2G at a construction
site, so for a non-Latin language the chrome is rasterised from hidden DOM
instead (`pdfPrepareChrome`). English keeps the native-text path, which stays
sharper and smaller, and its output is byte-for-byte the same shape as before.

Two things that bit, both now covered by `tests/test_printable_pdfs.py`:

- A **transparent PNG** for that chrome made jsPDF store a raw bitmap plus a
  soft mask. The header strip alone went from 10KB to 451KB and the Hindi
  payslip to 2735KB against English's 550KB. White background and JPEG
  instead: 536KB, slightly *smaller* than the English file.
- **html2canvas crops to the element box**, and Devanagari matras sit outside
  a tight one, so the header came out with its glyphs sliced flat along the
  bottom. The chrome elements carry deliberate `line-height` and `padding`
  for that reason — it looks like loose styling and is not.

The page footer is one pattern (`Page %n of %t`) rather than four pieces,
so Hindi can read `पृष्ठ 1 / 2` instead of a word-for-word `पृष्ठ 1 में से 2`.

### The worker report

Prints through the browser, so Hindi there is ordinary text and no font
trickery is needed — 2517 characters extract out of the printed file. Its
"Policy in force" block comes from `salary.describe()`, whose values are
composed (`Fixed days (26)`, `2 day(s) per month`) and so cannot be looked up
whole; `translate_policy` matches those two shapes and falls back to the
ordinary table for the plain ones (`On`, `Off`, `Nearest rupee`).

### The ID card

One flat raster with no native jsPDF text at all, so it needed only its
labels translating. The one thing that must never change is the QR payload
(`CI002QR2025`) — it identifies the worker to the scanner, and the test
asserts it survives the translation untouched.

### A trap in checking this

`.report-section-title` carries `letter-spacing`, and that makes PyMuPDF
report a Devanagari matra twice — `प्रोजेक्ट` extracts as `प्रोोजेक्ट`. The
glyphs on the page are correct; it was confirmed by eye at 320 dpi before
being written off. The test folds repeated marks before comparing, and uses
`unicodedata.category() in ('Mn', 'Mc')` rather than `combining()`, because a
matra like U+094B is `Mc` with canonical combining class 0 and `combining()`
misses it entirely.

### Why the test owns its server

It starts its own server on its own port on purpose. Flask caches compiled
templates, so borrowing a dev server that was started before an edit makes
the test pass against the very bug it exists to catch — which is exactly
what happened the first time it was run against a deliberately reintroduced
fault.

## Not verified

- **Devanagari on a real Android device.** `fonts-noto-core` was installed in
  the build container so the PDFs above could actually be read; a real phone
  is still a different renderer. The font stack is
  `'Inter', 'Noto Sans Devanagari', 'Nirmala UI', sans-serif` — Inter has no
  Devanagari, so Hindi falls through, and Android ships Noto Sans Devanagari.
  Naming it explicitly matters: on a bare container `fc-match sans-serif:lang=hi`
  answers FreeSans, which has no Devanagari at all.
- **A real printer.** The print path was checked by printing to PDF.
- **A real QR scan of a Hindi card.** The payload was checked as text, not by
  scanning the rendered code.
