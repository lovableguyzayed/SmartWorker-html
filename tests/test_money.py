"""Every rupee amount in the application goes through one function.

Two things are checked here. First that the function is right — Indian
grouping, paise only where there are paise, a real minus sign, and no drift
of a paisa when a float arrives. Then that the templates actually use it:
the whole point was to stop `₹38000.0` reaching the screen, and that is only
true for as long as nobody writes `₹{{ worker.daily_rate }}` again.
"""
import glob
import os
import re
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from money import group_indian, money, money0, money2

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append((label, got, want))
    print('  %-5s %-34s %-16s %s' % ('OK' if ok else 'FAIL', label, got,
                                     '' if ok else '(want %s)' % want))


print('--- Indian grouping ---')
for digits, want in [('1', '1'), ('99', '99'), ('999', '999'),
                     ('1000', '1,000'), ('99999', '99,999'),
                     ('100000', '1,00,000'), ('195438', '1,95,438'),
                     ('1234567', '12,34,567'), ('123456789', '12,34,56,789')]:
    check(digits, group_indian(digits), want)

print('\n--- the amounts that were wrong on screen ---')
check('payroll total',   money(195438),      '₹1,95,438')
check('monthly salary',  money(38000.0),     '₹38,000')
check('daily rate',      money(800.0),       '₹800')
check('net pay',         money(38000.00),    '₹38,000')
check('a deduction',     money(-1100.00),    '−₹1,100')
check('with paise',      money(1234.5),      '₹1,234.50')
check('paise kept',      money(99.99),       '₹99.99')

print('\n--- forms ---')
check('forced 2dp',      money2(38000),      '₹38,000.00')
check('whole rupees',    money0(1234.56),    '₹1,235')
check('no symbol',       money(1234.5, symbol=False), '1,234.50')
check('zero',            money(0),           '₹0')
check('None',            money(None),        '₹0')
check('empty string',    money(''),          '₹0')
check('a string amount', money('4500.25'),   '₹4,500.25')
check('a Decimal',       money(Decimal('1999.9')), '₹1,999.90')

print('\n--- it must not drift by a paisa ---')
check('0.1+0.2',         money(0.1 + 0.2),   '₹0.30')
check('half up',         money(2.345),       '₹2.35')
check('half up, rupees', money0(2.5),        '₹3')
check('tiny negative',   money(-0.001),      '₹0')

print('\n--- no template prints a bare rupee value ---')
# `₹{{ thing }}` with no filter is exactly how ₹38000.0 reached the screen.
BARE = re.compile(r'₹\s*\{\{\s*[^}|]+\}\}')
# A format string anywhere near a ₹ is the other way it used to be done —
# both quote styles, and the symbol inside the format string too.
FORMAT = re.compile(r'''₹[^₹\n]{0,40}["']%\.\d+f["']\s*\|\s*format'''
                    r'''|["'][^"'\n]{0,6}₹%\.\d+f["']\s*\|\s*format''')
# A guard that matches nothing proves nothing, so point it at the four shapes
# that were actually in these templates before the migration.
for bad in ['<span>₹{{ worker.daily_rate }}/day</span>',
            '<div>₹{{ "%.0f"|format(totals.total_gross) }}</div>',
            "<div>₹{{ '%.2f'|format(salary_preview.daily_rate) }}</div>",
            "{{ srow(_('Gross'), '₹%.2f'|format(sb.gross_eligible_salary)) }}"]:
    check('guard catches %s' % bad[:34].strip(),
          bool(BARE.search(bad) or FORMAT.search(bad)), True)
check('guard ignores a clean line',
      bool(BARE.search('<span>{{ worker.daily_rate|money }}/day</span>')), False)

offenders = []
for path in sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 'templates', '*.html'))):
    src = open(path, encoding='utf-8').read()
    name = os.path.basename(path)
    for line_no, line in enumerate(src.splitlines(), 1):
        if BARE.search(line) or FORMAT.search(line):
            # The worker report shows the exact daily rate to four places on
            # purpose, to show how a monthly wage divides. That one stays.
            if 'daily_rate_exact' in line:
                continue
            offenders.append('%s:%d  %s' % (name, line_no, line.strip()[:84]))

if offenders:
    fails.append(('templates still format money by hand', len(offenders), 0))
    for row in offenders[:25]:
        print('  FAIL %s' % row)
    if len(offenders) > 25:
        print('  ... and %d more' % (len(offenders) - 25))
else:
    print('  OK    no template formats a rupee amount by hand')

print('\n%d failed' % len(fails))
sys.exit(1 if fails else 0)
