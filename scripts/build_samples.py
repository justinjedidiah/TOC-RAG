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

def P(text: str) -> tuple[str, str]:
    """A paragraph, written across lines here and joined into one."""
    return ("p", " ".join(text.split()))


# Each leaf section is written to be at least ~110 words, so the tree keeps its levels: merging joins sibling
# sections under 150 tokens (about 600 characters) into one, which would flatten a short document.
ANNUAL_REPORT = (
    "Fernhill Outdoor Annual Report 2026",
    [
        P("""Fernhill Outdoor Co. is a fictional company that designs and sells clothing, footwear and camping
            equipment for hiking and outdoor sports. This report covers the financial year from 1 January to
            31 December 2026. All amounts are in US dollars unless stated otherwise, and comparisons are with
            the 2025 financial year."""),
        ("h1", "Letter from the Chief Executive"),
        P("""2026 was our strongest year yet. Revenue passed 490 million dollars for the first time, growing
            10.6 percent, and operating income rose by almost a third as more customers bought directly from
            us. Equipment was the standout: our new lightweight tent range sold out twice in the summer, and
            the segment grew faster than any other. We also kept our promise to use more recycled materials,
            which now make up 58 percent of the fabric we buy."""),
        P("""Not everything went to plan. Trail-running shoes faced heavy discounting across the market, and we
            cut our range rather than chase sales at a loss. A warm November in Europe slowed jacket sales for
            several weeks. Both reminded us why we keep a strong balance sheet: we ended the year with 64.8
            million dollars in cash and no borrowings."""),
        P("""Next year we will open six new stores and start building a second distribution centre, in the
            Netherlands, so that orders reach European customers in two days instead of four. Thank you to our
            2,140 colleagues and to every customer who chose Fernhill. Maya Lindqvist, Chief Executive."""),
        ("h1", "2026 at a Glance"),
        P("""The table below sums up the year. Every measure improved on 2025. Revenue grew in all three
            segments and all three regions, the gross margin widened as more sales came through our own
            website, app and stores, and free cash flow covered both the year's investment and the proposed
            dividend. Definitions of each measure are given in the Financial Review."""),
        ("table", ["Measure", "2026", "2025", "Change"], [
            ["Revenue (millions)", "493.5", "446.2", "+10.6%"],
            ["Gross margin", "47.8%", "46.1%", "+1.7 pts"],
            ["Operating income (millions)", "58.3", "44.9", "+29.8%"],
            ["Operating margin", "11.8%", "10.1%", "+1.7 pts"],
            ["Net income (millions)", "41.0", "31.6", "+29.7%"],
            ["Free cash flow (millions)", "37.2", "28.4", "+31.0%"],
            ["Stores at year end", "64", "58", "+6"],
            ["Employees at year end", "2,140", "1,960", "+180"],
        ]),
        ("h1", "Strategy"),
        ("h2", "Our plan for 2025 to 2028"),
        P("""In 2025 we set out a four-year plan with three priorities: sell more directly to customers, lead the
            market in lightweight camping equipment, and make products that last longer and can be repaired or
            resold. Behind each priority sit measurable targets for 2028: direct sales above two thirds of
            revenue, equipment revenue of 150 million dollars, and 75 percent recycled or responsibly sourced
            fabric. The board reviews progress against these targets twice a year, and part of executive pay
            depends on them, as described under Governance.
            Two years in, we are ahead of plan on direct sales and recycled materials and on track for equipment.
            The plan was shaped by a survey of 12,000 customers, who told us they wanted lighter gear that lasts longer."""),
        ("h2", "Progress on our priorities"),
        ("h3", "Selling directly to customers"),
        P("""Direct sales, through our website, app and own stores, rose to 64 percent of revenue from 60
            percent. The relaunched app now has 1.3 million active users, and app customers buy 2.4 times a year
            on average, against 1.6 times for website-only customers. We opened seven stores and closed one,
            ending the year with 64. Wholesale remains important to reach new customers, especially in
            countries where we have no stores, but we now sell to fewer, larger retailers.
            Customers who buy directly also tell us more: product reviews and repair requests now feed straight into our design teams.
            The app also lets customers book a boot fitting, check stock in a nearby store and register products for the five-year guarantee."""),
        ("h3", "Leading in lightweight equipment"),
        P("""The Aspen ultralight tent range, launched in April, was the most successful launch in our history,
            selling 41,000 units. Its two-person tent weighs 1.1 kilograms, lighter than any competitor at the
            same price. We doubled the equipment design team to 36 people and opened a test centre in Colorado
            where every tent spends a week in wind and rain machines before it goes on sale. Equipment revenue
            reached 113.0 million dollars, on track for the 2028 target.
            A one-person version and a four-season version will join the range in 2027.
            Independent reviewers named the Aspen 2 the best lightweight tent of the year in three outdoor magazines."""),
        ("h3", "Making products that last"),
        P("""We want customers to keep Fernhill products for longer. Every product now carries a five-year
            guarantee, up from two years, and our repair service fixed 23,500 items. The Fernhill Second Life
            programme buys back used products for store credit and resells them, and sold 11,200 items in 2026.
            Repair and resale together earned 2.9 million dollars, a small amount, but customers who use them
            are twice as likely to buy from us again within a year.
            In 2027 we will add repair counters to the ten stores that do not yet have one.
            Repairs are free within the guarantee and charged at cost after it, and the most common repairs are broken zips and torn seams."""),
        ("h1", "Financial Review"),
        ("h2", "Revenue by segment"),
        P("""Fernhill reports three segments. Apparel is the largest and peaks in the fourth quarter with winter
            jackets. Equipment grew fastest, by 15.0 percent, from 98.3 to 113.0 million dollars, driven by the
            new tent range in the second and third quarters. Footwear grew more slowly as trail-running shoes
            faced strong competition and heavy discounting across the market."""),
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
        P("""Online sales through our own website and app made up 41 percent of revenue, up from 37 percent.
            Our own stores made up 23 percent, the same as last year, and wholesale to independent outdoor
            retailers and department stores 36 percent, down from 40 percent. Direct sales carry a higher
            margin, because we keep the retailer's share, so the shift towards them lifted profitability.
            Online orders are fulfilled from our distribution centre in Ohio, and returns fell to 8.1 percent
            of online sales after we added fit guides to every product page.
            Mobile phones now account for 71 percent of online orders.
            Online customers also spent more per order, 128 dollars on average, up from 119 dollars."""),
        ("h2", "Revenue by region"),
        P("""North America is still our largest market, but Asia-Pacific grew fastest, by 23.2 percent, after we
            opened our first two stores in Japan and started selling through a large Australian outdoor
            retailer. Europe grew 10.6 percent, held back by the warm November, which delayed jacket sales into
            December and January. Revenue earned in euros and pounds was 38 percent of the total, the source of
            our currency risk described under Risks.
            In 2027 we will open our first store in South Korea and expand wholesale in Australia and New Zealand."""),
        ("table", ["Region", "2026 (millions)", "2025 (millions)", "Growth"], [
            ["North America", "256.6", "236.5", "+8.5%"],
            ["Europe", "187.5", "169.6", "+10.6%"],
            ["Asia-Pacific", "49.4", "40.1", "+23.2%"],
            ["Total", "493.5", "446.2", "+10.6%"],
        ]),
        ("h2", "Profitability"),
        ("h3", "Gross margin"),
        P("""Gross margin rose to 47.8 percent from 46.1 percent. About 1.2 points came from the shift to direct
            sales and about 0.8 points from lower ocean freight rates, which returned to normal levels after two
            expensive years. Heavier discounting of trail-running shoes took away about 0.3 points. Gross
            profit, revenue minus the cost of the products we sold, was 235.9 million dollars, up from 205.7
            million. We expect freight costs to stay roughly flat in 2027.
            Each additional point of gross margin is worth about 4.9 million dollars of gross profit at this year's revenue, which is why we watch freight rates and discounting closely.
            Full-price sales made up 78 percent of the total, up from 74 percent, as we ran fewer sales events."""),
        ("h3", "Operating expenses"),
        P("""Operating expenses grew 10.4 percent to 177.6 million dollars, slightly slower than revenue, so
            operating margin reached 11.8 percent, up from 10.1 percent. Most of the increase came from new
            stores and from marketing for the Aspen tent launch. Distribution costs grew more slowly than sales
            thanks to new sorting machines in the Ohio warehouse. The table shows operating expenses by type.
            Head office costs grew 11.8 percent, mostly from a larger design team, and we expect them to grow more slowly than revenue in 2027."""),
        ("table", ["Expense", "2026 (millions)", "2025 (millions)"], [
            ["Stores and selling", "82.4", "75.0"],
            ["Marketing", "38.1", "33.2"],
            ["Distribution", "31.6", "29.8"],
            ["General and administrative", "25.5", "22.8"],
            ["Total", "177.6", "160.8"],
        ]),
        ("h2", "Cash flow and balance sheet"),
        ("h3", "Cash flow"),
        P("""Cash generated by operations was 55.8 million dollars. Capital spending was 18.6 million, mostly on
            new stores and warehouse automation, leaving free cash flow of 37.2 million, up 31.0 percent. We
            paid a dividend of 14.4 million for 2025 and bought no shares back. Cash at year end was 64.8
            million dollars, up from 42.0 million, and we have no borrowings. An unused credit line of 80
            million dollars is available until 2029 if we need it.
            Our cash is held with three large banks, in accounts that can be withdrawn at short notice.
            Interest earned on cash balances was 2.1 million dollars, up from 1.3 million."""),
        ("h3", "Inventory"),
        P("""Inventory at year end was 96.4 million dollars, down 4 percent despite higher sales. We now plan
            stock for each store weekly instead of monthly and moved slow-selling trail-running shoes to our
            outlet stores earlier in the season. Inventory turned 2.7 times in the year, up from 2.4. Less money
            tied up in stock was the main reason cash flow improved more than profit did. We aim to keep
            inventory growth below sales growth in 2027 as well.
            Older stock is offered first to our outlet stores and then donated to outdoor charities; we do not destroy unsold products.
            Stock of winter jackets at year end was lower than last year, so we expect fewer discounts in the January sales."""),
        ("h3", "Dividend and use of cash"),
        P("""The board proposes a dividend of 0.42 dollars per share for 2026, up from 0.36 dollars, which would
            cost about 16.8 million dollars and be paid in May 2027. Our policy is to pay out about 40 percent
            of net income as dividends. The rest of our cash will fund the second distribution centre, new
            stores and the equipment test centre. We will consider buying back shares only if cash stays above
            what those plans need.
            Shareholders will vote on the dividend at the annual meeting in May 2027.
            Since we started paying dividends in 2019, the dividend has grown every year."""),
        ("h1", "Segment Performance"),
        ("h2", "Apparel"),
        ("h3", "Jackets and insulation"),
        P("""Apparel revenue grew 10.7 percent to 237.0 million dollars, and jackets made up just under half of
            it. The Ridgeline insulated jacket was again our best-selling product, with 182,000 sold. We moved
            all insulated jackets to recycled polyester fill and certified down, at no extra cost to customers.
            The warm November in Europe delayed jacket sales, but most of them came back in December, so
            fourth-quarter apparel revenue still reached a record 74.9 million dollars.
            Rain jackets also had a good year after the wet spring in the United Kingdom, and sales of children's jackets doubled after we added sizes for children from four years old.
            Jackets carry our highest margins, so their strong fourth quarter lifted profit more than revenue."""),
        ("h3", "Base layers and everyday wear"),
        P("""The new merino base-layer range added 9 million dollars in its first year, mostly through our own
            website, where customers who bought one piece often came back for a second. Everyday wear, such as
            fleeces and walking trousers sold for city use, grew 6 percent. Returns of apparel fell to 8.1
            percent of sales after we added fit guides, body-shape photos and customer size ratings to the
            website. For 2027 we plan a women's cut of every base layer.
            Merino is a natural wool that keeps its warmth when wet and does not hold smells, which makes it popular for multi-day hikes.
            All the merino comes from farms certified to the Responsible Wool Standard in Australia and New Zealand."""),
        ("h2", "Footwear"),
        ("h3", "Hiking boots"),
        P("""Footwear revenue grew 7.2 percent to 143.5 million dollars, all of it from hiking boots, which grew
            13 percent. The Summit mid-height boot, made with a recycled rubber sole, became our best-selling
            shoe. Boots sell best in our own stores, where customers can try them on and have them fitted, so
            new stores helped. In 2027 we will launch a footwear repair service that replaces worn soles,
            starting in ten stores in the United States and Germany.
            Every boot now comes with a free fitting in store, and online customers can exchange a size for free.
            Boots are also the footwear product customers most often bring back for repair, which is why the new repair service starts with them."""),
        ("h3", "Trail-running shoes"),
        P("""Trail-running shoe revenue was flat at 41 million dollars. Several large brands cut prices sharply
            during the year, and we chose not to follow them below the point where we would lose money. We
            reduced the number of trail-running models from 14 to 9 to focus on the best sellers, and sold the
            rest through our outlet stores. A redesigned range, lighter and with a wider toe box that customers
            asked for, goes on sale in March 2027.
            Trail-running shoes made up 29 percent of footwear revenue, down from 31 percent.
            Despite the price competition, customer ratings for our trail-running shoes stayed among the highest in the market, at 4.6 out of 5."""),
        ("h2", "Equipment"),
        ("h3", "Tents"),
        P("""Equipment revenue grew 15.0 percent to 113.0 million dollars, the fastest of our three segments.
            Tents led the way: the Aspen ultralight range, launched in April, sold 41,000 units and sold out
            twice in the summer. We added a second supplier in Vietnam to meet demand. Fourth-quarter equipment
            sales were lower than the third quarter, as is usual after the camping season, which is why the
            segment's quarterly revenue peaks in the third quarter.
            Tents made up 61 million dollars of equipment revenue, up 21 percent, and we sold more two-person tents than any other size.
            Tent returns were just 2.3 percent of sales, the lowest of any product group."""),
        ("h3", "Packs and accessories"),
        P("""Backpacks, sleeping bags and smaller accessories such as stoves and headlamps made up 52 million
            dollars of equipment revenue, up 9 percent. The Trailhead 45 litre pack won two industry awards. We
            stopped selling our cheapest sleeping bags, which had the highest return rates, and replaced them
            with a mid-priced range filled with recycled insulation. Accessories are often bought alongside a
            tent, so they also benefited from the Aspen launch.
            Packs are the equipment product most often brought to our repair counters, so every new pack has replaceable buckles and straps.
            Accessories also make good gifts, and they sell strongly in December."""),
        ("h1", "Operations"),
        ("h2", "Stores"),
        P("""We opened seven stores in 2026, three in the United States, two in Japan, one in the United Kingdom
            and one in Canada, and closed one in a shopping mall where footfall had fallen. That leaves 64
            stores at year end. New stores are smaller than our older ones, about 400 square metres, with a
            repair counter and a space for local hiking clubs to meet. Sales per square metre in stores open for
            more than a year grew 5 percent. Six more stores will open in 2027.
            Every store also offers free collection of online orders, which brought 380,000 customers into our stores in 2026.
            Store staff run free guided walks and introductory camping evenings, which drew 26,000 people in 2026."""),
        ("h2", "Distribution and logistics"),
        P("""All online orders and store deliveries in North America leave from our distribution centre in
            Columbus, Ohio, and European orders from a partner warehouse near Rotterdam. In 2026 we installed
            automatic sorting machines in Ohio, which cut the cost of handling each order by 14 percent. Orders
            in Europe take four days on average to arrive. A second distribution centre of our own, in the
            Netherlands, will start construction in 2027 and open in 2028, bringing that down to two days.
            We ship to customers in 31 countries, and next-day delivery is available in the largest cities of the United States and Canada.
            Returns are processed within three days of reaching the warehouse."""),
        ("h2", "Our people"),
        P("""We ended the year with 2,140 employees, up from 1,960, most of the new jobs in stores and in
            equipment design. 47 percent of our employees and 42 percent of managers are women. Voluntary staff
            turnover fell to 14 percent from 17 percent, and 81 percent of employees took part in our annual
            survey, with 76 percent saying they would recommend Fernhill as a place to work. Every employee
            received a 500 dollar gear allowance, and we raised the minimum hourly wage in our stores to 19
            dollars in the United States.
            We also trained 120 store employees as product specialists through our internal programme."""),
        ("h1", "Sustainability"),
        ("h2", "Materials"),
        P("""Recycled and responsibly sourced materials made up 58 percent of the fabric we bought, up from 49
            percent. Our goal is 75 percent by 2028. All down used in our jackets is certified to the
            Responsible Down Standard, and all wool to the Responsible Wool Standard. We stopped using
            fluorinated water repellents, known as PFAS, in every product in July 2026, a year earlier than we
            had promised. Recycled fabrics cost on average 6 percent more, which we absorbed in our margins.
            Most of our recycled polyester is made from plastic bottles, and in 2026 we began testing fabric recycled from old Fernhill jackets.
            Our product designers now receive a materials score for every new product, which counts towards their own targets."""),
        ("h2", "Emissions"),
        P("""Emissions from our own operations and the electricity we buy fell 18 percent, as 41 of our 64
            stores now run on renewable electricity. Emissions from our suppliers' factories and from shipping,
            which make up most of our footprint, fell 6 percent, mainly because more goods travelled by sea
            instead of air. Our target is to halve emissions from our own operations and cut supplier and
            shipping emissions by 30 percent by 2030, compared with 2022.
            The table shows emissions in tonnes of carbon dioxide equivalent."""),
        ("table", ["Emissions (tonnes of CO2 equivalent)", "2026", "2025", "Change"], [
            ["Own operations and electricity (scopes 1 and 2)", "8,900", "10,850", "-18%"],
            ["Suppliers, shipping and products (scope 3)", "212,000", "225,500", "-6%"],
        ]),
        ("h2", "Suppliers and factory audits"),
        P("""About 70 percent of our products are made by 46 supplier factories in Vietnam, Bangladesh and
            Portugal. Every factory is audited at least once a year by an independent firm, unannounced, against
            our supplier code, which covers wages, working hours, safety and the right to join a union. In 2026
            the audits found 112 issues, mostly about overtime and fire exits; 97 were fixed by year end and
            the rest have dated plans. We stopped working with one factory that refused to let auditors in.
            We publish the names and addresses of all our supplier factories on our website, updated every six months.
            Wages at our suppliers are checked against local living-wage estimates, not only against the legal minimum."""),
        ("h1", "Governance"),
        ("h2", "Board of directors"),
        P("""The board has seven directors: the chair, the chief executive, the chief financial officer and four
            independent directors. Three of the seven are women. The board met nine times in 2026, and every
            director attended at least eight meetings. Its audit committee oversees financial reporting and
            risk, and its people committee sets executive pay. All directors stand for re-election at the annual
            meeting each May.
            Directors are paid a fixed fee and receive no bonus or shares, so that they can judge the executives' performance independently."""),
        ("table", ["Director", "Role", "Joined"], [
            ["Thomas Okafor", "Chair, independent", "2019"],
            ["Maya Lindqvist", "Chief Executive", "2021"],
            ["Daniel Reyes", "Chief Financial Officer", "2022"],
            ["Priya Nair", "Independent, chairs the audit committee", "2020"],
            ["Hannah Weber", "Independent, chairs the people committee", "2023"],
            ["Kenji Watanabe", "Independent", "2024"],
            ["Laura Bianchi", "Independent", "2026"],
        ]),
        ("h2", "Executive pay"),
        P("""The chief executive's total pay for 2026 was 2.6 million dollars: a salary of 850,000 dollars, an
            annual bonus of 940,000 dollars and shares worth about 810,000 dollars that vest in 2029 if targets
            are met. Half of the annual bonus depends on operating income, a quarter on direct sales and a
            quarter on sustainability targets, including recycled materials and emissions. The chief
            executive's pay was 48 times the median pay of our employees, down from 52 times in 2025.
            Shares granted to executives must be held for at least two years after they vest.
            The people committee compares executive pay with ten similar companies in the outdoor and sports market every year."""),
        ("h1", "Risks"),
        ("h2", "Supply chain"),
        P("""About 70 percent of our products are made by suppliers in Vietnam, Bangladesh and Portugal. A
            disruption at a major supplier or port, from a natural disaster, political unrest or a pandemic,
            could delay deliveries for months. We now buy every one of our top 50 products from at least two
            suppliers in different countries, and we keep eight weeks of stock of our best sellers. Shipping
            prices can also change quickly, which affects our gross margin.
            In 2026 a typhoon closed a port in Vietnam for nine days; because of these measures, no store ran out of a top-selling product.
            Rising trade tariffs between countries could also raise the cost of the products we import."""),
        ("h2", "Weather and seasonality"),
        P("""A warm winter lowers demand for jackets, our most profitable products, and a wet summer lowers
            demand for camping equipment. Almost a third of annual revenue is earned in the fourth quarter, so a
            poor season can affect the whole year's results, as the warm November in Europe showed in 2026. To
            reduce this risk we are growing products sold all year round, such as base layers and everyday wear,
            and we order winter stock in two rounds, so we can cut the second order if demand is weak.
            We also track long-range weather forecasts when deciding how much winter stock to order.
            In a mild winter, discounts on jackets can take about one point off our gross margin."""),
        ("h2", "Currency"),
        P("""Most costs are in US dollars, while 38 percent of revenue is earned in euros and pounds. If the dollar
            strengthens, that revenue is worth fewer dollars, and our profit falls. We hedge about 70 percent of
            expected currency needs for the next twelve months using forward contracts, which fix the exchange
            rate in advance. In 2026, currency movements reduced reported revenue by about 3.1 million dollars
            and had almost no effect on operating income because of these hedges.
            We do not use currency contracts to speculate, only to protect expected cash flows.
            Our stores in Japan add a small exposure to the yen, which is not yet hedged."""),
        ("h2", "Cyber security and data"),
        P("""More than 40 percent of our revenue now comes through our website and app, which hold the personal
            details of about 4 million customers. An attack that took the website offline in a busy season or
            exposed customer data would cost us sales and trust. We do not store card numbers ourselves, we test
            our systems with outside security firms twice a year, and every employee takes security training. We
            had no serious security incident in 2026.
            The audit committee reviews our security plans twice a year, and we hold insurance against the cost of a cyber attack.
            Customer passwords are stored in encrypted form, and customers can turn on two-step sign-in in the app."""),
        ("h1", "Outlook for 2027"),
        P("""We expect revenue of 530 to 550 million dollars and an operating margin of about 12 percent. We plan
            to open six new stores, start building a second distribution centre in the Netherlands, and launch a
            footwear repair service. Capital spending is expected to be about 30 million dollars, higher than in
            2026 because of the distribution centre. We expect equipment to keep growing fastest, helped by a
            new range of ultralight sleeping bags, and the redesigned trail-running shoes to return that range
            to growth in the second half of the year.
            These figures assume normal weather and no major disruption to our suppliers, as described under Risks.
            We will report our results for the first half of 2027 at the end of July."""),
    ],
)

HANDBOOK = (
    "Fernhill Employee Handbook",
    [
        P("""This handbook explains how we work at Fernhill Outdoor Co., a fictional company, and what you can
            expect from us. It applies to all employees in offices, distribution centres and stores, unless a
            section says otherwise. Your contract and local law take priority if they differ. If something is
            unclear, ask your manager or the People team. Last updated January 2026."""),
        ("h1", "Joining Fernhill"),
        ("h2", "Your first week"),
        P("""Before your first day you will receive an email with your start time, where to go and who to ask
            for. On day one your manager will meet you, give you your laptop or store login, and introduce you
            to a buddy from your team who can answer everyday questions. During the first week you will
            complete online training on health and safety, data protection and our code of conduct, and you
            will have a welcome session with someone from the People team, where you can ask anything about pay,
            benefits or this handbook.
            Your manager will also set up a 30-minute meeting at the end of your first week to see how things are going.
            If you need any adjustments to start work, such as a particular desk or screen reader, tell the People team before you start."""),
        ("h2", "Probation period"),
        P("""The first six months are a probation period, or three months for store and distribution centre roles.
            Your manager will meet you at least once a month to talk about how things are going and agree what
            you should focus on. At the end, they will confirm your job in writing, or, if more time is needed,
            extend the probation once by up to three months and explain why. During probation either side can
            end the employment with one week's notice; after it, the notice periods in Leaving Fernhill apply.
            You can raise concerns of your own at these meetings too: probation is a chance for both sides to check the job is right.
            Your annual leave and benefits apply in full from your first day, including during probation."""),
        ("h2", "Learning and development"),
        P("""Every employee has a learning budget of 1,000 dollars a year for courses, books, conferences or
            certifications related to their work, and up to five working days a year to use it. Agree how you
            will use it with your manager. We also run an internal programme where store employees can train as
            product specialists or assistant managers, and we advertise every open job internally for a week
            before it goes outside the company. Each spring you and your manager agree development goals for the
            year ahead.
            Unused budget does not carry over to the next year.
            Popular choices include first aid and mountain leader courses, language classes and professional qualifications in finance and design."""),
        ("h1", "Working Hours and Location"),
        ("h2", "Working hours"),
        ("h3", "Core hours"),
        P("""Office teams work flexible hours, but everyone is available for meetings between 10:00 and 15:00
            local time. A full-time week is 37.5 hours, usually Monday to Friday. You can start and finish when
            it suits you outside the core hours, as long as your team knows when you are working and you take a
            break of at least 30 minutes if you work more than six hours. Part-time and compressed weeks, such as
            four longer days, can be agreed with your manager, and we try to say yes.
            Please keep your calendar up to date so colleagues can see when you are available.
            Meetings outside core hours should be the exception, especially for colleagues in other time zones."""),
        ("h3", "Rotas and overtime"),
        P("""Store and distribution centre teams work to a rota published at least two weeks in advance, so you
            can plan your life around it. If we change your shifts with less than 48 hours' notice, you are paid
            for the original shift as well as the new one. Overtime must be agreed with your manager in advance
            and is paid at one and a half times your hourly rate, or twice your rate on public holidays.
            Salaried office employees do not receive overtime pay but can take the time back within a month.
            You can swap shifts with a colleague in the rota app, as long as your manager approves the swap.
            You should have at least 11 hours off between shifts and two days off in every seven."""),
        ("h2", "Where you work"),
        ("h3", "Hybrid work"),
        P("""Office roles are hybrid: you work from the office at least three days a week, including your team's
            anchor day, and from home on the other days. Your manager can agree a different pattern for a fixed
            period, for example after parental leave or while you care for someone. When you work from home you
            need a quiet place and a reliable internet connection. We give every hybrid employee a one-off 300
            dollar allowance to buy a desk, chair or screen for their home office.
            If you need special equipment at home for health reasons, such as an ergonomic chair, ask the People team; we pay for it in full.
            Office days are for working together, so teams plan meetings and workshops for the days when most people are in."""),
        ("h3", "Working from abroad"),
        P("""You can work from another country for up to 20 working days a year, for example to extend a visit to
            family. Ask your manager and the People team at least four weeks before you go, so we can check tax
            and visa rules. Some countries are not allowed for security reasons, and the People team keeps the
            current list. You must still be available during your team's core hours, adjusted for the time
            difference, and use the company VPN for all work. Moving abroad permanently is a different process.
            The 20 days do not need to be taken at once.
            Your laptop must stay with you, and you should not work from public places where others can see your screen."""),
        ("h1", "Time Off"),
        ("h2", "Holidays"),
        ("h3", "Annual leave"),
        P("""Full-time employees get 25 days of paid annual leave a year plus public holidays, rising to 28 days
            after five years. Part-time employees get the same in proportion to their hours. Leave runs from
            January to December. You can carry up to 5 unused days into the next year; they must be used by the
            end of March. Book leave in the HR portal at least two weeks ahead for anything longer than three
            days. In stores, leave in December needs approval by the end of September.
            If you are ill during your annual leave and have a doctor's note, those days count as sick leave instead, and you can take the leave later.
            You can also buy up to 5 extra days of leave a year through the HR portal, paid for from your salary over the year."""),
        ("h3", "Public holidays"),
        P("""You get the public holidays of the country you work in, on top of your annual leave. Offices close on
            public holidays. Stores often open on public holidays, so store employees may be rostered to work
            them; if you are, you are paid twice your hourly rate and get a day off in lieu within the next two
            months. If you work part-time and a public holiday falls on a day you would not work, you get a
            proportional amount of time off instead.
            Religious or cultural holidays that are not public holidays can be taken as annual leave, and managers will do their best to approve them.
            The People team publishes the list of public holidays for each country every December."""),
        ("h2", "Sick leave"),
        P("""Tell your manager before your shift or start time if you are ill, by phone or message, and say when
            you expect to return. You can self-certify for up to 3 days; after that we need a note from a doctor.
            You get full pay for up to 10 sick days a year, and half pay for a further 20 days. If you are off
            for more than two weeks, your manager and the People team will keep in touch and agree a plan for
            your return, which can include shorter hours for a while. Medical appointments do not count as sick
            leave if you make up the time.
            Sick leave is recorded in the HR portal, either by you or by your manager."""),
        ("h2", "Family leave"),
        ("h3", "Parental leave"),
        P("""Every parent, whatever their gender and however they became a parent, gets 16 weeks of parental
            leave at full pay, to be taken within the first year after the birth or adoption. Birth parents can
            take a further 10 weeks at statutory pay. Tell the People team at least 15 weeks before the due date
            or placement. You can take the leave in up to three blocks. When you return, you can work 80 percent
            of your hours for full pay for the first 4 weeks.
            Parental leave does not reduce your annual leave: you keep earning annual leave while you are away, and your pension contributions continue.
            Before and after your leave, you can work from home more often, if your role allows it, to help you adjust."""),
        ("h3", "Caring for a dependant"),
        P("""If a child, partner, parent or someone else who depends on you is ill or has an emergency, you can
            take up to 5 days of paid carer's leave a year to look after them or arrange care. Tell your manager
            as soon as you can; you do not need to give proof. For longer-term caring, such as a parent with a
            serious illness, you can ask for up to 12 weeks of unpaid leave or for a temporary change to your
            hours or working pattern. We keep your job open during unpaid carer's leave.
            The employee assistance line can also help you find care services and advice.
            Carer's leave can be taken in half days as well as whole days."""),
        ("h2", "Other leave"),
        P("""The table lists other paid leave. Bereavement and jury duty can be taken at short notice; for the
            others, ask your manager at least two weeks ahead and record the leave in the HR portal so it does not
            come out of your annual leave. If something important happens that does not fit any of these, talk
            to your manager: they can grant up to 3 extra days of paid leave a year.
            Unpaid leave of up to four weeks for other reasons, such as a long trip, can be agreed with your manager."""),
        ("table", ["Type", "Paid days", "Notes"], [
            ["Bereavement", "Up to 10", "For a partner, child, parent or sibling; 3 days for other relatives"],
            ["Volunteering", "2 per year", "For registered charities and community projects"],
            ["Moving home", "1 per year", ""],
            ["Jury duty", "As needed", "Full pay; tell your manager when you are summoned"],
        ]),
        ("h1", "Pay and Benefits"),
        ("h2", "Pay"),
        ("h3", "Pay day and payslips"),
        P("""You are paid monthly, on the last working day of the month, by bank transfer. Store and distribution
            centre employees paid by the hour are paid for the hours worked up to the 20th of the month, with
            any later hours paid the following month. Payslips are in the HR portal two days before pay day. If
            you think your pay is wrong, tell the payroll team through the portal; they will reply within two
            working days and correct any underpayment within a week.
            If the last working day falls on a public holiday, you are paid on the working day before.
            Your payslip shows your pay, tax, pension contributions and any expenses paid, and you can download past payslips for up to seven years."""),
        ("h3", "Pay reviews"),
        P("""Pay is reviewed every April based on your performance and market rates, and any rise applies from
            1 April. We compare our pay with other retailers and outdoor brands every year and publish the pay
            range for every job inside the company, so you can see where you stand. You can ask your manager
            about your pay at any time. Promotions outside the April review are possible and come with a rise of
            at least 8 percent.
            Your manager will explain the outcome of your review in a one-to-one meeting in March.
            Employees on parental or sick leave during the review are included in it."""),
        ("h2", "Pension"),
        P("""We match your pension contributions up to 6 percent of your salary: if you pay in 6 percent, we pay
            in 6 percent as well. You are enrolled automatically after your first month and can change your
            contribution, or choose different funds, at any time in the pension provider's app. If you leave,
            the pension stays yours. Twice a year a financial adviser runs free sessions on saving for
            retirement, open to every employee.
            If you do not want to be in the pension, you can opt out in the first month, but you will then not receive our contributions.
            Your contributions are taken before tax where local rules allow, which lowers the tax you pay."""),
        ("h2", "Health and wellbeing"),
        P("""Private health insurance covers you from your first day, and you can add your partner and children
            at a reduced rate. It includes dental and eye care. The employee assistance line offers free,
            confidential counselling 24 hours a day, for anything from stress to money worries, and up to eight
            sessions with a therapist a year. We also pay half the cost of a gym or climbing wall membership, up
            to 40 dollars a month.
            Store and distribution centre employees on part-time contracts of 20 hours a week or more get the same cover as everyone else.
            Claims are made directly with the insurer through its app, and the People team never sees your medical details."""),
        ("h2", "Gear allowance and discount"),
        P("""You get 40 percent off Fernhill products, for yourself and up to two friends or family members. Each
            year you also get a 500 dollar gear allowance to spend on Fernhill products, because we think people
            who make outdoor gear should use it. The allowance is added to your staff account every January;
            new joiners get a share in proportion to the months left in the year. Unused allowance does not carry
            over, and products bought with the discount may not be resold.
            The discount also applies in our outlet stores and on the Fernhill Second Life resale site.
            To use the discount online, sign in with your work email address."""),
        ("h1", "Expenses and Travel"),
        ("h2", "Before you spend"),
        P("""Get your manager's approval before you book travel or spend more than 250 dollars. Use the company
            card where you have one; otherwise pay yourself and claim the money back. Spend company money as if
            it were your own: choose the cheaper option when two are equally good. Some things are never paid
            for, such as fines, upgrades you choose for comfort, and personal shopping. If you are unsure whether
            something can be claimed, ask your manager before you spend, not afterwards.
            Directors approve any single purchase over 2,000 dollars.
            Software subscriptions are always bought by the IT team, never on a personal card."""),
        ("h2", "Travel"),
        ("h3", "Trains and flights"),
        P("""Book travel through the travel portal, which shows our negotiated prices and keeps a record of where
            you are in case of an emergency. Take the train for journeys under four hours. Flights are economy
            class, or premium economy for flights over eight hours. Book at least two weeks ahead where you can,
            as late bookings cost more. You may keep air miles, but they must not influence which airline you
            choose. Taxis are allowed late at night, with heavy luggage or where there is no public transport.
            If plans change, cancel through the portal as early as you can, so we can get money back.
            Car hire is allowed only when it is cheaper than the alternatives or there is no other way to reach the place."""),
        ("h3", "Hotels"),
        P("""Hotels should cost no more than the city limit shown in the portal, which is set for each city
            every year. If no suitable hotel is available within the limit, for example during a big trade fair,
            your manager can approve a higher price. Book through the portal so that the company pays directly
            where possible. Staying with friends instead of a hotel is welcome; you can then claim a 40 dollar
            thank-you gift for your host per trip.
            Hotel loyalty points are yours to keep.
            If you are travelling with colleagues, each person gets their own room. Extras such as minibar drinks, films and laundry for trips under five nights are not paid."""),
        ("h2", "Meals and daily allowance"),
        P("""When you travel for work you get a daily allowance for meals instead of claiming each one. You do not
            need receipts for the allowance itself, but you do need to record the dates and places of your trip
            in the expenses app. The amounts are in the table below. Client dinners are separate: they need your
            manager's approval in advance and are claimed with receipts.
            The allowance is paid with your expenses, so it reaches you with your next salary."""),
        ("table", ["Trip", "Daily meal allowance", "Notes"], [
            ["Same country, overnight", "60 dollars", "Breakfast included in the hotel is not claimed"],
            ["Abroad", "85 dollars", "Converted at the rate on the day of travel"],
            ["Day trip over 10 hours", "25 dollars", "No overnight stay"],
        ]),
        ("h2", "Claiming expenses"),
        P("""Submit claims in the expenses app within 30 days, with a photo of each receipt. Claims approved by
            the 20th of the month are paid with that month's salary. Alcohol is not reimbursed, except at events
            approved in advance by a director. Claims older than 90 days are not paid. Your manager approves
            your claims, and finance checks a sample of them every month; claiming something you did not spend
            is treated as gross misconduct.
            If you lose a receipt, write a short note explaining the cost instead; your manager decides whether it can be paid.
            Mileage for using your own car on company business is paid at the rate shown in the expenses app."""),
        ("h1", "Equipment and Security"),
        ("h2", "Laptops and phones"),
        P("""Office employees receive a laptop, and a phone if their role needs one. They stay company property:
            do not install software that is not in the company app store, and do not let anyone else use them.
            Lock your screen whenever you step away. Keep work files in the company's cloud storage, not on the
            laptop itself, so nothing is lost if it breaks. Return all equipment on your last day. If something
            breaks, the IT service desk will repair or replace it, usually within two working days.
            You may use your work phone for reasonable personal calls and messages.
            Laptops are replaced every four years, or sooner if they stop working well."""),
        ("h2", "Passwords and sign-in"),
        P("""Use the company password manager and turn on two-step sign-in for every work account. Use a
            different password for every account and never reuse your work password anywhere else. Never share
            your password, even with IT: the IT team will never ask for it. Be careful with emails asking you to
            sign in, pay an invoice or change bank details, even if they seem to come from a colleague; check by
            phone first.
            The IT team sends practice phishing emails a few times a year; if you click one, you will just be shown a short training video.
            Change a password straight away if you think someone else may know it."""),
        ("h2", "Reporting a security incident"),
        P("""If you lose a device, click a suspicious link or think customer data may have been exposed, report it
            to the IT service desk within one hour, at any time of day, by phone or through the portal. You will
            not be blamed for reporting a mistake quickly. The sooner we know, the sooner we can lock a lost
            laptop or reset an account, and in some countries we must tell the authorities within 72 hours if
            personal data was exposed.
            Do not try to investigate or fix the problem yourself, and do not delete suspicious emails until the IT team has seen them.
            The IT service desk number is printed on the back of your staff badge."""),
        ("h1", "Conduct"),
        ("h2", "Code of conduct"),
        P("""Treat colleagues, customers and suppliers with respect. Harassment, discrimination and bullying are
            not tolerated, whether in person, in messages or on social media, and at work events as much as at
            work. Do not speak for Fernhill in public or to journalists unless that is part of your job. Breaking
            the code can lead to disciplinary action, up to dismissal. The full code of conduct is in the HR
            portal, and everyone completes training on it every year.
            If you are unsure whether something is acceptable, ask your manager or the People team.
            The same standards apply to contractors and temporary staff who work with us, and we expect our suppliers to follow our supplier code."""),
        ("h2", "Gifts and conflicts of interest"),
        P("""Gifts from suppliers worth more than 50 dollars must be declared to your manager, and you may never
            accept cash or anything offered to win a decision. Tell your manager if you, a relative or a close
            friend has an interest in a supplier, competitor or customer of Fernhill, or if you want to take on a
            second job. Most of these are fine once declared; the problem is keeping them secret. Declarations
            are recorded in the HR portal.
            Invitations to events paid for by a supplier, such as a sports match, also need your manager's approval in advance.
            You must never use information you learn at work, such as unpublished results, to buy or sell shares."""),
        ("h2", "Raising a concern"),
        P("""If you see something wrong, talk to your manager or the People team. You can also use the
            confidential speak-up line, run by an independent company, anonymously if you prefer, by phone or
            online in 12 languages. Every report is looked into by someone not involved, and you will hear what
            happened next where we can share it. Nobody will be treated badly for raising a concern in good
            faith, even if it turns out to be unfounded.
            Retaliating against someone who has raised a concern is itself a serious breach of the code of conduct.
            The audit committee of the board receives a summary of all speak-up reports every quarter."""),
        ("h1", "Leaving Fernhill"),
        ("h2", "Notice periods"),
        P("""If you decide to leave, tell your manager and confirm it in writing in the HR portal. The notice you
            give, and the notice we give you, depends on your role and how long you have worked here, as in the
            table. Local law may require longer notice, in which case the longer period applies. Your manager may
            agree a shorter notice period if the handover allows it.
            If we end your employment, we will explain why in writing, except during probation.
            Notice must be given in writing; a conversation alone does not count."""),
        ("table", ["Role", "Less than 2 years", "2 years or more"], [
            ["Store and distribution centre", "2 weeks", "4 weeks"],
            ["Office", "1 month", "2 months"],
            ["Managers and directors", "3 months", "3 months"],
        ]),
        ("h2", "Your last day"),
        P("""Before your last day, agree a handover plan with your manager and take any annual leave you have
            left; leave you could not take is paid with your final salary. Return your laptop, phone, keys and
            badge on your last day. Your final pay, including any expenses still owed, is paid on the next usual
            pay day. We will ask you to complete a short leaving survey, and you can ask for an exit conversation
            with the People team. Your staff discount ends on your last day.
            You can keep your pension and transfer it to a new employer's scheme if you wish.
            We are happy to give a reference confirming your job title and dates of employment."""),
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
        if kind in ("h1", "h2", "h3"):
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
