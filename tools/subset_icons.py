"""Cut the icon font down to the icons this app actually draws.

fa-solid-900.woff2 ships 2,400-odd glyphs and weighs 147KB. Measured on
Chrome's Slow 3G profile it was 8.5 seconds of a cold start, second only
to the logo — and the app draws fewer than a hundred of them.

Run it after adding or removing icons:

    python tools/subset_icons.py            # report only
    python tools/subset_icons.py --apply    # rewrite the font files

Finding the icons is the delicate half, not the subsetting. An icon can be
written in markup as `fa-solid fa-user`, or assigned from JavaScript as
`icon.className = 'fa-solid fa-play'`, so both have to be read, and a name
that is missed goes missing from the interface as an empty box. Nothing is
inferred: every name is matched against the CSS's own name-to-codepoint
table, and anything in the source that looks like an icon but is not in
that table is listed for a human to look at rather than quietly dropped.

tests/test_icon_font.py runs the same scan and fails if the shipped font
is missing a glyph the source asks for.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, 'static/vendor/fontawesome/css/all.min.css')
FONTS = os.path.join(ROOT, 'static/vendor/fontawesome/webfonts')
# The complete fonts live outside static/ on purpose: kept so this can be
# re-run after adding an icon, but never reachable over HTTP, where they
# would be 545KB of files nothing asks for.
FULL = os.path.join(ROOT, 'tools/fontawesome-full')
FULL_CSS = os.path.join(FULL, 'all.min.css')
SCAN_DIRS = ('templates', 'static/js')

# Weight and sizing classes share the fa- prefix with the icons themselves.
# They are not glyphs and must not be reported as unknown names.
NOT_ICONS = {
    'solid', 'regular', 'brands', 'light', 'thin', 'duotone', 'sharp',
    'fw', 'spin', 'pulse', 'border', 'inverse', 'stack', 'stack-1x',
    'stack-2x', 'ul', 'li', 'xs', 'sm', 'lg', 'xl', '2xl', '1x', '2x',
    '3x', '4x', '5x', '6x', '7x', '8x', '9x', '10x', 'rotate-90',
    'rotate-180', 'rotate-270', 'flip-horizontal', 'flip-vertical',
    'flip-both', 'beat', 'fade', 'bounce', 'shake', 'spin-reverse',
    'spin-pulse',
}


def codepoints_by_name():
    """The font's own name -> codepoint table, read out of its CSS.

    Selector lists share one rule — .fa-house:before,.fa-home:before{...} —
    so every alias in the list maps to the same glyph. Codepoints run from
    two hex digits (fa-plus is \\2b) to five, which is why this does not
    insist on four.
    """
    # The complete stylesheet when it is there, because the shipped one is
    # cut down to the icons in use and would make the table shrink a little
    # more on every run — the same trap the fonts avoid by keeping the
    # originals in tools/fontawesome-full/.
    source = FULL_CSS if os.path.exists(FULL_CSS) else CSS
    css = open(source, encoding='utf-8').read()
    table = {}
    for selectors, code in re.findall(
            r'([^{}]*?)\{content:"\\([0-9a-f]{2,5})"\}', css):
        for name in re.findall(r'\.fa-([a-z0-9-]+):before', selectors):
            table.setdefault(name, int(code, 16))
    return table


def _without_comments(body):
    """Comments are not markup, and an icon named in one is not drawn.

    Worth the trouble: a note explaining why an icon was replaced mentions
    the old name, and a scanner that reads it keeps the dead glyph in the
    font forever while reporting a name nobody uses.
    """
    body = re.sub(r'\{#.*?#\}', ' ', body, flags=re.S)      # Jinja
    body = re.sub(r'<!--.*?-->', ' ', body, flags=re.S)      # HTML
    body = re.sub(r'/\*.*?\*/', ' ', body, flags=re.S)       # JS block
    body = re.sub(r'(?m)^\s*//.*$', ' ', body)               # JS line
    return body


def names_in_source():
    """Every fa-* token in the templates and the scripts."""
    found = set()
    for folder in SCAN_DIRS:
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, folder)):
            for name in files:
                if not name.endswith(('.html', '.js')):
                    continue
                body = _without_comments(
                    open(os.path.join(dirpath, name), encoding='utf-8').read())
                found |= set(re.findall(r'fa-([a-z0-9-]+)', body))
    return found


def wanted():
    """(codepoints, resolved names, names that are not icons at all)."""
    table = codepoints_by_name()
    used = names_in_source()
    icons = {n for n in used if n in table}
    unknown = sorted(used - icons - NOT_ICONS)
    # Icons only. A space was asked for here at first, defensively, and
    # the subsetter dropped it anyway — an icon font is never used to set
    # text, so there is nothing for it to do.
    points = {table[n] for n in icons}
    return points, sorted(icons), unknown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true',
                    help='rewrite the font files; without it, report only')
    args = ap.parse_args()

    points, icons, unknown = wanted()
    print('icons drawn by this app : %d' % len(icons))
    if unknown:
        print('\nfa-* names that are not in the font\'s table (%d).'
              % len(unknown))
        print('A typo here is an icon that will not render — check them:')
        for n in unknown:
            print('   fa-%s' % n)

    targets = [('fa-solid-900', True), ('fa-regular-400', False),
               ('fa-brands-400', False)]
    print()
    for stem, keep in targets:
        for ext in ('woff2', 'ttf'):
            path = os.path.join(FONTS, '%s.%s' % (stem, ext))
            if not os.path.exists(path):
                continue
            size = os.path.getsize(path) / 1024
            if not keep:
                # Nothing in the source asks for these weights; the browser
                # never downloads them, but they are still in the repo and
                # in every deploy.
                print('   %-22s %7.1f KB  unused by this app' % (
                    '%s.%s' % (stem, ext), size))
                continue
            print('   %-22s %7.1f KB' % ('%s.%s' % (stem, ext), size))

    if not args.apply:
        print('\nReport only. Re-run with --apply to write the subset.')
        return

    from fontTools import subset
    for ext in ('woff2', 'ttf'):
        src = os.path.join(FONTS, 'fa-solid-900.%s' % ext)
        if not os.path.exists(src):
            continue
        backup = os.path.join(FULL, 'fa-solid-900.%s' % ext)
        if not os.path.exists(backup):
            # Subsetting an already-subsetted file would narrow it further
            # on every run, and the second run could not be undone. The
            # complete font is always the input.
            print('   missing %s — cannot subset without the full font'
                  % backup)
            continue
        before = os.path.getsize(backup) / 1024
        options = subset.Options()
        options.flavor = 'woff2' if ext == 'woff2' else None
        options.desubroutinize = True
        options.layout_features = []
        options.notdef_outline = True
        font = subset.load_font(backup, options)
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=points)
        subsetter.subset(font)
        subset.save_font(font, src, options)
        font.close()
        after = os.path.getsize(src) / 1024
        print('   fa-solid-900.%-5s %7.1f KB -> %6.1f KB  (%.0f%% smaller)'
              % (ext, before, after, 100 * (1 - after / before)))
    # --- and the stylesheet, which was never cut ------------------------
    #
    # The fonts were subsetted a while ago and the CSS was not, so 102KB of
    # it went to every first-time visitor to name 2,452 icons, of which this
    # app draws about a hundred. The glyphs were already gone: the other
    # 2,336 names pointed at nothing.
    #
    # Only the name-to-codepoint rules are dropped. Everything else — the
    # @font-face blocks, .fa itself, the sizing, spin and stack classes —
    # is left exactly as it was, because those are not icons and something
    # does use them.
    if os.path.exists(FULL_CSS):
        full = open(FULL_CSS, encoding='utf-8').read()
        keep = set(icons)
        dropped = [0]

        def _rule(match):
            selectors, code = match.group(1), match.group(2)
            names = re.findall(r'\.fa-([a-z0-9-]+):before', selectors)
            if names and not any(n in keep for n in names):
                dropped[0] += 1
                return ''
            return match.group(0)

        trimmed = re.sub(r'([^{}]*?)\{content:"\\([0-9a-f]{2,5})"\}',
                         _rule, full)
        # A rule removed from the middle of a comma-joined list leaves the
        # comma behind; tidy those so the result is still valid CSS.
        trimmed = re.sub(r',\s*,', ',', trimmed)
        trimmed = re.sub(r'(?m)^\s*,', '', trimmed)
        # And the @font-face blocks that name a file this app does not
        # ship. Nothing draws .fa-brands or .fa-regular, so those two
        # weights were deleted — 375KB of files in every deploy that no
        # browser ever asked for. Leaving their @font-face behind would
        # make the stylesheet and the folder disagree, and the first
        # person to write fa-regular would get a 404 instead of a clear
        # miss. (tests/test_icon_font.py already fails on a name that is
        # not in the shipped font, which is the check that matters.)
        def _face(match):
            block = match.group(0)
            files = re.findall(r'url\(\.\./webfonts/([^)]+?)\)', block)
            files = [f.split('?')[0].strip('\'"') for f in files]
            if files and not any(
                    os.path.exists(os.path.join(FONTS, f)) for f in files):
                dropped_faces[0] += 1
                return ''
            return block

        dropped_faces = [0]
        trimmed = re.sub(r'@font-face\{[^}]*\}', _face, trimmed)

        before = len(full) / 1024
        open(CSS, 'w', encoding='utf-8').write(trimmed)
        after = os.path.getsize(CSS) / 1024
        print('   all.min.css          %7.1f KB -> %6.1f KB  (%.0f%% smaller,'
              ' %d icon rules, %d @font-face dropped)'
              % (before, after, 100 * (1 - after / before), dropped[0],
                 dropped_faces[0]))

    print('\nThe complete fonts and stylesheet are kept in '
          'tools/fontawesome-full/,\nso this can be re-run after adding '
          'icons without compounding.')


if __name__ == '__main__':
    main()
