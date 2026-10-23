"""Workbook building for the data the app exports.

The exports used to be csv.writer output: a header row, some rows, and for
payroll a TOTALS line padded with eighteen empty strings to reach the right
column. Opened in Excel that is naked text — money in a column that sorts
alphabetically, a header that scrolls away on the second screen of rows,
and columns narrow enough to show ####.

Everything here is layout. The numbers come from the same code the screens
use; nothing is recalculated on the way out, because an export that does
its own arithmetic is an export that can disagree with the app.

openpyxl rather than pandas or xlsxwriter: it reads as well as writes, so
the tests open the finished file and assert on real cells instead of
trusting that the writer did what it was told.
"""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# One accent, the app's own, and greys that print legibly in mono.
ACCENT = '1E40AF'
HEADER_BG = 'F1F5F9'
RULE = 'CBD5E1'
MUTED = '64748B'

# Indian digit grouping is 2,2,3 — ₹12,34,567 and not ₹1,234,567. Excel
# takes the pattern literally, so this is written out rather than relying
# on a locale the opener's machine may not have.
MONEY = '[$₹-en-IN]##,##,##0.00'
MONEY_0 = '[$₹-en-IN]##,##,##0'
DATE = 'dd-mmm-yyyy'

_thin = Side(style='thin', color=RULE)
BORDER = Border(bottom=_thin)


def _title_block(ws, title, subtitle, company, width):
    """The three lines above the table: who, what, and when.

    An exported file outlives the screen it came from. A month-end payroll
    sheet mailed to an accountant has to say which company and which month
    it is without the covering email.
    """
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    cell = ws.cell(row=1, column=1, value=(company or 'SmartWorker'))
    cell.font = Font(size=15, bold=True, color=ACCENT)

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=width)
    cell = ws.cell(row=2, column=1, value=title)
    cell.font = Font(size=11, bold=True)

    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=width)
    cell = ws.cell(row=3, column=1, value=subtitle)
    cell.font = Font(size=9, italic=True, color=MUTED)
    ws.row_dimensions[1].height = 21
    ws.row_dimensions[3].height = 14
    return 5                      # first body row: 4 is left blank


def write_sheet(ws, columns, rows, title, subtitle, company, totals=None):
    """One table: title block, header, body, and an optional totals line.

    `columns` is a list of (heading, key, kind, width). `kind` drives the
    number format — 'money', 'money0', 'int', 'date' or None for text — so
    a column is described once and every cell in it agrees.
    """
    head_row = _title_block(ws, title, subtitle, company, len(columns))

    for i, (heading, _key, _kind, width) in enumerate(columns, start=1):
        cell = ws.cell(row=head_row, column=i, value=heading)
        cell.font = Font(bold=True, size=9)
        cell.fill = PatternFill('solid', fgColor=HEADER_BG)
        cell.alignment = Alignment(vertical='center', wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[head_row].height = 28

    for r, row in enumerate(rows, start=head_row + 1):
        for i, (_heading, key, kind, _w) in enumerate(columns, start=1):
            value = row.get(key)
            cell = ws.cell(row=r, column=i, value=value)
            cell.font = Font(size=9)
            if kind == 'money':
                cell.number_format = MONEY
            elif kind == 'money0':
                cell.number_format = MONEY_0
            elif kind == 'date':
                cell.number_format = DATE
            elif kind == 'int':
                cell.alignment = Alignment(horizontal='right')

    if totals:
        r = head_row + len(rows) + 1
        for i, (_heading, key, kind, _w) in enumerate(columns, start=1):
            value = totals.get(key)
            cell = ws.cell(row=r, column=i, value=value)
            cell.font = Font(bold=True, size=9)
            cell.fill = PatternFill('solid', fgColor=HEADER_BG)
            if kind == 'money':
                cell.number_format = MONEY
            elif kind == 'money0':
                cell.number_format = MONEY_0

    # Freeze under the header, so scrolling a thousand rows never loses the
    # column names, and turn on filters — the first thing anyone does with
    # a sheet like this is narrow it to one department.
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = '%s%d:%s%d' % (
            'A', head_row, get_column_letter(len(columns)),
            head_row + len(rows))
    ws.sheet_view.showGridLines = False
    return ws


def new_workbook():
    wb = Workbook()
    wb.remove(wb.active)          # drop the default empty 'Sheet'
    return wb


def to_bytes(wb):
    import io
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
