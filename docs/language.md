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

## What is *not* translated, and why

| | |
|---|---|
| Worker names, IDs, departments, positions, site and project names | Employer-entered data. Someone who typed "Munsi" expects to read "Munsi". |
| Stored dropdown values (`employee_type`, e.g. `permanent`) | Stored as the English string on the record; translating the display without a value-mapping layer would make the list and the filter disagree. |
| `am` / `pm`, `₹` amounts, `GST No.`, `Reg. No.` | Read the same way in both languages in India. |
| **Payslip and worker-report PDFs** | Still English. They go to banks and contractors, and Hindi rendering through html2canvas could not be verified here — see below. |
| The brand name "SmartWorker" | A name. |

## Not verified

- **Devanagari rendering on a real Android device.** This container has no
  Devanagari font installed, so a screenshot taken here shows tofu boxes
  whatever the markup says. The font stack is
  `'Inter', 'Noto Sans Devanagari', 'Nirmala UI', sans-serif` — Inter has no
  Devanagari, so Hindi falls through to the next family, and Android ships
  Noto Sans Devanagari. Checked in the browser: the nav labels do not clip at
  390px width.
- **Hindi in the generated PDFs**, for the same reason, which is why the
  payslip and worker report were left in English rather than changed blind.
