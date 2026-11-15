"""Generate the sample .docx files and optionally index them for the read-only sample library.

    python scripts/build_samples.py            # writes samples/source/*.docx (skips files that exist)
    python scripts/build_samples.py --index    # also indexes them into samples/index (needs ANTHROPIC_API_KEY)

Re-generating a file changes its content hash, and so its doc id. Only use --force before re-indexing.
"""

import argparse
import dataclasses
import io
from pathlib import Path

from docx import Document
from docx.shared import Inches

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "samples" / "source"
INDEX_DIR = ROOT / "samples" / "index"


def grouped_bar_chart_png(title: str, unit: str, groups: list[str], series: dict[str, list[float]]) -> bytes:
    """A grouped bar chart like one in a real report: title, y axis with gridlines, a value on every bar,
    group labels and a legend. Drawn with Pillow and its built-in font, so it looks the same everywhere."""
    from PIL import Image, ImageDraw, ImageFont

    scale = 2  # drawn at twice the size, then shrunk, for smooth edges and text
    width, height = 1100 * scale, 620 * scale
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    def font(size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.load_default(size=size * scale)

    ink, muted, grid = (33, 37, 41), (108, 117, 125), (226, 230, 234)
    colors = [(31, 95, 139), (226, 125, 46), (76, 154, 107), (142, 103, 170)]
    left, right, top, bottom = 110 * scale, 40 * scale, 130 * scale, 80 * scale
    plot_w, plot_h = width - left - right, height - top - bottom

    draw.text((left, 30 * scale), title, font=font(30), fill=ink)
    draw.text((left, 72 * scale), unit, font=font(19), fill=muted)
    # Legend, top right
    x = width - right
    for name, color in reversed(list(zip(series, colors))):
        label_w = draw.textlength(name, font=font(19))
        x -= label_w
        draw.text((x, 74 * scale), name, font=font(19), fill=ink)
        x -= 26 * scale
        draw.rectangle((x, 77 * scale, x + 18 * scale, 95 * scale), fill=color)
        x -= 30 * scale

    top_value = max(v for values in series.values() for v in values)
    step = 20
    y_max = step * (int(top_value // step) + 1)
    for tick in range(0, y_max + 1, step):
        y = top + plot_h - plot_h * tick / y_max
        draw.line((left, y, width - right, y), fill=grid if tick else ink, width=2 * scale if tick == 0 else scale)
        label = f"{tick}"
        draw.text((left - 16 * scale - draw.textlength(label, font=font(18)), y - 11 * scale), label, font=font(18), fill=muted)

    group_w = plot_w / len(groups)
    bar_w = group_w * 0.72 / len(series)
    for g, group in enumerate(groups):
        x0 = left + g * group_w + group_w * 0.14
        for s, (name, values) in enumerate(series.items()):
            value = values[g]
            bx = x0 + s * bar_w
            by = top + plot_h - plot_h * value / y_max
            draw.rectangle((bx + 3 * scale, by, bx + bar_w - 3 * scale, top + plot_h), fill=colors[s % len(colors)])
            label = f"{value:.1f}"
            lw = draw.textlength(label, font=font(15))
            draw.text((bx + (bar_w - lw) / 2, by - 22 * scale), label, font=font(15), fill=ink)
        gw = draw.textlength(group, font=font(19))
        draw.text((left + g * group_w + (group_w - gw) / 2, top + plot_h + 18 * scale), group, font=font(19), fill=ink)

    image = image.resize((width // scale, height // scale), Image.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


REVENUE_CHART = dict(
    title="Revenue by segment and quarter, 2026",
    unit="USD millions",
    groups=["Q1", "Q2", "Q3", "Q4"],
    series={
        "Apparel": [48.2, 52.6, 61.3, 74.9],
        "Footwear": [31.5, 34.0, 36.8, 41.2],
        "Equipment": [22.4, 29.7, 33.1, 27.8],
    },
)

ANNUAL_REPORT = (
    "Fernhill Outdoor Annual Report 2026",
    [
        ("p", "Fernhill Outdoor Co. is a fictional company that designs and sells clothing, footwear and camping "
              "equipment for hiking and outdoor sports. This report covers the financial year from 1 January to "
              "31 December 2026. All amounts are in US dollars."),
        ("h1", "Letter from the Chief Executive"),
        ("p", "2026 was our strongest year yet. Revenue passed 490 million dollars for the first time, growing "
              "10.6 percent, and operating income rose by almost a third as more customers bought directly from "
              "us. Equipment was the standout: our new lightweight tent range sold out twice in the summer. "
              "We also kept our promise to use more recycled materials, which now make up 58 percent of the "
              "fabric we buy. Next year we will open six new stores and invest in a second distribution centre "
              "so that orders reach customers faster. Thank you to our 2,140 colleagues and to every customer "
              "who chose Fernhill. Maya Lindqvist, Chief Executive."),
        ("h1", "2026 at a Glance"),
        ("table", ["Measure", "2026", "2025", "Change"], [
            ["Revenue (millions)", "493.5", "446.2", "+10.6%"],
            ["Gross margin", "47.8%", "46.1%", "+1.7 pts"],
            ["Operating income (millions)", "58.3", "44.9", "+29.8%"],
            ["Net income (millions)", "41.0", "31.6", "+29.7%"],
            ["Free cash flow (millions)", "37.2", "28.4", "+31.0%"],
            ["Stores at year end", "64", "58", "+6"],
            ["Employees at year end", "2,140", "1,960", "+180"],
        ]),
        ("h1", "Financial Review"),
        ("h2", "Revenue by segment"),
        ("p", "Fernhill reports three segments. Apparel is the largest and peaks in the fourth quarter with "
              "winter jackets. Equipment grew fastest, by 15.0 percent, driven by the new tent range in the "
              "second and third quarters. Footwear grew more slowly as trail-running shoes faced strong "
              "competition and heavy discounting across the market."),
        ("table", ["Segment", "2026 (millions)", "2025 (millions)", "Growth"], [
            ["Apparel", "237.0", "214.0", "+10.7%"],
            ["Footwear", "143.5", "133.9", "+7.2%"],
            ["Equipment", "113.0", "98.3", "+15.0%"],
            ["Total", "493.5", "446.2", "+10.6%"],
        ]),
        ("chart", REVENUE_CHART,
         "Figure 1. Revenue by segment and quarter, 2026, in millions of dollars. Apparel: Q1 48.2, Q2 52.6, "
         "Q3 61.3, Q4 74.9. Footwear: Q1 31.5, Q2 34.0, Q3 36.8, Q4 41.2. Equipment: Q1 22.4, Q2 29.7, "
         "Q3 33.1, Q4 27.8."),
        ("h2", "Revenue by channel"),
        ("p", "Online sales through our own website and app made up 41 percent of revenue, up from 37 percent. "
              "Our own stores made up 23 percent and wholesale to independent outdoor retailers 36 percent. "
              "Direct sales carry a higher margin, so the shift towards them lifted profitability."),
        ("h2", "Margins and costs"),
        ("p", "Gross margin rose to 47.8 percent from 46.1 percent, helped by the shift to direct sales and "
              "lower ocean freight rates. Operating expenses grew 7.9 percent, slower than revenue, mainly from "
              "new store openings and marketing for the tent launch. Operating margin reached 11.8 percent, "
              "up from 10.1 percent."),
        ("h2", "Cash flow and balance sheet"),
        ("p", "Free cash flow was 37.2 million dollars after capital spending of 18.6 million, mostly on stores "
              "and warehouse automation. Inventory at year end was 96.4 million dollars, down 4 percent despite "
              "higher sales. Cash at year end was 64.8 million dollars, with no borrowings. The board proposes "
              "a dividend of 0.42 dollars per share."),
        ("h1", "Segment Performance"),
        ("h2", "Apparel"),
        ("p", "Apparel revenue grew 10.7 percent to 237.0 million dollars. The Ridgeline insulated jacket was "
              "again our best-selling product, and the new merino base-layer range added 9 million dollars in "
              "its first year. Returns fell to 8.1 percent of sales after we added fit guides to the website."),
        ("h2", "Footwear"),
        ("p", "Footwear revenue grew 7.2 percent to 143.5 million dollars. Hiking boots grew strongly, but "
              "trail-running shoes were flat. We reduced the number of trail-running models from 14 to 9 to "
              "focus on the best sellers."),
        ("h2", "Equipment"),
        ("p", "Equipment revenue grew 15.0 percent to 113.0 million dollars. The Aspen ultralight tent range, "
              "launched in April, sold 41,000 units. Fourth-quarter equipment sales were lower than the third "
              "quarter, as is usual after the camping season."),
        ("h1", "Sustainability"),
        ("h2", "Materials"),
        ("p", "Recycled and responsibly sourced materials made up 58 percent of the fabric we bought, up from "
              "49 percent. Our goal is 75 percent by 2028. All down used in our jackets is certified to the "
              "Responsible Down Standard."),
        ("h2", "Emissions"),
        ("p", "Emissions from our own operations and the electricity we buy fell 18 percent, as 41 of our 64 "
              "stores now run on renewable electricity. Emissions from our suppliers' factories and from "
              "shipping, which make up most of our footprint, fell 6 percent."),
        ("h2", "Repair and resale"),
        ("p", "Our repair service fixed 23,500 items in 2026, and the Fernhill Second Life resale programme sold "
              "11,200 used items. Both services are now offered in every store."),
        ("h1", "Risks"),
        ("h2", "Supply chain"),
        ("p", "About 70 percent of our products are made by suppliers in Vietnam, Bangladesh and Portugal. A "
              "disruption at a major supplier or port could delay deliveries. We now buy key products from at "
              "least two suppliers."),
        ("h2", "Weather and seasonality"),
        ("p", "A warm winter lowers demand for jackets, our most profitable products. Almost a third of annual "
              "revenue is earned in the fourth quarter."),
        ("h2", "Currency"),
        ("p", "Most costs are in US dollars, while 38 percent of revenue is earned in euros and pounds. We "
              "hedge about 70 percent of expected currency needs for the next twelve months."),
        ("h1", "Outlook for 2027"),
        ("p", "We expect revenue of 530 to 550 million dollars and an operating margin of about 12 percent. We "
              "plan to open six new stores, start building a second distribution centre in the Netherlands, and "
              "launch a footwear repair service. Capital spending is expected to be about 30 million dollars."),
    ],
)

HANDBOOK = (
    "Fernhill Employee Handbook",
    [
        ("p", "This handbook explains how we work at Fernhill Outdoor Co., a fictional company, and what you can "
              "expect from us. It applies to all employees in offices, distribution centres and stores, unless "
              "a section says otherwise. Your contract and local law take priority if they differ. Last "
              "updated January 2026."),
        ("h1", "Working Hours and Location"),
        ("h2", "Core hours"),
        ("p", "Office teams work flexible hours, but everyone is available for meetings between 10:00 and 15:00 "
              "local time. A full-time week is 37.5 hours. Store and distribution centre teams work to a rota "
              "published at least two weeks in advance."),
        ("h2", "Hybrid work"),
        ("p", "Office roles are hybrid: you work from the office at least three days a week, including your "
              "team's anchor day, and from home on the other days. Your manager can agree a different "
              "pattern for a fixed period, for example after parental leave."),
        ("h2", "Working from abroad"),
        ("p", "You can work from another country for up to 20 working days a year, for example to extend a "
              "visit to family. Ask your manager and the People team at least four weeks before you go, so we "
              "can check tax and visa rules. Some countries are not allowed for security reasons."),
        ("h1", "Time Off"),
        ("h2", "Annual leave"),
        ("p", "Full-time employees get 25 days of paid annual leave a year plus public holidays, rising to 28 "
              "days after five years. Leave runs from January to December. You can carry up to 5 unused days "
              "into the next year; they must be used by the end of March. Book leave in the HR portal at least "
              "two weeks ahead for anything longer than three days."),
        ("h2", "Sick leave"),
        ("p", "Tell your manager before your shift or start time if you are ill. You can self-certify for up to "
              "3 days; after that we need a note from a doctor. You get full pay for up to 10 sick days a "
              "year, and half pay for a further 20 days."),
        ("h2", "Parental leave"),
        ("p", "Every parent, whatever their gender and however they became a parent, gets 16 weeks of parental "
              "leave at full pay, to be taken within the first year after the birth or adoption. Birth parents "
              "can take a further 10 weeks at statutory pay. Tell the People team at least 15 weeks before the "
              "due date or placement. When you return, you can work 80 percent of your hours for full pay for "
              "the first 4 weeks."),
        ("h2", "Other leave"),
        ("table", ["Type", "Paid days", "Notes"], [
            ["Bereavement", "Up to 10", "For a partner, child, parent or sibling; 3 days for other relatives"],
            ["Volunteering", "2 per year", "For registered charities and community projects"],
            ["Moving home", "1 per year", ""],
            ["Jury duty", "As needed", "Full pay; tell your manager when you are summoned"],
        ]),
        ("h1", "Pay and Benefits"),
        ("h2", "Pay"),
        ("p", "You are paid monthly, on the last working day of the month. Pay is reviewed every April based on "
              "your performance and market rates. Payslips are in the HR portal."),
        ("h2", "Pension"),
        ("p", "We match your pension contributions up to 6 percent of your salary. You are enrolled "
              "automatically after your first month and can change your contribution at any time."),
        ("h2", "Health and wellbeing"),
        ("p", "Private health insurance covers you from your first day, and you can add your partner and "
              "children at a reduced rate. The employee assistance line offers free, confidential counselling "
              "24 hours a day."),
        ("h2", "Gear allowance and discount"),
        ("p", "You get 40 percent off Fernhill products, for yourself and up to two friends or family members. "
              "Each year you also get a 500 dollar gear allowance to spend on Fernhill products, because we "
              "think people who make outdoor gear should use it."),
        ("h1", "Expenses and Travel"),
        ("h2", "Before you spend"),
        ("p", "Get your manager's approval before you book travel or spend more than 250 dollars. Use the "
              "company card where you have one; otherwise pay yourself and claim the money back."),
        ("h2", "Travel"),
        ("p", "Book travel through the travel portal. Take the train for journeys under four hours. Flights "
              "are economy class, or premium economy for flights over eight hours. Hotels should cost no more "
              "than the city limit shown in the portal."),
        ("h2", "Meals and daily allowance"),
        ("table", ["Trip", "Daily meal allowance", "Notes"], [
            ["Same country, overnight", "60 dollars", "Breakfast included in the hotel is not claimed"],
            ["Abroad", "85 dollars", "Converted at the rate on the day of travel"],
            ["Day trip over 10 hours", "25 dollars", "No overnight stay"],
        ]),
        ("h2", "Claiming expenses"),
        ("p", "Submit claims in the expenses app within 30 days, with a photo of each receipt. Claims approved "
              "by the 20th of the month are paid with that month's salary. Alcohol is not reimbursed, except "
              "at events approved in advance by a director."),
        ("h1", "Equipment and Security"),
        ("h2", "Laptops and phones"),
        ("p", "Office employees receive a laptop, and a phone if their role needs one. Do not install software "
              "that is not in the company app store. Return all equipment on your last day."),
        ("h2", "Passwords and sign-in"),
        ("p", "Use the company password manager and turn on two-step sign-in for every work account. Never "
              "share your password, even with IT: the IT team will never ask for it."),
        ("h2", "Reporting a security incident"),
        ("p", "If you lose a device, click a suspicious link or think customer data may have been exposed, "
              "report it to the IT service desk within one hour, at any time of day. You will not be blamed "
              "for reporting a mistake quickly."),
        ("h1", "Conduct"),
        ("h2", "Code of conduct"),
        ("p", "Treat colleagues, customers and suppliers with respect. Harassment, discrimination and bullying "
              "are not tolerated. Gifts from suppliers worth more than 50 dollars must be declared to your "
              "manager."),
        ("h2", "Raising a concern"),
        ("p", "If you see something wrong, talk to your manager or the People team. You can also use the "
              "confidential speak-up line, run by an independent company, anonymously if you prefer. Nobody "
              "will be treated badly for raising a concern in good faith."),
    ],
)

# File name (shown as the document's title in the library) -> content. The doc id is the name as a slug
# plus a content hash: "fernhill-annual-report-2026-<hash>".
SAMPLES = {
    "Fernhill Annual Report 2026": ANNUAL_REPORT,
    "Fernhill Employee Handbook": HANDBOOK,
}


def build_docx(path: Path, title: str, items: list) -> None:
    doc = Document()
    doc.add_heading(title, level=0)
    for kind, *args in items:
        if kind in ("h1", "h2"):
            doc.add_heading(args[0], level=int(kind[1]))
        elif kind == "p":
            doc.add_paragraph(args[0])
        elif kind == "table":
            header, rows = args
            table = doc.add_table(rows=1, cols=len(header), style="Table Grid")
            for cell, text in zip(table.rows[0].cells, header):
                cell.text = text
            for row in rows:
                for cell, text in zip(table.add_row().cells, row):
                    cell.text = text
        elif kind == "chart":
            chart, caption = args
            doc.add_picture(io.BytesIO(grouped_bar_chart_png(**chart)), width=Inches(6))
            doc.add_paragraph(caption)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="overwrite .docx files that already exist")
    parser.add_argument("--index", action="store_true", help="also index the sample files")
    parser.add_argument("--no-llm", action="store_true", help="with --index: skip summaries (for testing)")
    parser.add_argument("--out", type=Path, default=INDEX_DIR, help="with --index: where to write the index")
    args = parser.parse_args()

    for name, (title, items) in SAMPLES.items():
        path = SOURCE_DIR / f"{name}.docx"
        if path.exists() and not args.force:
            print(f"kept     {path.relative_to(ROOT)}")
        else:
            build_docx(path, title, items)
            print(f"wrote    {path.relative_to(ROOT)}")

    if args.index:
        from toc_rag.config import get_settings
        from toc_rag.indexing import index_document
        from toc_rag.storage import Store

        settings = dataclasses.replace(get_settings(), data_dir=args.out)
        if not args.no_llm and not settings.index_model:
            raise SystemExit("Set TOC_RAG_PROVIDER and TOC_RAG_INDEX_MODEL (and its key) in .env, or pass --no-llm.")
        store = Store(args.out)
        for path in sorted(SOURCE_DIR.glob("*.docx")):
            index = index_document(path, store, settings, use_llm=not args.no_llm)
            print(f"indexed  {index.doc_id}: {sum(1 for _ in index.root.walk())} nodes, {len(index.images)} images")


if __name__ == "__main__":
    main()
