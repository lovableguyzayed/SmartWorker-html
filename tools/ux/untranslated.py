"""Which literal strings in the templates are not wrapped in _().

hindi_gaps.py says what a Hindi screen still shows in English. This says
where to fix it: every piece of visible text in a template that is written
as a bare literal rather than passed through the translation helper, with
the file and line.

It reads the templates rather than the rendered page, because that is where
the edit goes. Attributes that a person reads — placeholder, title,
aria-label, the label on a submit button — count as visible text.
"""
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                    'templates')

# Text between tags, and the attributes a person actually reads.
BETWEEN = re.compile(r'>([^<>{}]+)<')
ATTRS = re.compile(r'(?:placeholder|title|aria-label|alt)="([^"{}]+)"')
VALUE = re.compile(r'<option[^>]*>([^<>{}]+)</option>')
WORDS = re.compile(r"[A-Za-z][A-Za-z'’]{2,}")

# Not translation gaps.
SKIP_EXACT = {'SmartWorker', 'QR', 'PDF', 'CSV', 'ID', 'IST', 'OTP', 'UPI',
              'IFSC', 'PAN', 'GST', 'AM', 'PM', 'OT'}
SKIP_FILE = {'_calendar.html'}          # its labels come from weekday_names


def is_prose(text):
    text = text.strip()
    if not text or text in SKIP_EXACT:
        return False
    words = WORDS.findall(text)
    if not words:
        return False
    # A lone capitalised token that looks like a code, not a word.
    if len(words) == 1 and re.fullmatch(r'[A-Z]{2,6}\d*', text.strip()):
        return False
    return True


found = defaultdict(list)
for name in sorted(os.listdir(ROOT)):
    if not name.endswith('.html') or name in SKIP_FILE:
        continue
    path = os.path.join(ROOT, name)
    src = open(path, encoding='utf-8').read()
    # Script and style bodies are not interface copy.
    stripped = re.sub(r'<(script|style)[^>]*>.*?</\1>', lambda m: '\n' * m.group(0).count('\n'),
                      src, flags=re.S | re.I)
    for lineno, line in enumerate(stripped.split('\n'), 1):
        for pattern in (BETWEEN, ATTRS, VALUE):
            for hit in pattern.findall(line):
                if is_prose(hit):
                    found[name].append((lineno, hit.strip()[:72]))

total = sum(len(v) for v in found.values())
uniq = {t for v in found.values() for _, t in v}
print('%d bare literals in %d templates, %d of them distinct\n'
      % (total, len(found), len(uniq)))
for name, items in sorted(found.items(), key=lambda kv: -len(kv[1])):
    print('  %-28s %3d' % (name, len(items)))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
os.makedirs(out, exist_ok=True)
with open(os.path.join(out, 'untranslated.txt'), 'w', encoding='utf-8') as fh:
    for name, items in sorted(found.items()):
        for lineno, text in items:
            fh.write('%s:%d\t%s\n' % (name, lineno, text))
with open(os.path.join(out, 'untranslated-unique.txt'), 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(sorted(uniq)))
print('\nout/untranslated.txt (with line numbers) and '
      'out/untranslated-unique.txt (%d strings)' % len(uniq))
