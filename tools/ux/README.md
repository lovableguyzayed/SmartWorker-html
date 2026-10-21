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

## Two things that will bite you

**Do not take a full-page screenshot to measure against.** Chromium stretches
the viewport to capture one and the page reflows, so coordinates read at
phone height stop matching the pixels — sticky headers and anything sized in
viewport units move, and a handful of rows come back scored against the wrong
background. `contrast.py` scrolls a screen at a time and photographs each
screen instead.

**Do not take the background from the stylesheet.** The navy header is a
gradient, which paints no `background-color`, so walking up the ancestors for
one finds the page behind it and reports white text on a white page. The
most common colour inside the text's own box is what is actually behind it.
Where glyphs or a gradient leave no clear majority, `contrast.py` calls the
row unmeasurable rather than guessing.
