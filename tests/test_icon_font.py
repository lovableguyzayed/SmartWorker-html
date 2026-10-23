"""Every icon the app draws must exist in the font the app ships.

The icon font is subsetted — cut from 2,400-odd glyphs and 147KB down to
the hundred-odd this app actually uses, which took 8.5 seconds off a cold
start on Slow 3G. The saving comes with a hazard that did not exist
before: add `fa-truck` to a template and it renders as an empty box,
because the shipped font no longer contains it and nothing says so.

So this reads the names out of the source the same way the subsetter does
and checks each one against the glyphs really present in the file being
served. It also catches the other half of the problem, which existed
before subsetting and had gone unnoticed: fa-wifi-slash is a Pro icon that
is not in the free set at all, and the offline bar had been drawing an
empty box next to its message.

If this fails after adding an icon, the fix is to run:

    python tools/subset_icons.py --apply
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from fontTools.ttLib import TTFont

import subset_icons

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-52s %r%s' % ('OK' if ok else 'FAIL', label, got,
                                 '' if ok else '  (want %r)' % (want,)))


points, icons, unknown = subset_icons.wanted()

print('--- the names in the source ---')
check('the app draws some icons', len(icons) > 50, True)
# A name that is not in the font's own table is a typo or a Pro-only icon;
# either way it is an empty box on a screen somebody is using.
check('every fa- name is a real icon in this font', unknown, [])
if unknown:
    for n in unknown:
        print('        fa-%s is not in the free set' % n)

print('\n--- the font that is actually served ---')
served = os.path.join(ROOT, 'static/vendor/fontawesome/webfonts/fa-solid-900.woff2')
check('the solid font exists', os.path.exists(served), True)

font = TTFont(served)
have = set()
for table in font['cmap'].tables:
    have |= set(table.cmap.keys())
font.close()

missing = sorted(p for p in points if p not in have)
check('every icon the app draws is in the file', missing, [])
if missing:
    table = subset_icons.codepoints_by_name()
    back = {v: k for k, v in table.items()}
    for p in missing:
        print('        U+%04X  fa-%s' % (p, back.get(p, '?')))

size_kb = os.path.getsize(served) / 1024
print('\n  font size: %.1f KB for %d icons' % (size_kb, len(icons)))
# The whole point. The full font is 147KB; if this creeps back up, the
# subset has been overwritten by a full copy.
check('the font is still a subset, not the whole set', size_kb < 60, True)

print()
if fails:
    print('FAILED %d of the checks above:' % len(fails))
    for label, got, want in fails:
        print('  %s: got %r, want %r' % (label, got, want))
    print('\nIf an icon was added, run: python tools/subset_icons.py --apply')
    sys.exit(1)
print('Every icon the app draws is in the font it ships.')
