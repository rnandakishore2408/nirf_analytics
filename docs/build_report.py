"""Build the staff-facing PDF report: docs/NIRF_Analytics_Report.pdf
All numbers are read from db/nirf.db and data/processed/*.json so the report always matches the pipeline."""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "NIRF_Analytics_Report.pdf"
IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)
P = json.loads((ROOT / "data/processed/prediction_2026.json").read_text())
A = json.loads((ROOT / "data/processed/analysis.json").read_text())
M = json.loads((ROOT / "data/processed/model_report.json").read_text())
con = sqlite3.connect(ROOT / "db/nirf.db")
W, H = A4

# ---------------- palette ----------------
NAVY, CORAL, GOLD, TEAL, SKY, PLUM = "#1B2A4A", "#E4572E", "#F3A712", "#17A398", "#3E92CC", "#7B4B94"
INK, MUTED, LINE = "#1F2937", "#5B6B7F", "#D9DEE7"
TINT = {SKY: "#E8F1FA", CORAL: "#FCEAE4", GOLD: "#FEF3DC", TEAL: "#E3F5F2", PLUM: "#EFE7F3", NAVY: "#E6E9F0", MUTED: "#F3F5F8"}
PCOL = {"tlr": SKY, "rpc": CORAL, "go": TEAL, "oi": GOLD, "pr": PLUM}
C = colors.HexColor

# ---------------- styles ----------------
ss = getSampleStyleSheet()
BODY = ParagraphStyle("B", parent=ss["Normal"], fontSize=10, leading=14.5, spaceAfter=7, textColor=C(INK))
LEAD = ParagraphStyle("Lead", parent=BODY, fontSize=11.5, leading=16.5, textColor=C(NAVY))
SMALL = ParagraphStyle("S", parent=BODY, fontSize=8.5, leading=11.5, textColor=C(MUTED))
H2 = ParagraphStyle("H2", parent=BODY, fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=C(NAVY), spaceBefore=10, spaceAfter=4)
BUL = ParagraphStyle("Bul", parent=BODY, leftIndent=14, bulletIndent=3, spaceAfter=4)
CODE = ParagraphStyle("Code", parent=BODY, fontName="Courier", fontSize=8, leading=10.5, textColor=C(INK))
HEADCELL = ParagraphStyle("Head", parent=SMALL, textColor=colors.white, fontName="Helvetica-Bold", fontSize=8.2, leading=10)
CELL = ParagraphStyle("Cell", parent=SMALL, textColor=C(INK), fontSize=8.3, leading=10.5)


def p(t, st=BODY):
    return Paragraph(t, st)


def section(num, title, col=NAVY):
    numcell = Paragraph(f"<font color='white'><b>{num}</b></font>", ParagraphStyle("n", parent=BODY, fontSize=14, leading=16, alignment=TA_CENTER))
    tcell = Paragraph(f"<b>{title}</b>", ParagraphStyle("t", parent=BODY, fontSize=17, leading=20, textColor=C(NAVY)))
    t = Table([[numcell, tcell]], colWidths=[0.95 * cm, 16.4 * cm], rowHeights=[0.95 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), C(col)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (1, 0), (1, 0), 8),
                           ("LINEBELOW", (0, 0), (-1, 0), 1.2, C(col)), ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 2)]))
    return KeepTogether([Spacer(1, 6), t, Spacer(1, 8)])


def callout(text, col=SKY, label=None):
    body = [Paragraph(text, ParagraphStyle("co", parent=BODY, spaceAfter=0))]
    if label:
        body.insert(0, Paragraph(f"<font color='{col}'><b>{label.upper()}</b></font>", ParagraphStyle("cl", parent=SMALL, fontSize=7.5, spaceAfter=3)))
    t = Table([["", body]], colWidths=[0.18 * cm, 17.1 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), C(col)), ("BACKGROUND", (1, 0), (1, 0), C(TINT[col])), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LEFTPADDING", (1, 0), (1, 0), 10), ("RIGHTPADDING", (1, 0), (1, 0), 10), ("TOPPADDING", (1, 0), (1, 0), 8), ("BOTTOMPADDING", (1, 0), (1, 0), 8)]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 8)])


def tech(text):
    return callout(text, col=MUTED, label="Technical note — skip if you like")


def tiles(items):
    cells = [[Paragraph(f"<font color='{col}'><b>{num}</b></font>", ParagraphStyle("tn", parent=BODY, fontSize=18, leading=21, spaceAfter=2)),
              Paragraph(lab, ParagraphStyle("tl", parent=SMALL, fontSize=8.3, leading=10.5))] for num, lab, col in items]
    w = 17.3 * cm / len(items)
    t = Table([cells], colWidths=[w] * len(items))
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
    for i, (_, _, col) in enumerate(items):
        st += [("BACKGROUND", (i, 0), (i, 0), C(TINT[col])), ("LINEABOVE", (i, 0), (i, 0), 3, C(col))]
    t.setStyle(TableStyle(st))
    return KeepTogether([t, Spacer(1, 10)])


def table(data, widths=None, head=True, zebra=True, align="LEFT", headcol=NAVY):
    data = [[c if not isinstance(c, str) else Paragraph(c, HEADCELL if (head and i == 0) else CELL) for c in row] for i, row in enumerate(data)]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, C(LINE)), ("ALIGN", (1, 1), (-1, -1), align),
          ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), C(headcol))]
    if zebra:
        st += [("BACKGROUND", (0, i), (-1, i), C("#F6F8FB")) for i in range(1 if head else 0, len(data)) if i % 2 == 0]
    t.setStyle(TableStyle(st))
    return t


def fig(name, w=16.5 * cm):
    im = Image(str(IMG / f"{name}.png"))
    im.drawWidth, im.drawHeight = w, w * im.imageHeight / im.imageWidth
    return im


def inr(x):
    return f"Rs {x / 1e7:.2f} Cr" if x >= 1e7 else f"Rs {x / 1e5:.2f} L" if x >= 1e5 else f"Rs {x:,.0f}"


# ---------------- data ----------------
r = pd.read_sql('SELECT year, rank, name, score, tlr, rpc, "go" AS go, oi, pr, institute_id FROM rankings WHERE category="Engineering"', con)
hist = pd.read_sql("SELECT * FROM v_saveetha_history", con)
sec_est = M["saveetha_estimates"]
s = P["saveetha"]; thr = P["thresholds"]["forecast_2026"]; val = P["top100_model_validation"]; mp = M["params"]
bp = s["band_probabilities"]; tier = pd.DataFrame(A["tier_profile_2025"])
gap = A["saveetha_gap_vs_rank90_100_avg"]; wgap = A["saveetha_weighted_gap_by_param"]
e25, e26 = sec_est[-2], sec_est[-1]
top200 = bp["top 100"] + bp["101-150"] + bp["151-200"]

# ---------------- charts ----------------
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": LINE, "axes.grid": True, "grid.color": "#EDF0F5",
                     "grid.linewidth": 0.7, "axes.titleweight": "bold", "axes.titlesize": 10, "axes.titlecolor": NAVY, "axes.titlelocation": "left"})

cut = r[r["rank"] <= 100].groupby("year").score.min()
f, ax = plt.subplots(figsize=(7.2, 3.3))
ax.fill_between(list(cut.index) + [2026], list(cut.values) + [thr["100"]], 30, color=SKY, alpha=0.08)
ax.plot(cut.index, cut.values, "-o", color=SKY, lw=2.4, label="Score needed for rank 100", zorder=3)
ax.plot([2025, 2026], [cut.values[-1], thr["100"]], "--D", color=SKY, lw=2.2, label="Our 2026 forecast", zorder=3)
hr = hist[hist.status == "ranked"]
ax.scatter(hr.year, hr.score, s=85, color=CORAL, zorder=5, label="Saveetha, published score")
for _, row in hr.iterrows():
    ax.annotate(f"rank {int(row.rank_or_band_low)}", (row.year, row.score), textcoords="offset points", xytext=(0, -15), ha="center", fontsize=8, color=CORAL)
ax.scatter([e["year"] for e in sec_est], [e["total_est"] for e in sec_est], s=95, facecolors="white", edgecolors=CORAL, linewidths=2.2, zorder=5, label="Saveetha, our estimate")
for e in sec_est:
    ax.annotate(f"≈{e['total_est']:.0f}", (e["year"], e["total_est"]), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=8.5, color=CORAL, fontweight="bold")
ax.annotate(f"{thr['100']:.0f} needed\nin 2026", (2026, thr["100"]), textcoords="offset points", xytext=(-4, 8), ha="right", fontsize=8.5, color=SKY, fontweight="bold")
ax.set_xticks(range(2017, 2027)); ax.set_ylabel("Total score (out of 100)"); ax.set_ylim(30, 51); ax.legend(loc="upper left", fontsize=8, frameon=False)
ax.set_title("The bar keeps rising")
f.tight_layout(); f.savefig(IMG / "cutoff.png", dpi=200); plt.close(f)

f, ax = plt.subplots(figsize=(7.2, 3.0))
x = range(len(tier)); w = 0.16
for i, pkey in enumerate(["tlr", "rpc", "go", "oi", "pr"]):
    ax.bar([xx + (i - 2) * w for xx in x], tier[pkey], w, color=PCOL[pkey], label=pkey.upper(), edgecolor="white", linewidth=0.6)
ax.set_xticks(list(x)); ax.set_xticklabels([f"Rank {t}" for t in tier.tier]); ax.set_ylabel("Average parameter score"); ax.set_ylim(0, 100)
ax.legend(ncol=5, fontsize=8, frameon=False, loc="upper right"); ax.set_title("What each rank tier looks like (2025)")
f.tight_layout(); f.savefig(IMG / "tiers.png", dpi=200); plt.close(f)

t76 = tier[tier.tier == "76-100"].iloc[0]; t10 = tier[tier.tier == "1-10"].iloc[0]
f, ax = plt.subplots(figsize=(7.2, 3.0))
labels = ["TLR", "RPC", "GO", "OI", "PR"]; keys = ["tlr", "rpc", "go", "oi", "pr"]
ax.bar([i - 0.27 for i in range(5)], [t10[k] for k in keys], 0.27, color="#C9D2E0", label="Top 10 average")
ax.bar([i for i in range(5)], [t76[k] for k in keys], 0.27, color="#8A98AD", label="Rank 76-100 average")
sv = [e26["tlr"], e26["rpc"], e26["go"], e26["oi"], e26["pr_assumed"]]
ax.bar([i + 0.27 for i in range(5)], sv, 0.27, color=[PCOL[k] for k in keys], label="Saveetha, 2026 filing (estimated)")
for i, v in enumerate(sv):
    ax.text(i + 0.27, v + 1.5, f"{v:.0f}", ha="center", fontsize=8.5, color=PCOL[keys[i]], fontweight="bold")
ax.set_xticks(range(5)); ax.set_xticklabels(labels); ax.set_ylim(0, 100); ax.set_ylabel("Parameter score"); ax.legend(fontsize=8, frameon=False)
ax.set_title("Where Saveetha stands on each parameter")
f.tight_layout(); f.savefig(IMG / "compare.png", dpi=200); plt.close(f)

order = ["top 100", "101-150", "151-200", "201-250", "251-300", "below 300"]
f, ax = plt.subplots(figsize=(7.2, 2.7))
bars = ax.bar(order, [100 * bp[k] for k in order], color=[CORAL if k == s["most_likely_band"] else "#C9D2E0" for k in order])
for b, k in zip(bars, order):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1, f"{100 * bp[k]:.0f}%", ha="center", fontsize=9, fontweight="bold" if k == s["most_likely_band"] else None)
ax.set_ylabel("Probability (%)"); ax.set_ylim(0, 45); ax.set_title("Where Saveetha is likely to land in 2026")
f.tight_layout(); f.savefig(IMG / "bands.png", dpi=200); plt.close(f)

lev = pd.DataFrame(P["what_if_levers"]).head(10)[::-1]
f, ax = plt.subplots(figsize=(7.2, 3.4))
cols_ = [CORAL if "PhD" in l else TEAL if ("salary" in l or "Graduation" in l) else GOLD if "states" in l else SKY for l in lev.lever]
ax.barh(lev.lever, lev.delta_total, color=cols_)
for i, v in enumerate(lev.delta_total):
    ax.text(v + 0.05, i, f"+{v:.2f}", va="center", fontsize=8.5)
ax.set_xlabel("Estimated gain in total score (points)"); ax.set_xlim(0, lev.delta_total.max() + 0.8); ax.grid(axis="y", visible=False)
ax.set_title("What one change is worth")
f.tight_layout(); f.savefig(IMG / "levers.png", dpi=200); plt.close(f)

f, ax = plt.subplots(figsize=(7.4, 3.9)); ax.axis("off"); ax.set_xlim(0, 100); ax.set_ylim(0, 100)
def box(x, y, w_, h_, title, sub, col):
    ax.add_patch(plt.Rectangle((x, y), w_, h_, facecolor=col, edgecolor="none", alpha=0.12))
    ax.add_patch(plt.Rectangle((x, y), w_, 5, facecolor=col, edgecolor="none"))
    ax.add_patch(plt.Rectangle((x, y), w_, h_, facecolor="none", edgecolor=col, lw=1.2))
    ax.text(x + w_ / 2, y + h_ - 5, title, ha="center", va="top", fontsize=8.5, fontweight="bold", color=NAVY)
    ax.text(x + w_ / 2, y + h_ / 2 - 2, sub, ha="center", va="center", fontsize=6.8, color="#334155", linespacing=1.3)
def arrow(x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color=NAVY, lw=1.3))
box(2, 62, 22, 34, "1  SOURCES", "nirfindia.org rankings\n2017-2025 + band pages\n704 institute data PDFs\nmethodology PDFs\nsaveetha.ac.in filings", SKY)
box(30, 62, 22, 34, "2  SCRAPE & PARSE", "Python: requests,\nBeautifulSoup, pdftotext\n+ regex → clean tables", TEAL)
box(58, 62, 22, 34, "3  DATABASE", "SQLite db/nirf.db\n10 tables, 2 views\nrankings · submissions\nmethodology · documents\nlive data · predictions", GOLD)
box(58, 14, 22, 36, "4  MODELS", "Score model (XGBoost,\nmonotone) learns NIRF's\nhidden f() curves\n2026 forecast (ridge +\nMonte Carlo)", CORAL)
box(30, 14, 22, 36, "5  ANALYSIS", "Cut-offs, tier profiles,\nmovers, Tamil Nadu peers,\nSaveetha gap & levers\n→ analysis.json", PLUM)
box(2, 14, 22, 36, "6  APP", "Streamlit dashboard\n6 pages · what-if sliders\nlive data entry\nAI assistant (Groq/Gemini)\nwith SQL + doc search", SKY)
arrow(24, 79, 30, 79); arrow(52, 79, 58, 79); arrow(69, 62, 69, 50); arrow(58, 32, 52, 32); arrow(30, 32, 24, 32)
ax.annotate("", xy=(13, 62), xytext=(13, 50), arrowprops=dict(arrowstyle="<-", color=NAVY, lw=1.2, linestyle="--"))
ax.text(14.5, 56, "staff live data\nwritten back", fontsize=6.5, color="#475569", va="center")
ax.text(50, 4, "One command (./pipeline.sh) re-runs every step when NIRF 2026 is published", ha="center", fontsize=7.5, color="#475569", style="italic")
f.tight_layout(); f.savefig(IMG / "architecture.png", dpi=220); plt.close(f)


# ---------------- page furniture ----------------
def cover(canvas, d):
    canvas.saveState()
    canvas.setFillColor(C(NAVY)); canvas.rect(0, H - 12.2 * cm, W, 12.2 * cm, stroke=0, fill=1)
    canvas.setFillColor(C(CORAL)); canvas.rect(0, H - 12.2 * cm, W, 0.35 * cm, stroke=0, fill=1)
    canvas.setFillColor(C(GOLD)); canvas.rect(0, H - 12.55 * cm, 6 * cm, 0.35 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 11); canvas.drawString(1.8 * cm, H - 2.3 * cm, "SAVEETHA ENGINEERING COLLEGE  ·  INTERNAL REPORT")
    canvas.setFont("Helvetica-Bold", 34); canvas.drawString(1.8 * cm, H - 4.6 * cm, "Getting back into")
    canvas.drawString(1.8 * cm, H - 6.0 * cm, "the NIRF top 100")
    canvas.setFont("Helvetica", 12.5); canvas.setFillColor(C("#C9D2E0"))
    for i, line in enumerate(["Where we stand in India's engineering rankings, why we slipped,", "what the numbers say about 2026, and the levers that matter most."]):
        canvas.drawString(1.8 * cm, H - 7.4 * cm - i * 0.6 * cm, line)
    canvas.setFont("Helvetica", 9.5)
    canvas.drawString(1.8 * cm, H - 10.3 * cm, f"Prepared {date.today().strftime('%d %B %Y')}  ·  Data: official NIRF results 2017-2025, the college's NIRF 2025 & 2026 filings")
    canvas.drawString(1.8 * cm, H - 10.9 * cm, "Written for leadership and staff. Plain language first; grey boxes hold the technical detail.")
    canvas.setFont("Helvetica", 7.5); canvas.setFillColor(C(MUTED)); canvas.drawString(1.8 * cm, 1 * cm, "NIRF Analytics — Saveetha Engineering College")
    canvas.drawRightString(W - 1.8 * cm, 1 * cm, "Page 1")
    canvas.restoreState()


def footer(canvas, d):
    canvas.saveState()
    canvas.setStrokeColor(C(CORAL)); canvas.setLineWidth(1.2); canvas.line(1.8 * cm, 1.45 * cm, 4.3 * cm, 1.45 * cm)
    canvas.setStrokeColor(C(LINE)); canvas.setLineWidth(0.5); canvas.line(4.3 * cm, 1.45 * cm, W - 1.8 * cm, 1.45 * cm)
    canvas.setFont("Helvetica", 7.5); canvas.setFillColor(C(MUTED))
    canvas.drawString(1.8 * cm, 1 * cm, "NIRF Analytics — Saveetha Engineering College · internal report")
    canvas.drawRightString(W - 1.8 * cm, 1 * cm, f"Page {d.page}")
    canvas.restoreState()


# ---------------- story ----------------
doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.9 * cm,
                        title="Getting back into the NIRF top 100 — Saveetha Engineering College", author="NIRF Analytics project")
S = []

S += [Spacer(1, 11.8 * cm)]
S += [tiles([("Band 201-300", "Our NIRF 2025 position (Engineering). Same in 2024.", CORAL),
             (f"≈ {e26['total_est']:.0f}", "Our estimated score from the 2026 filing", SKY),
             (f"{thr['100']:.0f}", "Score we forecast for rank 100 in 2026", GOLD),
             (f"{100 * bp[s['most_likely_band']]:.0f}% · {s['most_likely_band']}", "Most likely band for 2026", TEAL)])]
S += [fig("cutoff", 16.8 * cm)]
S += [p("The blue line is the score you need to be ranked 100. It has climbed every year since 2019. The red dots are us: our two published "
        "scores, and our estimates for the last two filings. We are moving up, but not yet faster than the line.", SMALL)]
S += [PageBreak()]

# 1 summary
S += [section("1", "The short version")]
S += [p("We were ranked <b>91 in 2017</b> and <b>124 in 2019</b>. In 2024 and 2025 NIRF placed us in the <b>201-300 band</b>. NIRF publishes no scores for "
        "bands, so until this project nobody could say what our numbers actually were. Now we can, at least approximately.", LEAD)]
S += [p(f"<b>Why we slipped.</b> Mostly because everyone else moved. The score for rank 100 went from 41.9 in 2023 to 44.0 in 2024 to 45.6 in 2025, and we "
        f"expect about {thr['100']:.0f} in 2026. Our own filing is worth roughly {e25['total_est']:.0f} points in 2025 and {e26['total_est']:.0f} in 2026 by our model. "
        f"That is real improvement, about 2.5 points in a year, but the line rises about 1.5 a year, so the gap closes slowly.")]
S += [p(f"<b>Where the gap is.</b> One place, really: <b>research</b>. Our estimated Research score is about {e26['rpc']:.0f}. Colleges ranked 76-100 average about 30. "
        f"Behind that: we award 12 PhDs a year (they award 24), we have 61 full-time PhD scholars (they have 163), and we bring in about Rs 30 lakh of sponsored research a year "
        f"(they bring in Rs 3.7 crore). Placements, graduation rate and women's participation are already fine. This is not a broad problem. It is a specific one.")]
S += [p(f"<b>2026.</b> The most likely result is the <b>{s['most_likely_band']} band</b>, one step up. We put the chance of the top 100 in 2026 at about "
        f"{100 * bp['top 100']:.0f}%, and the chance of the top 200 at about {100 * top200:.0f}%. Those are honest numbers with real uncertainty in them; section 8 explains why.")]
S += [callout("The single biggest lever is PhD output. Going from 12 to 80 PhDs a year is worth an estimated 3.7 points. Doubling operating spend per student adds about 2. "
              "Reaching 200 full-time scholars adds 1.4, and lifting median salary to Rs 10 lakh adds 1.4. A serious publication push adds more on top, which our model "
              "cannot yet measure. Done together, these close the gap in two to three ranking cycles.", col=CORAL, label="What to do")]
S += [p("<b>What we built to find this out.</b> A database of every NIRF Engineering result since 2017, the raw data behind 704 institute submissions, a model that "
        "reverse-engineers NIRF's scoring, a 2026 forecast, and a web app with dashboards, what-if sliders, a live data form for staff, and an AI assistant that "
        "answers questions from the data. Everything runs on free tools.")]
S += [PageBreak()]

# 2 NIRF
S += [section("2", "How NIRF actually scores us", SKY)]
S += [p("NIRF is the Ministry of Education's annual ranking, run since 2016 by the National Board of Accreditation. Institutions apply voluntarily and upload their own data; "
        "publication and patent counts are pulled from Scopus, Web of Science and the patent office. Everyone gets a score out of 100 from five parameters, added up with fixed weights:")]
S += [Table([[Paragraph(f"Total  =  <font color='{SKY}'><b>0.30 × TLR</b></font>  +  <font color='{CORAL}'><b>0.30 × RPC</b></font>  +  <font color='{TEAL}'><b>0.20 × GO</b></font>  +  <font color='{GOLD}'><b>0.10 × OI</b></font>  +  <font color='{PLUM}'><b>0.10 × PR</b></font>",
                          ParagraphStyle("f", parent=BODY, alignment=TA_CENTER, fontSize=11.5, leading=15))]], colWidths=[17.3 * cm],
             style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), C("#F6F8FB")), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)])), Spacer(1, 8)]
meth = pd.read_sql("SELECT parameter, parameter_weight, sub_parameter, sub_code, marks FROM methodology WHERE year=2025 AND category='Engineering'", con)
_order = {"TLR": 0, "RPC": 1, "GO": 2, "OI": 3, "PR": 4}
_sub = ["SS", "FSR", "FQE", "FRU", "PU", "QP", "IPR", "FPPP", "GPH", "GUE", "GMS", "GPHD", "RD", "WD", "ESCS", "PCS", "PR"]
meth["_k"] = meth.parameter.map(_order) * 100 + meth.sub_code.map(lambda c: _sub.index(c) if c in _sub else 99)
meth = meth.sort_values("_k")
names = {"TLR": "Teaching, Learning & Resources", "RPC": "Research & Professional Practice", "GO": "Graduation Outcomes", "OI": "Outreach & Inclusivity", "PR": "Perception"}
plain = {"SS": "How many students you have, incl. PhD scholars", "FSR": "Faculty-student ratio; 1:15 earns full marks", "FQE": "Share of faculty with a PhD, and a healthy experience mix",
         "FRU": "Money spent per student, capital and operating", "PU": "Publications per faculty (Scopus / Web of Science)", "QP": "Citations and top-25% papers per faculty",
         "IPR": "Patents published and granted", "FPPP": "Research funding and consultancy income", "GPH": "Share placed plus share going to higher studies",
         "GUE": "Share graduating on time; 80% earns full marks", "GMS": "Median salary of placed graduates", "GPHD": "PhDs awarded per year",
         "RD": "Students from other states and countries", "WD": "Women students (target 50%) and women faculty (20%)", "ESCS": "Students on full fee reimbursement",
         "PCS": "Facilities for physically challenged students", "PR": "A survey of employers and academics"}
rows = [["Parameter", "Sub-parameter", "Marks", "In plain words"]]
for _, m in meth.iterrows():
    rows.append([f"<font color='{PCOL[m.parameter.lower()]}'><b>{m.parameter}</b></font> · {names[m.parameter]} (weight {m.parameter_weight:.2f})",
                 f"{m.sub_parameter} <font color='{MUTED}'>({m.sub_code})</font>", str(m.marks), plain.get(m.sub_code, "")])
t = table(rows, widths=[4.7 * cm, 5.4 * cm, 1.2 * cm, 6.0 * cm])
t.setStyle(TableStyle([("BACKGROUND", (0, i), (0, i), C(TINT[PCOL[m.parameter.lower()]])) for i, (_, m) in enumerate(meth.iterrows(), start=1)]))
S += [t, Spacer(1, 6)]
S += [tech("The formulas NIRF publishes (Engineering 2025). FSR = 30 × [15 × (F/N)] with F = full-time faculty and N = students incl. PhD scholars; zero below 1:50. "
           "FQE = 10 × (FRA/95) for the PhD share plus up to 10 for an even spread over ≤8, 8-15 and >15 years of experience. FRU = 7.5 × f(BC) + 22.5 × f(BO) on capital and operating spend per student. "
           "PU = 35 × f(P/FRQ) − 5 × f(Pret); retracted papers now cost marks. QP = 20 × f(CC/FRQ) + 20 × f(TOP25P/P) − 5 × f(Cret). IPR = 10 × f(patents granted) + 5 × f(patents published). "
           "GPH = 40 × (Np/100 + Nhs/100). GUE = 15 × min(Ng/80, 1). GMS = 25 × f(median salary). GPHD = 20 × f(PhDs graduated). RD = 25 × (share from other states) + 5 × (share from abroad). "
           "WD = 15 × (women students %/50) + 15 × (women faculty %/20). ESCS = 20 × f(fee-reimbursed %). The f( ) curves are NIRF's own normalisation and are not published. That is the gap our model fills.")]
S += [callout("Two things that confuse people. First, only the top 100 get a numeric rank; everyone below is put in a band (101-150, 151-200, 201-300) with no score. "
              "Second, <b>Saveetha Engineering College</b> (a college in Sriperumbudur, NIRF id IR-E-C-16590) is a different NIRF entity from <b>Saveetha Institute of Medical and "
              "Technical Sciences</b> (a deemed university in Chennai, ranked 45 in 2025). This report is about the college only.", col=GOLD, label="Worth knowing")]

# 3 history
S += [section("3", "Our record, year by year", CORAL)]
hrows = [["Year", "Category", "Position", "Total", "TLR", "RPC", "GO", "OI", "PR"]]
for _, h in hist.iterrows():
    pos = f"Rank {int(h.rank_or_band_low)}" if h.status == "ranked" else f"Band {int(h.rank_or_band_low)}-{int(h.rank_or_band_high)}"
    fm = lambda v: "–" if pd.isna(v) else f"{v:.2f}"
    hrows.append([str(int(h.year)), h.category, pos, fm(h.score), fm(h.tlr), fm(h.rpc), fm(h["go"]), fm(h.oi), fm(h.pr)])
S += [table(hrows, widths=[1.3 * cm, 2.4 * cm, 2.8 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm], align="CENTER")]
S += [p("A dash means NIRF published nothing (band placement). We also applied in 2021, 2022 and 2023 and were placed beyond the published lists. "
        "Look at the two years with scores: TLR, GO and OI were respectable. <b>RPC was 4.7 and 3.0.</b> Perception was close to zero. The story has not changed much since.", SMALL)]
S += [p("What the last two filings are worth, by our model", H2)]
erows = [["Filing", "TLR", "RPC", "GO", "OI", "PR (assumed)", "Estimated total", "Rank-100 line that year"]]
for e_ in sec_est:
    erows.append([str(e_["year"]), f"{e_['tlr']:.1f}", f"{e_['rpc']:.1f}", f"{e_['go']:.1f}", f"{e_['oi']:.1f}", f"{e_['pr_assumed']:.1f}", f"<b>{e_['total_est']:.1f}</b>", "45.55" if e_["year"] == 2025 else f"≈ {thr['100']:.1f}"])
S += [table(erows, align="CENTER")]
S += [p(f"A useful check: the 2025 filing comes out at {e25['total_est']:.1f}, which sits inside the 201-300 band NIRF actually announced. The model was never told that. "
        "The 2026 filing shows genuine progress: graduation rate 61% → 81%, placements 92% → 97%, operating spend per student Rs 80k → Rs 1.1 lakh, PhDs 9 → 12 a year.")]
S += [KeepTogether([fig("compare", 16 * cm), p("Our estimated parameters (coloured) against institutes ranked 76-100 and 1-10 in 2025. Four of the five bars are close to the 76-100 tier. RPC is not.", SMALL)])]
S += [p(" (coloured) against institutes ranked 76-100 and 1-10 in 2025. Four of the five bars are close to the 76-100 tier. RPC is not.", SMALL)]

# 4 data
S += [section("4", "What we collected", TEAL)]
counts = {t_: con.execute(f"SELECT COUNT(*) FROM {t_}").fetchone()[0] for t_ in ("rankings", "rank_bands", "participants", "submissions", "faculty", "methodology", "documents")}
drows = [["Source", "What it gives us", "Size"],
         ["nirfindia.org ranking pages", "Engineering, Overall, College and University lists 2017-2025: rank, total and the five parameter scores (Engineering ranks 1-200 for 2019-22)", f"{counts['rankings']:,} ranked rows"],
         ["nirfindia.org band pages", "Who was placed in 101-150 / 151-200 / 201-300, with no scores", f"{counts['rank_bands']:,} rows"],
         ["nirfindia.org participant lists", "Every institution that applied, per year and category", f"{counts['participants']:,} rows"],
         ["Per-institute data PDFs", "The raw data each ranked Engineering institute submitted: intake, enrolment by gender, state and category, placements, median salary, higher studies, PhDs, capital and operating spend, sponsored research, consultancy, patents, facilities. Top 100 for 2023-25; top 200 for 2021-22", f"{counts['submissions']:,} PDFs parsed"],
         ["NIRF methodology PDFs", "Official definitions, marks and formulas for 2023, 2024 and 2025 (Engineering, Overall, College)", f"{counts['methodology']} sub-parameter rows"],
         ["saveetha.ac.in NIRF page", "Our own NIRF 2025 filings (Engineering, Innovation, SDG) and the NIRF 2026 Engineering filing, including the full faculty list", "4 PDFs · 1,575 faculty rows"],
         ["Full text of all of the above", "So the AI assistant can search it", f"{counts['documents']} documents"]]
S += [table(drows, widths=[4 * cm, 10 * cm, 3.3 * cm], headcol=TEAL)]
S += [tech("Data quality fixes. The 2016 pages on nirfindia.org silently return the 2017 tables, so 2016 is dropped. In years with 200 numeric ranks the pages labelled '101-150' and "
           "'151-200' actually hold ranks 201-250 and 251-300; they are relabelled. Band pages carry no institute IDs, so band rows are linked to institutions through a normalised name key. "
           "PDFs are converted with pdftotext -layout and parsed with regular expressions; every numeric field the model uses has over 96% coverage. Faculty lists appear only in our own PDFs, "
           "not in the NIRF-hosted ones, so faculty PhD share is unavailable for other institutes.")]
S += [p("Our raw numbers next to the top 100 (2025)", H2)]
prof = pd.DataFrame(A["raw_profile_2025"]).set_index("metric")
show = ["students_total", "faculty_entered", "students_per_faculty", "phd_pursuing_ft", "phd_grad_3y_avg", "graduation_rate", "placement_rate", "median_salary_ug",
        "capex_per_student", "opex_per_student", "sponsored_amount_3y_avg", "consultancy_amount_3y_avg", "women_students_pct", "outside_state_pct"]
lab = {"students_total": "Students (UG+PG)", "faculty_entered": "Faculty", "students_per_faculty": "Students per faculty", "phd_pursuing_ft": "Full-time PhD scholars",
       "phd_grad_3y_avg": "PhDs awarded / year", "graduation_rate": "Graduating on time", "placement_rate": "Placed", "median_salary_ug": "Median UG salary",
       "capex_per_student": "Capital spend / student", "opex_per_student": "Operating spend / student", "sponsored_amount_3y_avg": "Sponsored research / yr",
       "consultancy_amount_3y_avg": "Consultancy / yr", "women_students_pct": "Women students", "outside_state_pct": "Students from other states"}
money = {"median_salary_ug", "capex_per_student", "opex_per_student", "sponsored_amount_3y_avg", "consultancy_amount_3y_avg"}; pct = {"graduation_rate", "placement_rate"}
weak = {"phd_pursuing_ft", "phd_grad_3y_avg", "median_salary_ug", "capex_per_student", "opex_per_student", "sponsored_amount_3y_avg", "consultancy_amount_3y_avg", "outside_state_pct"}
def fmtv(v, k):
    if pd.isna(v): return "–"
    if k in money: return inr(v)
    if k in pct: return f"{100 * v:.0f}%"
    if k in ("women_students_pct", "outside_state_pct"): return f"{v:.0f}%"
    return f"{v:,.1f}" if v % 1 else f"{v:,.0f}"
prows = [["Metric", "Top 10 (median)", "Rank 76-100 (median)", "Colleges in top 100", "Us, 2025 filing", "Us, 2026 filing"]]
for k in show:
    rw = prof.loc[k]; v26 = fmtv(rw.saveetha_2026_filing, k)
    prows.append([lab[k], fmtv(rw.top10_median, k), fmtv(rw.rank76_100_median, k), fmtv(rw.colleges_top100_median, k), fmtv(rw.saveetha_2025_filing, k),
                  f"<font color='{CORAL if k in weak else TEAL}'><b>{v26}</b></font>"])
S += [table(prows, widths=[4.2 * cm, 2.6 * cm, 2.8 * cm, 2.8 * cm, 2.5 * cm, 2.5 * cm], align="CENTER", headcol=TEAL)]
S += [p(f"<font color='{CORAL}'><b>Red</b></font> = well below the 76-100 tier. <font color='{TEAL}'><b>Green</b></font> = at or above it. The pattern is hard to miss: everything to do with "
        "research, PhDs and money per student is red; everything to do with students, placements and inclusion is green.", SMALL)]
S += [PageBreak()]

# 5 architecture
S += [section("5", "How the system works", GOLD)]
S += [fig("architecture", 16.8 * cm)]
S += [p("Think of it as a pipeline. Scripts fetch the public data (1) and turn web tables and PDFs into clean rows (2), which land in one database file (3). "
        "The models (4) learn from the 700 institutes where we know both the raw data and the published score, then score us. The analysis step (5) produces the comparisons "
        "and gap figures, and the app (6) shows all of it, lets staff enter live numbers, and answers questions through an AI assistant. When NIRF 2026 comes out, one command refreshes everything.")]
S += [tech("Stack: Python 3.13; requests + BeautifulSoup for scraping; poppler pdftotext + regex for PDF parsing; pandas; SQLite; XGBoost and scikit-learn for models; Streamlit + Plotly for the app; "
           "rank-bm25 for document retrieval; Groq (gpt-oss-120b) as the chat model with Gemini as fallback, both on free tiers. No paid service anywhere. "
           "Layout: scraper/ (4 scripts) · models/ (score_model.py, predict_2026.py, artifacts/) · analysis/analyze.py · app/ (Home.py, common.py, pages/1-6, rag/) · "
           "data/raw (html, pdf, pdf_text, methodology, saveetha) · data/processed (CSV + JSON) · db/nirf.db · docs/.")]

# 6 model
S += [section("6", "The model: estimating scores NIRF never published", CORAL)]
S += [p("<b>The problem.</b> NIRF tells us the formula but hides the curves f( ) that turn a raw number, say a median salary of Rs 8 lakh, into marks. Without them nobody can compute a score from raw data.")]
S += [p("<b>The idea.</b> For 700 institute-years we have both sides: the raw numbers they submitted and the parameter scores NIRF gave them. So we let a model learn the mapping, "
        "one model per parameter, using only the inputs NIRF says that parameter depends on. Then we feed our own filing through the same models.")]
S += [p("<b>Why this model.</b> NIRF's curves bend and flatten: after a point, more money buys no more marks. A straight-line model gets that wrong (we tried; R² about 0.5). "
        "Tree-based gradient boosting (XGBoost) captures bent curves well on a few hundred rows. We added <b>monotone constraints</b>, which force common sense into it: more placements can never lower GO, "
        "more spend can never lower TLR. That stops the model learning accidental patterns and makes the what-if sliders behave. A neural network would need far more data; "
        "fitting each f( ) curve by hand would mean too many unknowns for 700 rows.")]
mrows = [["Parameter", "Rows", "Cross-validated R²", "Typical error", "What the model found matters most"]]
for k, v in mp.items():
    mrows.append([f"<font color='{PCOL[k]}'><b>{k.upper()}</b></font>", str(v["n"]), f"{v['cv_r2']:.2f}", f"{v['cv_mae']:.1f} pts", ", ".join(list(v["importance"])[:3]).replace("_", " ")])
S += [table(mrows, widths=[2 * cm, 1.4 * cm, 3.2 * cm, 2.6 * cm, 8 * cm]), Spacer(1, 4)]
S += [p(f"R² of 1.0 would be perfect; 0.7-0.8 means the model explains most of the variation. Cross-validation is grouped by institute, so a college's other years are never used to predict it. "
        f"Combining the four estimates with the published Perception score reproduces published totals with an average error of <b>{M['total_score_fit']['mae']} points</b> (R² {M['total_score_fit']['r2']}).", SMALL)]
S += [callout("Publications and citations are 75 of RPC's 100 marks and are not in the PDFs, so RPC is estimated from PhD output, funding and faculty size. That is why its error is the largest. "
              "Perception is a survey and cannot be modelled from data; we treat it as an uncertainty drawn from private colleges ranked 60-100 (median about 12, but it can be near zero). "
              "The model is trained on institutes ranked 1-200, so it is most reliable there, which is where our 2026 filing sits.", col=GOLD, label="Known limits")]

# 7 results
S += [section("7", "The 2025 picture", SKY)]
S += [fig("tiers", 16 * cm)]
S += [p(f"Research (RPC) and Perception climb steeply with rank; TLR, GO and OI are much flatter. In 2025 the top 100 held {A['type_mix']['2025']['University']} universities, "
        f"{A['type_mix']['2025']['College']} colleges and {A['type_mix']['2025']['Institute (deemed / national importance)']} deemed or national institutes. The number of colleges fell from 12 in 2023 to 9 in 2025. "
        "It is getting harder for a college to be there at all.", SMALL)]
tn = pd.DataFrame(A["tamil_nadu_2025"])
tnrows = [["Rank", "Tamil Nadu institutions in the 2025 Engineering top 100", "Type", "Total", "RPC"]]
for x_ in tn.to_dict("records"):
    nm = f"<font color='{CORAL}'><b>{x_['name']}</b></font>" if x_["type_label"] == "College" else x_["name"]
    tnrows.append([str(int(x_["rank"])), nm, x_["type_label"].split(" ")[0], f"{x_['score']:.2f}", f"{x_['rpc']:.1f}"])
S += [table(tnrows, widths=[1.3 * cm, 9.6 * cm, 2.2 * cm, 1.8 * cm, 1.8 * cm]), Spacer(1, 4)]
S += [p("Only three of the fourteen are colleges like us: SSN (rank 47), PSG Tech (67) and Sri Krishna CET (100, exactly on the line). Those three are the realistic role models, and their RPC scores are the number to study.", SMALL)]
S += [p("Where the points go missing", H2)]
grows = [["Parameter", "Rank 90-100 average", "Our estimate", "Gap", "× weight = points lost"]]
for k in ["tlr", "rpc", "go", "oi", "pr"]:
    est_v = e26["pr_assumed"] if k == "pr" else e26[k]
    grows.append([f"<font color='{PCOL[k]}'><b>{k.upper()}</b></font>", f"{est_v + gap[k]:.1f}", f"{est_v:.1f}", f"{gap[k]:+.1f}", f"<font color='{CORAL if wgap[k] > 1 else INK}'><b>{wgap[k]:+.2f}</b></font>"])
S += [table(grows, align="CENTER")]
S += [p(f"Research alone accounts for about {wgap['rpc']:.1f} of the roughly {sum(v for v in wgap.values() if v > 0):.1f} weighted points between us and the rank-100 line. TLR and OI (students from other states) cover most of the rest. GO is nearly level.", SMALL)]

# 8 prediction
S += [section("8", "What 2026 probably looks like", PLUM)]
S += [fig("bands", 15.5 * cm)]
S += [tiles([(f"{s['total_score']['median']}", f"Estimated total. 80% of the time between {s['total_score']['p10']} and {s['total_score']['p90']}", PLUM),
             (f"≈ rank {s['expected_rank']}", "Expected position on the 2026 threshold curve", SKY),
             (f"{100 * top200:.0f}%", "Chance of being in the top 200", TEAL),
             (f"{s['gap_to_top100']:.1f} pts", f"Gap to the top 100 (needs ≈ {thr['100']:.0f})", CORAL)])]
trows = [["Rank in 2026", "100", "125", "150", "175", "200", "250", "300"], ["Score you will need (forecast)"] + [f"{thr[k]:.1f}" for k in ["100", "125", "150", "175", "200", "250", "300"]]]
S += [table(trows, align="CENTER", zebra=False, headcol=PLUM)]
S += [tech("How the forecast is built. (a) Thresholds: the rank-100 cut-off has risen linearly since 2020 (+1.5 a year); the shape of score-vs-rank below 100 comes from 2019-22, when NIRF published 200 ranks, "
           "extrapolated to 300 on a log-rank scale. (b) Us: parameter estimates from the score model on the 2026 filing; 20,000 Monte-Carlo draws add each model's cross-validated error, a Perception score "
           "drawn from private colleges ranked 60-100, and the threshold trend's own residual; each draw is placed in a band. (c) Everyone else: a ridge regression on last year's score, parameters and momentum "
           f"predicts every 2025 top-100 institute's 2026 score. Tested by predicting 2025 from 2024 it errs by {val['mae']} points on average, against {val['naive_mae_no_change']} for assuming no change, "
           f"and reproduces the rank order with Spearman {val['rank_spearman_top100']}.")]
S += [p("<b>Reading the probabilities.</b> The wide range is honest. Most of it comes from Perception, a survey we cannot see, and from RPC, where publications are missing from the PDFs. "
        "If our Scopus output is strong, the real result will sit towards the top of the range.")]

# 9 levers
S += [section("9", "What moves the score, and what we should do", CORAL)]
S += [fig("levers", 16 * cm)]
S += [p("Each bar is one change applied on its own to the 2026 filing. They add up roughly, so a programme can be sized from this chart.", SMALL)]
S += [p("Priorities, in order", H2)]
S += [Paragraph(x_, BUL, bulletText="•") for x_ in [
    "<b>Start the PhD pipeline now.</b> PhDs awarded (GPHD, 20 marks of GO; also feeds TLR and RPC) is the biggest single lever: 12 → 40 a year is worth about +2.2, 12 → 80 about +3.7. "
    "Enrol many more full-time scholars this year (61 → 200 is +1.4) because awards lag enrolment by three to four years.",
    "<b>Publish, and get cited.</b> 75 of RPC's 100 marks. Our model cannot see this, but the 76-100 tier averages RPC ≈ 30 against our ≈ 13. Set Scopus targets per department, reward Q1/Q2 papers, "
    "and record counts on the app's Live Data page so the next model version can use them. Avoid retractions: NIRF now deducts marks for them.",
    "<b>Spend more per student, on the right things.</b> FRU is 30 marks of TLR. Operating spend Rs 1.1 lakh → Rs 2 lakh per student is worth about +2.0; capital spend Rs 18k → Rs 60k about +0.8. Labs, e-resources and equipment count; buildings do not.",
    "<b>Lift the median salary.</b> 25 marks of GO. Rs 5.5 lakh → Rs 8 lakh is +0.8; → Rs 10 lakh is +1.4. It is the median, so the middle of the batch matters more than a few star offers.",
    "<b>Chase funded projects.</b> Rs 30 lakh → Rs 10 crore a year of sponsored research is about +1.0. DST, AICTE, SERB and industry projects all count; consultancy needs real receipts.",
    "<b>Admit from outside Tamil Nadu.</b> RD is 30 marks of OI; we are at 7.6% against 57% for the tier. Out-of-state and international admissions are a cheap +0.3 to +0.5.",
    "<b>Protect what already works.</b> Placement (97%), graduation on time (81%), women students (33%) and fee-reimbursement coverage (52%) are at or above the tier.",
]]
S += [callout("The gap is about 7 points today and grows about 1.5 a year. A programme that delivers PhDs → 40 a year, spend per student → Rs 2 lakh, median salary → Rs 8 lakh, scholars → 200 and a visible "
              "publication push is worth an estimated 6-8 points, plus whatever the publications add. That puts the top 150 within reach next year and the top 100 within two to three cycles.", col=TEAL, label="Sizing the goal")]
S += [PageBreak()]

# 10 app
S += [section("10", "The app, and where things live", TEAL)]
arows = [["Page", "What it is for"],
         ["Home", "One screen: our band, the cut-off trend, the 2026 forecast, and how the top 100 earns its points"],
         ["Top 100 Explorer", "Every ranked Engineering institute 2017-2025. Filter by year, state, type; see parameter scores, the weighted 'score anatomy', the raw numbers each institute submitted, and any institute's history"],
         ["Saveetha Position", "Our full NIRF history, estimated parameter scores, the gap table, raw numbers against the tiers, and the paths of Tamil Nadu colleges that reached the top 100"],
         ["Gap & What-If", "A slider for every lever (PhDs, salary, spend, research, diversity). The model re-scores instantly and shows the implied 2026 band"],
         ["Prediction 2026", "Forecast thresholds, band probabilities, model accuracy, and the projected 2026 order of the 2025 top 100"],
         ["Live Data Entry", "Staff type in this year's numbers (placements, salary, PhDs, spend, Scopus counts). Entries are time-stamped and kept; the model re-scores with the live values"],
         ["Ask the Data", "An AI assistant that writes database queries, reads the methodology and the 700 submissions, and can fetch nirfindia.org live ('has NIRF 2026 been released?'). It shows the queries it ran, so answers can be checked"]]
S += [table(arows, widths=[3.4 * cm, 13.9 * cm], headcol=TEAL)]
S += [p("<b>Running it.</b> On a laptop: <font face='Courier'>./run.sh</font>, then open http://localhost:8501. After NIRF 2026 is published: <font face='Courier'>./pipeline.sh</font> refreshes everything. "
        "The next step is a free public link on Streamlit Community Cloud so staff can open it on a phone.")]
S += [p("Folder structure", H2)]
S += [Table([[Paragraph("""<b>scraper/</b>   scrape_rankings.py · download_pdfs.py · parse_pdfs.py · build_db.py — collect and store<br/>
<b>models/</b>    score_model.py (learns NIRF's f curves) · predict_2026.py (forecast) · artifacts/ (trained model)<br/>
<b>analysis/</b>  analyze.py — cut-offs, tiers, movers, peers, our gap → data/processed/analysis.json<br/>
<b>app/</b>       Home.py · common.py · pages/1-6 · rag/index.py (document search) · rag/chat.py (AI assistant)<br/>
<b>data/raw/</b>  html/ pdf/ pdf_text/ methodology/ saveetha/ — everything downloaded, untouched, kept for audit<br/>
<b>data/processed/</b>  rankings.csv · submissions.csv · faculty.csv · analysis.json · prediction_2026.json · model_report.json<br/>
<b>db/nirf.db</b>   the one database file (SQLite); any SQL tool can open it<br/>
<b>docs/</b>      this report and the script that builds it · <b>README.md</b> · <b>.env</b> (API keys, never shared) · <b>run.sh</b> · <b>pipeline.sh</b>""", CODE)]],
            colWidths=[17.3 * cm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), C("#F6F8FB")), ("LINEBEFORE", (0, 0), (0, 0), 3, C(TEAL)), ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))]

# 11 caveats
S += [section("11", "Caveats, and a glossary", GOLD)]
S += [Paragraph(x_, BUL, bulletText="•") for x_ in [
    "Our scores are <b>estimates</b>. NIRF has never published them for 2020-2025. They are calibrated on 700 institute-years and pass a sanity check against the published band, but they are not official numbers. "
    "If someone quotes 'our RPC is 13', the honest phrasing is 'estimated at about 13'.",
    "Publications, citations and Perception cannot be seen in the data. They are the main sources of uncertainty and are shown as ranges, not points.",
    "The 2026 forecast assumes NIRF keeps the 2025 methodology. NIRF does adjust weights now and then; the pipeline re-reads the methodology PDF each year.",
    "The AI assistant can get wording wrong. It always shows the database queries it ran; check anything important against the dashboard.",
]]
grows2 = [["Term", "Meaning"], ["NIRF", "National Institutional Ranking Framework, the Ministry of Education's ranking"], ["TLR / RPC / GO / OI / PR", "The five scored parameters (section 2)"],
          ["Band", "A range such as 201-300 used instead of a number for institutes below rank 100; no score is published"], ["Cut-off", "The lowest score inside the top 100 in a given year"],
          ["Filing / submission", "The data form an institution uploads to NIRF, published as a PDF"], ["f( )", "NIRF's unpublished curve that converts a raw number into marks"],
          ["Model estimate", "A score computed by our model, not by NIRF"], ["R² / MAE", "Accuracy measures: share of variation explained / average error in points"],
          ["Monte Carlo", "Repeating a calculation thousands of times with random variation to get a range instead of one number"]]
S += [KeepTogether([p("Glossary", H2), table(grows2, widths=[4.2 * cm, 13.1 * cm], headcol=GOLD)])]

doc.build(S, onFirstPage=cover, onLaterPages=footer)
print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
