# UI measurement scripts

The numbers in `docs/ux-review.md` come from these. They drive a real
Chromium at a 390 × 844 phone viewport against a running server and read what
reaches the screen, so that a claim about the interface can be checked rather
than believed.

Start the application first — they sign in as the demo administrator and do
not start a server of their own:

    python3 main.py &
    python3 tools/ux/design_tokens.py
    python3 tools/ux/contrast.py
    python3 tools/ux/legibility.py
    python3 tools/ux/wordless.py
    python3 tools/ux/controls.py && python3 tools/ux/links.py
    python3 tools/ux/documents.py
    python3 tools/ux/hindi_gaps.py

Two environment variables, both optional:

- `UX_BASE` — where the server is (default `http://127.0.0.1:5000`)
- `UX_CHROME` — the Chromium binary (default is the one in this container)

Each prints its summary and leaves the raw rows in `tools/ux/out/`, which is
not tracked.

| Script | Answers |
|---|---|
| `design_tokens.py` | how many type sizes, inks, fills, radii, paddings and button shapes actually reach the screen |
| `contrast.py` | what each run of text really sits on, and its WCAG ratio |
| `legibility.py` | how small the text gets, in both languages |
| `wordless.py` | which controls show no word, and whether they at least carry a name |
| `controls.py` | every control, and what it is attached to — link, submit, handler, listener, or nothing |
| `links.py` | whether every link answers and every form action resolves (reads `controls.py`'s output) |
| `documents.py` | generates all eight printable documents and reads every page for blank sheets, cut lines and stranded headings |
| `hindi_gaps.py` | what is still English when the interface is set to Hindi, screen by screen |

### What these cannot tell you

They answer "is this control attached to something?" — never "does the
thing it is attached to work?". A filter chip bound to a form that reloads
the page having filtered nothing passes every script here. Two tests in
`tests/` cover that gap and should be run alongside them:

| Test | Answers |
|---|---|
| `test_interactions.py` | presses the controls that change something and checks the change: the chips filter, the search searches, the pager pages, the fold folds, the selection bar counts records rather than rows, mark-all-read marks all read |
| `test_forms_and_modals.py` | opens all eleven modals and checks they appear with their fields, then posts every create form and looks for the row |
| `test_no_script_errors.py` | loads every screen in both languages and listens for a thrown exception, a console error or a failed request — a screen can answer 200 with its scripts dead, and then every icon on it that needs them does nothing |

## Seven things that will bite you

**Do not take a full-page screenshot to measure against.** Chromium stretches
the viewport to capture one and the page reflows, so coordinates read at
phone height stop matching the pixels — sticky headers and anything sized in
viewport units move, and a handful of rows come back scored against the wrong
background. `contrast.py` scrolls a screen at a time and photographs each
screen instead.

**Do not decide a control is dead from the markup.** There is no DOM API
that lists an element's listeners, and the first version of `controls.py`
called five controls dead that were all bound with `addEventListener` — the
password eye, the photo button, both OTP buttons. It now wraps
`addEventListener` before any page script runs and marks the elements it is
called on.

**Do not judge a printed page from a thumbnail.** A 58dpi render of a
payslip made the calendar legend look sliced in half across a page break.
It was not: asking the paginator for its cut points showed every one
falling exactly on a block edge. `documents.py` reads the page at 110dpi
and reports where the ink actually is.

**Do not take the background from the stylesheet — but do not ignore it
either.** The navy header is a gradient, which paints no
`background-color`, so walking up the ancestors for one finds the page
behind it and reports white text on a white page. That is why `contrast.py`
reads pixels. But sampling inside the text run's own box is only sound when
the run really is on a gradient: a tight box around small text is mostly
glyph and anti-aliased edge, the flat colour behind it never reaches a
majority, and the fallback then picks a dark edge pixel as though it were
the background. That reported the worker-card buttons at 3.69:1 and 2.74:1
when the colours they declare are 9.37:1 and 5.80:1 — and twenty of
twenty-eight reported failures were this. It now reads the nearest declared
background when nothing translucent or gradient is in the way, and reaches
for pixels only otherwise.

**A `[gradient]` row is a floor, not a reading.** It is the worst point
anywhere under the run, which is not necessarily what the glyphs sit on.
Before changing a colour because of one, measure that element properly —
screenshot it with its glyphs set to `transparent`, average the backdrop,
composite the text colour over it. `tests/test_glass_contrast.py` does
exactly that, and it is the reason the avatar initials were left alone:
the sweep calls them 2.82:1 against a 3.0 floor, and composited they are
3.4:1.

**Do not write an inline event handler, and do not use a string predicate
to drive the browser.** The application sends a Content-Security-Policy
whose `script-src` allows no inline script: an `onclick=` is refused, and so
is anything evaluated from a string. Markup declares `data-act="fnName"`
and `static/js/actions.js` dispatches it. In these scripts that means
Playwright's `wait_for_function("some expression")` fails with an EvalError,
because Playwright evaluates a string predicate with `eval()` inside the
page — use `wait_for_url(...)` or poll with `evaluate("() => …")`, which go
through the debugger protocol instead.

**Do not call an inline onclick a missing function.** `this.closest(...)`
and `event.preventDefault()` start with an identifier and a bracket, so the
"is this function defined?" check matched them and reported the flash
toast's close button as broken. The root there is bound at call time, not a
global to look up; `controls.py` skips `this` and `event`.
