"""One way to write a rupee amount.

Before this there were four. Sixteen places formatted with `%.0f`, forty-six
with `%.2f`, one with `%.4f`, and ten printed the raw Python float, which is
how `₹38000.0` reached the workers list — not a rounding choice, just
`str(float)` arriving on screen. Nothing grouped the digits, so a foreman
read `₹195438` and counted them by eye to find out whether that was nineteen
lakh or one lakh ninety-five thousand.

India groups by lakh, not by thousand: 1,95,438, with the last three digits
together and everything above them in pairs. That is what `money` does.

Rounding is ROUND_HALF_UP on Decimal, the same convention the salary engine
uses, so a figure does not change by a paisa on its way to the screen.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

RUPEE = '₹'          # ₹
MINUS = '−'          # a real minus sign, not a hyphen
_PAISE = Decimal('0.01')


def _dec(value):
    """Whatever the template had, as a Decimal — or None if it was nothing.

    Floats go through str() first: Decimal(0.1) is 0.1000000000000000055…,
    which quantizes the wrong way often enough to matter on money.
    """
    if value is None or value == '':
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def group_indian(digits):
    """'195438' -> '1,95,438'. Last three together, then pairs."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ','.join(parts + [tail])


def money(value, places=None, symbol=True):
    """A rupee amount as a person should read it.

    places=None  show paise only when there are any: ₹38,000 but ₹1,234.50
    places=2     always two, for a column of figures that should line up
    places=0     whole rupees, rounded

    symbol=False gives the number alone, for a field that carries its own ₹.

    A negative amount reads ₹ after the minus — −₹1,100 — because the sign
    belongs to the amount, not to the currency.
    """
    amount = _dec(value)
    if amount is None:
        amount = Decimal('0')

    if places == 0:
        amount = amount.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        shown = str(abs(amount))
        whole, frac = shown, ''
    else:
        amount = amount.quantize(_PAISE, rounding=ROUND_HALF_UP)
        whole, _, frac = str(abs(amount)).partition('.')
        if places is None and frac == '00':
            frac = ''

    out = group_indian(whole)
    if frac:
        out = '%s.%s' % (out, frac)
    if symbol:
        out = RUPEE + out
    # -0.00 is not a thing anyone wants to read.
    if amount < 0 and abs(amount) >= (Decimal('0.005') if places != 0
                                      else Decimal('0.5')):
        out = MINUS + out
    return out


def money0(value):
    """Whole rupees. For headline totals where paise are noise."""
    return money(value, places=0)


def money2(value):
    """Always two places. For a column of figures in a document."""
    return money(value, places=2)
