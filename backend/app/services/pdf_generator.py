from decimal import Decimal
from io import BytesIO
from typing import Dict, Any, List
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable


MONTH_NAMES = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
]


def _fmt(amount: Decimal) -> str:
    return f"₹{amount:,.2f}"


def generate_monthly_pdf(report_data: Dict[str, Any]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, spaceAfter=6)
    heading_style = ParagraphStyle('Heading2', parent=styles['Heading2'], fontSize=13, spaceAfter=8, spaceBefore=12)
    normal_style = styles['Normal']

    year = report_data['year']
    month = report_data['month']
    month_name = MONTH_NAMES[month] if 1 <= month <= 12 else str(month)

    elements.append(Paragraph(f"Monthly Financial Report", title_style))
    elements.append(Paragraph(f"{month_name} {year}", ParagraphStyle('Subtitle', parent=normal_style, fontSize=14, textColor=colors.grey, spaceAfter=12)))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey, spaceAfter=12))

    elements.append(Paragraph("Summary", heading_style))
    summary_data = [
        ['Total Income', _fmt(report_data['total_income'])],
        ['Total Expenses', _fmt(report_data['total_expenses'])],
        ['Net Cash Flow', _fmt(report_data['net_cashflow'])],
        ['Transactions', str(report_data['transaction_count'])],
    ]
    t = Table(summary_data, colWidths=[3*inch, 2.5*inch])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, -1), (-1, -1), 0.5, colors.lightgrey),
    ]))
    elements.append(t)

    if report_data['category_breakdown']:
        elements.append(Paragraph("Category Breakdown", heading_style))
        cat_data = [['Category', 'Amount', '% of Expenses']]
        total_exp = report_data['total_expenses']
        for c in report_data['category_breakdown']:
            pct = float(c['amount'] / total_exp * 100) if total_exp > 0 else 0
            cat_data.append([c['category'], _fmt(c['amount']), f"{pct:.1f}%"])
        t = Table(cat_data, colWidths=[2.5*inch, 2*inch, 1.5*inch])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.95, 0.95, 0.95)),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        elements.append(t)

    if report_data['top_merchants']:
        elements.append(Paragraph("Top Merchants", heading_style))
        merch_data = [['Merchant', 'Total Spent']]
        for m in report_data['top_merchants']:
            merch_data.append([m['merchant'][:40], _fmt(m['total_spent'])])
        t = Table(merch_data, colWidths=[3.5*inch, 2.5*inch])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.95, 0.95, 0.95)),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        elements.append(t)

    if report_data['recurring_expenses']:
        elements.append(Paragraph("Recurring Expenses", heading_style))
        rec_data = [['Description', 'Amount', 'Category']]
        for r in report_data['recurring_expenses']:
            rec_data.append([r['description'][:40], _fmt(r['amount']), r['category'] or ''])
        t = Table(rec_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.95, 0.95, 0.95)),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        elements.append(t)

    if report_data['budget_status']:
        elements.append(Paragraph("Budget Status", heading_style))
        bud_data = [['Category', 'Budget', 'Spent', 'Remaining', 'Utilization']]
        for b in report_data['budget_status']:
            bud_data.append([
                b['category'],
                _fmt(b['monthly_cap']),
                _fmt(b['spent']),
                _fmt(b['remaining']),
                f"{b['utilization']:.0f}%",
            ])
        t = Table(bud_data, colWidths=[1.5*inch, 1.2*inch, 1.2*inch, 1.2*inch, 1*inch])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.95, 0.95, 0.95)),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        elements.append(t)

    if report_data['savings_progress']:
        elements.append(Paragraph("Savings Goal Progress", heading_style))
        sav_data = [['Goal', 'Target', 'Current', 'Progress']]
        for s in report_data['savings_progress']:
            sav_data.append([
                s['name'],
                _fmt(s['target_amount']),
                _fmt(s['current_amount']),
                f"{s['progress_percent']:.1f}%",
            ])
        t = Table(sav_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1*inch])
        t.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.95, 0.95, 0.95)),
            ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ]))
        elements.append(t)

    if not any([
        report_data['category_breakdown'],
        report_data['top_merchants'],
        report_data['recurring_expenses'],
        report_data['budget_status'],
        report_data['savings_progress'],
    ]):
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("No transaction data for this period.", ParagraphStyle('Empty', parent=normal_style, textColor=colors.grey, alignment=1)))

    doc.build(elements)
    return buffer.getvalue()
