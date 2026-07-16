from pathlib import Path
from math import sin, pi
from PIL import Image, ImageDraw, ImageFont, ImageFilter


PROJECT = Path(r"C:\Users\Anthony.DESKTOP-ES5HL78\Documents\Tshiamiso_Trust_Application")
ASSETS = PROJECT / "assets"
OUTPUTS = Path(r"C:\Users\Anthony.DESKTOP-ES5HL78\Documents\Codex\2026-07-15\files-mentioned-by-the-user-codex\outputs")

ASSETS.mkdir(parents=True, exist_ok=True)
OUTPUTS.mkdir(parents=True, exist_ok=True)

BG = (233, 231, 222)
SURFACE = (246, 244, 236)
INK = (32, 29, 24)
MUTED = (91, 86, 76)
GREEN = (47, 93, 87)
GOLD = (168, 116, 34)
RUST = (138, 63, 43)
DARK = (24, 48, 45)
GREY = (107, 114, 128)
WHITE = (255, 255, 255)


def font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def text_wrap(draw, text, fnt, max_width):
    words = text.split()
    lines = []
    line = ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textbbox((0, 0), test, font=fnt)[2] <= max_width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def draw_wrapped(draw, xy, text, fnt, fill, max_width, line_gap=8):
    x, y = xy
    for line in text_wrap(draw, text, fnt, max_width):
        draw.text((x, y), line, font=fnt, fill=fill)
        y += fnt.size + line_gap
    return y


def rounded(draw, box, fill, outline=None, width=1, radius=10):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def curved_route(draw, a, b, color, width=5, bend=70):
    pts = []
    ax, ay = a
    bx, by = b
    for i in range(34):
        t = i / 33
        x = ax + (bx - ax) * t
        y = ay + (by - ay) * t - sin(pi * t) * bend
        pts.append((x, y))
    draw.line(pts, fill=color, width=width, joint="curve")
    # arrow head
    hx, hy = pts[-1]
    px, py = pts[-4]
    dx, dy = hx - px, hy - py
    mag = max((dx * dx + dy * dy) ** 0.5, 1)
    ux, uy = dx / mag, dy / mag
    left = (hx - ux * 18 - uy * 8, hy - uy * 18 + ux * 8)
    right = (hx - ux * 18 + uy * 8, hy - uy * 18 - ux * 8)
    draw.polygon([left, (hx, hy), right], fill=color)


def node(draw, xy, label, color, r=11, label_side="right"):
    x, y = xy
    draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=WHITE, width=2)
    f = font(18, True)
    tx = x + r + 8 if label_side == "right" else x - r - 8 - draw.textbbox((0, 0), label, font=f)[2]
    draw.text((tx, y - 11), label, font=f, fill=INK)


def cover_image():
    w, h = 2400, 1350
    img = Image.new("RGB", (w, h), (229, 227, 217))
    d = ImageDraw.Draw(img)

    # Executive cover frame.
    rounded(d, (78, 70, 2322, 1280), fill=(20, 47, 43), radius=34)
    rounded(d, (116, 110, 2284, 1242), fill=(245, 242, 231), radius=24)
    rounded(d, (144, 138, 2256, 1214), fill=(17, 42, 39), radius=22)

    # Map grid inside the intelligence panel.
    map_box = (1010, 220, 2176, 1008)
    rounded(d, map_box, fill=(14, 37, 34), outline=(58, 91, 84), width=2, radius=18)
    for x in range(map_box[0] + 58, map_box[2], 112):
        d.line((x, map_box[1] + 26, x, map_box[3] - 26), fill=(36, 69, 63), width=1)
    for y in range(map_box[1] + 58, map_box[3], 98):
        d.line((map_box[0] + 26, y, map_box[2] - 26, y), fill=(36, 69, 63), width=1)

    # Stylised operating footprint with stronger geometry and less screenshot noise.
    land = [
        (1105, 448), (1224, 372), (1410, 392), (1548, 334), (1712, 385),
        (1856, 372), (2025, 444), (2115, 552), (2026, 716), (1836, 748),
        (1682, 712), (1542, 790), (1396, 728), (1268, 742), (1148, 650)
    ]
    d.polygon(land, fill=(222, 216, 194))
    d.line(land + [land[0]], fill=(166, 155, 126), width=4)
    d.line((1505, 350, 1572, 788), fill=(190, 181, 153), width=2)
    d.line((1840, 378, 1772, 744), fill=(190, 181, 153), width=2)

    def map_node(x, y, label, color, kind="circle", side="right"):
        if kind == "diamond":
            d.regular_polygon((x, y, 18), 4, rotation=45, fill=color, outline=WHITE)
        else:
            d.ellipse((x - 14, y - 14, x + 14, y + 14), fill=color, outline=WHITE, width=3)
        label_font = font(25, True)
        pad_x, pad_y = 12, 7
        tw = d.textbbox((0, 0), label, font=label_font)[2]
        lx = x + 23 if side == "right" else x - tw - 23
        ly = y - 22
        rounded(d, (lx - pad_x, ly - pad_y, lx + tw + pad_x, ly + 31), fill=(245, 242, 231), radius=8)
        d.text((lx, ly), label, font=label_font, fill=INK)

    def arc(a, b, color, width, bend, arrows=True):
        curved_route(d, a, b, color, width=width, bend=bend)

    centres = {
        "Maseru": (1390, 673),
        "Mthatha": (1580, 855),
        "Maputo": (1990, 660),
        "Mbabane": (1882, 646),
        "Polokwane": (1704, 420),
    }
    hubs = {
        "Welkom": (1495, 558),
        "Johannesburg": (1618, 520),
        "Barberton": (1830, 548),
    }
    for label, start in centres.items():
        target = hubs["Welkom"] if label in {"Maseru", "Mthatha"} else hubs["Barberton"]
        arc(start, target, RUST, 7, 78)
        arc(target, start, GREEN, 4, -54, arrows=False)
    for label, pt in hubs.items():
        map_node(*pt, label, GOLD, kind="diamond", side="right")
    for label, pt in centres.items():
        side = "left" if label in {"Maseru", "Mthatha", "Polokwane", "Mbabane"} else "right"
        map_node(*pt, label, GREEN, side=side)

    # Left-side narrative and KPI stack.
    d.text((218, 210), "Claimant-Intelligence", font=font(82, True), fill=WHITE)
    d.text((218, 300), "Platform", font=font(82, True), fill=GOLD)
    draw_wrapped(
        d,
        (224, 414),
        "Turning fragmented mining, TEBA, medical and regional records into located claimants, defensible payments and targeted outreach.",
        font(36),
        (217, 228, 218),
        670,
        13,
    )
    draw_wrapped(
        d,
        (224, 586),
        "Geo intelligence | Identity matching | Outreach | Executive dashboards",
        font(27, True),
        (179, 202, 193),
        640,
        6,
    )

    cards = [
        ("414,885", "registrations monitored"),
        ("53,945", "claimants contacted"),
        ("26%", "medical-yield signal"),
        ("+24/day", "backlog movement"),
    ]
    for i, (v, lab) in enumerate(cards):
        x = 224 + (i % 2) * 350
        y = 702 + (i // 2) * 146
        rounded(d, (x, y, x + 302, y + 106), fill=(245, 242, 231), radius=15)
        d.text((x + 24, y + 18), v, font=font(45, True), fill=GOLD)
        d.text((x + 25, y + 72), lab.upper(), font=font(17, True), fill=MUTED)

    # Insight strip and legend.
    rounded(d, (224, 1032, 2168, 1148), fill=(245, 242, 231), radius=18)
    d.text((260, 1062), "Executive question:", font=font(28, True), fill=RUST)
    d.text((530, 1062), "Where are eligible ex-mineworkers likely to be, what evidence confirms them, and what action happens next?", font=font(26), fill=INK)
    legend_x = 1552
    d.text((legend_x, 804), "Operational layers", font=font(26, True), fill=WHITE)
    legend = [("Migration to gold mines", RUST), ("Return / family tracing", GREEN), ("Gold-mining hub", GOLD), ("Labour-sending centre", GREEN)]
    for i, (lab, col) in enumerate(legend):
        y = 846 + i * 38
        d.rounded_rectangle((legend_x, y + 8, legend_x + 28, y + 28), radius=4, fill=col)
        d.text((legend_x + 45, y), lab, font=font(23), fill=(229, 236, 229))

    d.text((222, 1166), "Anthony Apollis | IT & Data Manager proposal", font=font(28, True), fill=(233, 196, 137))
    d.text((1650, 1168), "Tshiamiso Trust compensation intelligence", font=font(24, True), fill=(211, 222, 211))
    return img


def social_base(title, subtitle):
    w, h = 1200, 627
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    rounded(d, (28, 26, 1172, 601), fill=SURFACE, outline=(194, 188, 174), width=2, radius=18)
    d.text((64, 54), "Tshiamiso Trust | Claimant Intelligence", font=font(22, True), fill=GREEN)
    d.text((64, 92), title, font=font(48, True), fill=INK)
    draw_wrapped(d, (66, 154), subtitle, font(24), MUTED, 520, 8)
    d.text((64, 562), "Anthony Apollis | Data Engineer & Analyst", font=font(22, True), fill=RUST)
    return img, d


def linkedin_overview():
    img, d = social_base(
        "From fragmented records to found claimants",
        "A governed data layer that joins mine, TEBA, medical, call-centre and GIS records into action."
    )
    x0, y0 = 690, 150
    steps = [("Ingest", GREEN), ("Match", GOLD), ("Locate", RUST), ("Engage", GREEN), ("Report", GOLD)]
    for i, (lab, col) in enumerate(steps):
        x = x0 + (i % 2) * 205
        y = y0 + (i // 2) * 112
        rounded(d, (x, y, x + 170, y + 70), fill=col, radius=10)
        d.text((x + 24, y + 20), lab, font=font(28, True), fill=WHITE if col != GOLD else INK)
        if i < len(steps) - 1:
            d.line((x + 172, y + 35, x + 198, y + 35), fill=INK, width=3)
    return img


def linkedin_map():
    img, d = social_base(
        "Geo intelligence for outreach",
        "Migration routes, return tracing and distance-ranked field trips in one operational map."
    )
    panel = (650, 135, 1125, 510)
    rounded(d, panel, fill=(24, 48, 45), radius=14)
    # mini map
    places = {
        "Maseru": (760, 420), "Mthatha": (870, 485), "Maputo": (1060, 400),
        "Mbabane": (995, 380), "Welkom": (800, 310), "Barberton": (955, 315), "JHB": (870, 275)
    }
    for src, dst in [("Maseru", "Welkom"), ("Mthatha", "Welkom"), ("Maputo", "Barberton"), ("Mbabane", "Barberton")]:
        curved_route(d, places[src], places[dst], RUST, width=4, bend=35)
        curved_route(d, places[dst], places[src], GREEN, width=3, bend=-26)
    for name in ["Welkom", "Barberton", "JHB"]:
        x, y = places[name]
        d.regular_polygon((x, y, 13), 4, rotation=45, fill=GOLD, outline=WHITE)
        d.text((x + 17, y - 10), name, font=font(16, True), fill=WHITE)
    for name in ["Maseru", "Mthatha", "Maputo", "Mbabane"]:
        x, y = places[name]
        d.ellipse((x - 10, y - 10, x + 10, y + 10), fill=GREEN, outline=WHITE, width=2)
        d.text((x + 15, y - 10), name, font=font(16, True), fill=WHITE)
    return img


def linkedin_dashboard():
    img, d = social_base(
        "Executive dashboard, not static reporting",
        "Every tile answers: what changed, why it matters, and what management should do next."
    )
    cards = [
        ("414,885", "registrations"),
        ("53,945", "contact made"),
        ("26%", "medical yield"),
        ("595", "certified unpaid"),
        ("+24/day", "backlog signal"),
        ("8.9%", "KZN conversion"),
    ]
    for i, (v, lab) in enumerate(cards):
        x = 650 + (i % 2) * 235
        y = 145 + (i // 2) * 120
        rounded(d, (x, y, x + 205, y + 88), fill=BG, outline=(194, 188, 174), width=2, radius=10)
        d.text((x + 18, y + 15), v, font=font(32, True), fill=GOLD if i != 4 else RUST)
        d.text((x + 18, y + 55), lab.upper(), font=font(13, True), fill=MUTED)
    return img


def linkedin_skills():
    img, d = social_base(
        "Skills behind the build",
        "Turning a hard social problem into governed data, maps, automation and decisions."
    )
    skills = [
        "Data engineering", "Cloud warehousing", "Python", "Power BI / Tableau",
        "GIS mapping", "Identity matching", "Snowflake / Azure", "Data governance",
        "Zero trust security", "Executive reporting", "Stakeholder management", "Automation"
    ]
    for i, skill in enumerate(skills):
        x = 610 + (i % 2) * 275
        y = 145 + (i // 2) * 58
        rounded(d, (x, y, x + 255, y + 38), fill=GREEN if i % 3 == 0 else GOLD if i % 3 == 1 else RUST, radius=18)
        d.text((x + 18, y + 9), skill, font=font(17, True), fill=WHITE if i % 3 != 1 else INK)
    return img


def save_all():
    images = {
        "tshiamiso_geo_intelligence_cover.png": cover_image(),
        "linkedin_claimant_intelligence_overview.png": linkedin_overview(),
        "linkedin_geo_intelligence_map.png": linkedin_map(),
        "linkedin_executive_dashboard.png": linkedin_dashboard(),
        "linkedin_skills_profile.png": linkedin_skills(),
    }
    saved = []
    for name, img in images.items():
        project_path = ASSETS / name
        output_path = OUTPUTS / name
        img.save(project_path, "PNG", optimize=True)
        img.save(output_path, "PNG", optimize=True)
        saved.append((project_path, output_path))
    return saved


if __name__ == "__main__":
    for project_path, output_path in save_all():
        print(project_path)
        print(output_path)
