"""Bill PDF rendering (fpdf2). Stored via the Storage abstraction."""
from fpdf import FPDF

MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


def rupees(paise: int) -> str:
    """Indian digit grouping: 5018500 paise -> '50,185.00' -> we drop .00 when zero."""
    sign = "-" if paise < 0 else ""
    paise = abs(paise)
    r, p = divmod(paise, 100)
    s = str(r)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return f"{sign}{s}" if p == 0 else f"{sign}{s}.{p:02d}"


def period_label(year: int, month: int) -> str:
    return f"{MONTHS[month]} {year}"


def render_bill_pdf(bill, unit, period, tenant_name: str | None) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "Building Bills", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, f"{unit.name}" + (f" - {tenant_name}" if tenant_name else ""),
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, period_label(period.year, period.month), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    def row(label, value, bold=False):
        pdf.set_font("Helvetica", "B" if bold else "", 11)
        pdf.cell(120, 8, label, border="B")
        pdf.cell(60, 8, value, border="B", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 9, "Electricity", new_x="LMARGIN", new_y="NEXT")
    row("Previous reading", f"{bill.prev_reading} kWh")
    row("Current reading", f"{bill.curr_reading} kWh")
    row("Units consumed", f"{bill.own_units} kWh")
    row("Common-area share", f"{bill.common_share_units} kWh")
    if bill.ev_units:
        row("EV charging units", f"{bill.ev_units} kWh")
    row("Billable units", f"{bill.billable_units} kWh")
    row("Rate", f"Rs {rupees(bill.rate_paise)} / unit")
    row("Electricity bill", f"Rs {rupees(bill.electricity_paise)}", bold=True)
    pdf.ln(4)

    if bill.charge_lines:
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 9, "Other charges", new_x="LMARGIN", new_y="NEXT")
        for line in bill.charge_lines:
            row(line.label, f"Rs {rupees(line.amount_paise)}")
        pdf.ln(4)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(120, 10, "TOTAL AMOUNT")
    pdf.cell(60, 10, f"Rs {rupees(bill.total_paise)}", align="R",
             new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
