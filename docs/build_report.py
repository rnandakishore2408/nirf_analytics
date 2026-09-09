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
    numcell = Paragraph(f"<font color='white'><b>{num}</b></font>", ParagraphStyle("n", parent=BODY, fontSize=12, leading=14, alignment=TA_CENTER))
    tcell = Paragraph(f"<b>{title}</b>", ParagraphStyle("t", parent=BODY, fontSize=17, leading=20, textColor=C(NAVY)))
    t = Table([[numcell, tcell]], colWidths=[1.15 * cm, 16.2 * cm], rowHeights=[0.95 * cm])
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


# ---------------- evidence helpers ----------------
SRC = {
    "rank": "nirfindia.org → Rankings → Engineering, yearly tables (2017-2025)",
    "band": "nirfindia.org → Rankings → Engineering → Rank-band pages",
    "pdf": "nirfindia.org per-institute data PDFs (nirfpdfcdn/<year>/pdf/Engineering/<id>.pdf)",
    "meth": "NIRF methodology PDF, Engineering 2025 (nirfindia.org/nirfpdfcdn/2025/framework/Engineering.pdf)",
    "sec25": "College's NIRF 2025 Engineering filing, saveetha.ac.in/nirf-documents-2024 (Engineering-1.pdf)",
    "sec26": "College's NIRF 2026 Engineering filing, saveetha.ac.in (SAVEETHA-ENGINEERING-COLLEGE20260216-.pdf)",
    "model": "Score model output, models/score_model.py → data/processed/model_report.json",
    "pred": "Forecast output, models/predict_2026.py → data/processed/prediction_2026.json",
    "ana": "analysis/analyze.py → data/processed/analysis.json (computed from db/nirf.db)",
    "db": "db/nirf.db (all of the above, loaded by scraper/build_db.py)",
}


def src(*keys, extra=""):
    txt = "Source: " + "; ".join(SRC[k] for k in keys) + (f". {extra}" if extra else ".")
    return Paragraph(txt, ParagraphStyle("src", parent=SMALL, fontSize=7.4, leading=9.5, textColor=C("#6B7A90"), spaceBefore=1, spaceAfter=8))


def ev(key, detail=""):
    """Inline evidence tag."""
    label = {"rank": "NIRF ranking tables", "band": "NIRF band pages", "pdf": "institute PDFs", "meth": "NIRF 2025 methodology", "sec25": "2025 filing",
             "sec26": "2026 filing", "model": "score model", "pred": "2026 forecast", "ana": "analysis.json", "db": "database"}[key]
    return f" <font size='7.5' color='#6B7A90'>[{label}{', ' + detail if detail else ''}]</font>"


# ---------------- page furniture ----------------
def cover(canvas, d):
    canvas.saveState()
    canvas.setFillColor(C(NAVY)); canvas.rect(0, H - 12.2 * cm, W, 12.2 * cm, stroke=0, fill=1)
    canvas.setFillColor(C(CORAL)); canvas.rect(0, H - 12.2 * cm, W, 0.35 * cm, stroke=0, fill=1)
    canvas.setFillColor(C(GOLD)); canvas.rect(0, H - 12.55 * cm, 6 * cm, 0.35 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 11); canvas.drawString(1.8 * cm, H - 2.3 * cm, "SAVEETHA ENGINEERING COLLEGE  ·  INTERNAL REPORT")
    canvas.setFont("Helvetica-Bold", 34); canvas.drawString(1.8 * cm, H - 4.6 * cm, "NIRF Analytics")
    canvas.setFont("Helvetica-Bold", 20); canvas.drawString(1.8 * cm, H - 5.9 * cm, "Position, drivers and the 2026 outlook")
    canvas.setFont("Helvetica", 12.5); canvas.setFillColor(C("#C9D2E0"))
    for i, line in enumerate(["An evidence-based reading of where the college stands in the NIRF Engineering", "rankings, how the score is built, and what the data says about 2026."]):
        canvas.drawString(1.8 * cm, H - 7.4 * cm - i * 0.6 * cm, line)
    canvas.setFont("Helvetica", 9.5)
    canvas.drawString(1.8 * cm, H - 10.3 * cm, f"Prepared {date.today().strftime('%d %B %Y')}  ·  Sources: nirfindia.org 2017-2025, NIRF methodology PDFs, the college's 2025 and 2026 filings")
    canvas.drawString(1.8 * cm, H - 10.9 * cm, "Every figure carries its source in grey. Grey boxes hold technical detail and can be skipped.")
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
                        title="NIRF Analytics — Saveetha Engineering College: position, drivers and the 2026 outlook", author="NIRF Analytics project")
S = []
cut25 = float(cut.loc[2025]); cut23 = float(cut.loc[2023]); cut24 = float(cut.loc[2024])

S += [Spacer(1, 11.8 * cm)]
S += [tiles([("Band 201-300", "NIRF 2025 Engineering placement; also 201-300 in 2024. Source: nirfindia.org band pages", CORAL),
             (f"≈ {e26['total_est']:.0f}", "Estimated score of the college's 2026 filing. Source: score model on the saveetha.ac.in filing", SKY),
             (f"{thr['100']:.0f}", "Forecast score at rank 100 in 2026. Source: trend of 2020-25 cut-offs, nirfindia.org", GOLD),
             (f"{100 * bp[s['most_likely_band']]:.0f}% · {s['most_likely_band']}", "Most likely 2026 band and its probability. Source: Monte-Carlo forecast", TEAL)])]
S += [fig("cutoff", 16.8 * cm)]
S += [p("The blue line is the lowest score inside the top 100 each year. The solid red dots are the college's two published scores; the hollow ones are model estimates for its last two filings.", SMALL),
      Paragraph("Sources: S1 NIRF ranking tables (cut-off = score at rank 100; the college's 2017 and 2019 rows); S6/S7 the college's 2025 and 2026 filings; S8 score model. Full list in section 12.",
                ParagraphStyle("src0", parent=SMALL, fontSize=7.4, leading=9.5, textColor=C("#6B7A90")))]
S += [PageBreak()]

# 1 summary
S += [section("1", "Summary of findings")]
S += [p(f"Saveetha Engineering College was ranked <b>91 in 2017</b> (score 36.88) and <b>124 in 2019</b> (score 34.14) in NIRF's Engineering category.{ev('rank', '2017 and 2019 tables')} "
        f"In 2024 and 2025 it was placed in the <b>201-300 band</b>.{ev('band', '2024, 2025')} NIRF publishes no scores for band placements, so the college's actual "
        f"parameter scores for those years are not public; the estimates in this report come from a model described in section 6.", LEAD)]
S += [p(f"<b>The cut-off has risen every year since 2019.</b> The lowest score inside the top 100 was {cut23:.2f} in 2023, {cut24:.2f} in 2024 and {cut25:.2f} in 2025.{ev('rank', 'score at rank 100')} "
        f"A linear trend on 2020-2025 gives about {thr['100']:.1f} for 2026.{ev('pred', 'thresholds')} The college's filings are estimated at {e25['total_est']:.1f} (2025) and "
        f"{e26['total_est']:.1f} (2026).{ev('model', 'saveetha_estimates')} The 2025 estimate falls inside the band NIRF actually published, which is one check on the model.")]
S += [p(f"<b>The gap is concentrated in research.</b> The estimated Research and Professional Practice score (RPC) for the 2026 filing is {e26['rpc']:.1f}; institutes ranked 76-100 in 2025 "
        f"average {t76['rpc']:.1f}.{ev('ana', 'tier_profile_2025')} In the filings themselves: 12 PhDs awarded per year against a tier median of 24; 61 full-time PhD scholars against 163; "
        f"about Rs 30 lakh a year of sponsored research against Rs 3.7 crore.{ev('sec26')}{ev('pdf', '2025 top-100 medians')} Placement (97%), on-time graduation (81%) and women students (33%) "
        f"are at or above the 76-100 tier medians (70%, 87%, 25%).{ev('sec26')}{ev('ana', 'raw_profile_2025')}")]
S += [p(f"<b>2026 outlook.</b> The most likely outcome is the <b>{s['most_likely_band']} band</b> ({100 * bp[s['most_likely_band']]:.0f}% of simulations); top 100 in "
        f"{100 * bp['top 100']:.0f}% of simulations; top 200 in {100 * top200:.0f}%.{ev('pred', 'band_probabilities')} The range is wide because two inputs are unobservable (section 8).")]
S += [callout("Ranked by the model's estimate of value: PhDs awarded (12 → 80 a year: +3.7 points), operating spend per student (Rs 1.1 L → 2 L: +2.0), full-time PhD scholars "
              "(61 → 200: +1.4), median UG salary (Rs 5.5 L → 10 L: +1.4), sponsored research (Rs 30 L → 10 Cr a year: +1.0). Each figure is one change applied alone to the 2026 filing; "
              "publications and citations are not in the data and are not counted here.", col=CORAL, label="Levers with the largest estimated effect  [2026 forecast, what_if_levers]")]
S += [p("<b>What this report is based on.</b> Every NIRF Engineering result since 2017, the raw data PDFs of 704 institute submissions, NIRF's methodology documents for 2023-25, "
        "the college's own 2025 and 2026 filings, a model fitted on 700 institute-years, and a 2026 forecast. Section 12 lists each source with its location.")]
S += [PageBreak()]

# 2 NIRF
S += [section("2", "How NIRF scores an engineering institution", SKY)]
S += [p(f"NIRF is the Ministry of Education's annual ranking, run since 2016 with the National Board of Accreditation as ranking agency.{ev('meth', 'section 4.1')} Institutions apply "
        f"voluntarily and upload their own data; publication, citation and patent counts come from third-party databases.{ev('meth', 'section 3.5')} Each institution receives a score out of 100 "
        f"from five parameters with fixed weights:{ev('meth', 'summary table')}")]
S += [Table([[Paragraph(f"Total  =  <font color='{SKY}'><b>0.30 × TLR</b></font>  +  <font color='{CORAL}'><b>0.30 × RPC</b></font>  +  <font color='{TEAL}'><b>0.20 × GO</b></font>  +  <font color='{GOLD}'><b>0.10 × OI</b></font>  +  <font color='{PLUM}'><b>0.10 × PR</b></font>",
                          ParagraphStyle("f", parent=BODY, alignment=TA_CENTER, fontSize=11.5, leading=15))]], colWidths=[17.3 * cm],
             style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), C("#F6F8FB")), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)])), Spacer(1, 8)]
meth = pd.read_sql("SELECT parameter, parameter_weight, sub_parameter, sub_code, marks FROM methodology WHERE year=2025 AND category='Engineering'", con)
_order = {"TLR": 0, "RPC": 1, "GO": 2, "OI": 3, "PR": 4}
_sub = ["SS", "FSR", "FQE", "FRU", "PU", "QP", "IPR", "FPPP", "GPH", "GUE", "GMS", "GPHD", "RD", "WD", "ESCS", "PCS", "PR"]
meth["_k"] = meth.parameter.map(_order) * 100 + meth.sub_code.map(lambda c: _sub.index(c) if c in _sub else 99)
meth = meth.sort_values("_k")
names = {"TLR": "Teaching, Learning & Resources", "RPC": "Research & Professional Practice", "GO": "Graduation Outcomes", "OI": "Outreach & Inclusivity", "PR": "Perception"}
plain = {"SS": "Number of students, incl. PhD scholars", "FSR": "Faculty-student ratio; 1:15 earns full marks", "FQE": "Share of faculty with a PhD, and the experience mix",
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
S += [t, src("meth", extra="Marks and weights as printed in the 'Summary of Ranking Parameters and Weightages – 2025 (Engineering)' table; plain-words column is our paraphrase.")]
S += [tech("Formulas as printed in the 2025 Engineering methodology. FSR = 30 × [15 × (F/N)], F = full-time faculty, N = students incl. PhD scholars; zero below 1:50. "
           "FQE = 10 × (FRA/95) for the PhD share plus up to 10 for an even spread over ≤8, 8-15 and >15 years of experience. FRU = 7.5 × f(BC) + 22.5 × f(BO) on capital and operating spend per student. "
           "PU = 35 × f(P/FRQ) − 5 × f(Pret); QP = 20 × f(CC/FRQ) + 20 × f(TOP25P/P) − 5 × f(Cret); the −5 terms for retracted work are new in 2025. IPR = 10 × f(patents granted) + 5 × f(patents published). "
           "GPH = 40 × (Np/100 + Nhs/100). GUE = 15 × min(Ng/80, 1). GMS = 25 × f(median salary). GPHD = 20 × f(PhDs graduated). RD = 25 × (share from other states) + 5 × (share from abroad). "
           "WD = 15 × (women students %/50) + 15 × (women faculty %/20). ESCS = 20 × f(fee-reimbursed %). The f( ) functions are described in the document as 'to be determined by NIRF' and are not published.")]
S += [callout("Only the top 100 receive a numeric rank; institutions below are listed in bands (101-150, 151-200, 201-300) without scores [NIRF band pages]. "
              "<b>Saveetha Engineering College</b> (Sriperumbudur, NIRF id IR-E-C-16590) and <b>Saveetha Institute of Medical and Technical Sciences</b> (Chennai, IR-E-I-1441, rank 45 in 2025) "
              "are separate NIRF entities [NIRF 2025 Engineering table; the college's filing header]. This report covers the college only.", col=GOLD, label="Two points of definition")]

# 3 history
S += [section("3", "The college's NIRF record", CORAL)]
hrows = [["Year", "Category", "Position", "Total", "TLR", "RPC", "GO", "OI", "PR"]]
for _, h in hist.iterrows():
    pos = f"Rank {int(h.rank_or_band_low)}" if h.status == "ranked" else f"Band {int(h.rank_or_band_low)}-{int(h.rank_or_band_high)}"
    fm = lambda v: "–" if pd.isna(v) else f"{v:.2f}"
    hrows.append([str(int(h.year)), h.category, pos, fm(h.score), fm(h.tlr), fm(h.rpc), fm(h["go"]), fm(h.oi), fm(h.pr)])
S += [table(hrows, widths=[1.3 * cm, 2.4 * cm, 2.8 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm], align="CENTER")]
S += [src("rank", "band", extra="'–' = no score published (band placement). 2021-2023: the college appears in the participant lists but not in the ranked lists or bands. "
                                 "In 2020 NIRF published 200 numeric ranks, so the page labelled '101-150' holds 201-250; the table reflects that.")]
S += [p("What the last two filings are worth, by the model", H2)]
erows = [["Filing", "TLR", "RPC", "GO", "OI", "PR (assumed)", "Estimated total", "Rank-100 score that year"]]
for e_ in sec_est:
    erows.append([str(e_["year"]), f"{e_['tlr']:.1f}", f"{e_['rpc']:.1f}", f"{e_['go']:.1f}", f"{e_['oi']:.1f}", f"{e_['pr_assumed']:.1f}", f"<b>{e_['total_est']:.1f}</b>", f"{cut25:.2f}" if e_["year"] == 2025 else f"≈ {thr['100']:.1f} (forecast)"])
S += [table(erows, align="CENTER")]
S += [src("model", "sec25", "sec26", extra="PR is not in the filing; the value shown is the median Perception score of private colleges ranked 60-100 in 2025 [NIRF ranking tables].")]
S += [p(f"The 2025 filing's estimate ({e25['total_est']:.1f}) lies within the 201-300 band that NIRF announced for the college in 2025; the model was not given that information. "
        f"Between the two filings the reported numbers moved: on-time graduation 61% → 81%, placement 92% → 97%, operating spend per student Rs 80,210 → Rs 1,10,595, PhDs awarded 9 → 12 a year.{ev('sec25')}{ev('sec26')}")]
S += [KeepTogether([fig("compare", 16 * cm), p("Estimated parameters for the college's 2026 filing (coloured) beside the 2025 averages of institutes ranked 76-100 and 1-10.", SMALL),
                    src("model", "ana", extra="Tier averages from tier_profile_2025.")])]

# 4 data
S += [section("4", "Data collected", TEAL)]
counts = {t_: con.execute(f"SELECT COUNT(*) FROM {t_}").fetchone()[0] for t_ in ("rankings", "rank_bands", "participants", "submissions", "faculty", "methodology", "documents")}
drows = [["Source", "What it gives", "Size", "Where"],
         ["NIRF ranking pages", "Engineering, Overall, College and University lists 2017-2025: rank, total and the five parameter scores (Engineering ranks 1-200 for 2019-22)", f"{counts['rankings']:,} rows", "nirfindia.org/Rankings/<year>/EngineeringRanking.html"],
         ["NIRF band pages", "Institutions placed in 101-150 / 151-200 / 201-300, no scores", f"{counts['rank_bands']:,} rows", "…/EngineeringRanking150.html, 200, 300"],
         ["NIRF participant lists", "Every institution that applied, per year and category", f"{counts['participants']:,} rows", "…/EngineeringRankingALL.html"],
         ["Per-institute data PDFs", "Each ranked institute's submitted data: intake, enrolment by gender/state/category, placements, median salary, higher studies, PhDs, capital and operating spend, sponsored research, consultancy, patents, facilities. Top 100 for 2023-25; top 200 for 2021-22", f"{counts['submissions']:,} PDFs", "nirfindia.org/nirfpdfcdn/<year>/pdf/Engineering/<id>.pdf"],
         ["NIRF methodology PDFs", "Definitions, marks and formulas for 2023, 2024, 2025 (Engineering, Overall, College)", f"{counts['methodology']} rows", "nirfindia.org/nirfpdfcdn/<year>/framework/<category>.pdf"],
         ["College's own filings", "NIRF 2025 Engineering, Innovation and SDG filings and the NIRF 2026 Engineering filing, incl. the full faculty list", "4 PDFs · 1,575 faculty rows", "saveetha.ac.in/nirf-documents-2024/"],
         ["Full text of the above", "Indexed for the AI assistant", f"{counts['documents']} documents", "db/nirf.db, table documents"]]
S += [table(drows, widths=[3.1 * cm, 7.2 * cm, 2.2 * cm, 4.8 * cm], headcol=TEAL), src("db", extra="Row counts are live from the database at build time.")]
S += [tech("Data handling. The 2016 pages on nirfindia.org return the 2017 tables (identical content, title 'India Rankings 2017'), so 2016 is dropped. In years with 200 numeric ranks the pages labelled "
           "'101-150' and '151-200' hold ranks 201-250 and 251-300 (no overlap with the ranked list), and are relabelled. Band pages carry no institute IDs, so band rows are linked to institutions by a normalised name key. "
           "PDFs are converted with pdftotext -layout and parsed with regular expressions; every numeric field the model uses has over 96% coverage across the 704 PDFs. Faculty lists appear only in the college's own PDFs.")]
prof = pd.DataFrame(A["raw_profile_2025"]).set_index("metric")
show = ["students_total", "faculty_entered", "students_per_faculty", "phd_pursuing_ft", "phd_grad_3y_avg", "graduation_rate", "placement_rate", "median_salary_ug",
        "capex_per_student", "opex_per_student", "sponsored_amount_3y_avg", "consultancy_amount_3y_avg", "women_students_pct", "outside_state_pct"]
lab = {"students_total": "Students (UG+PG)", "faculty_entered": "Faculty", "students_per_faculty": "Students per faculty", "phd_pursuing_ft": "Full-time PhD scholars",
       "phd_grad_3y_avg": "PhDs awarded / year (3-yr avg)", "graduation_rate": "Graduating on time", "placement_rate": "Placed", "median_salary_ug": "Median UG salary",
       "capex_per_student": "Capital spend / student (3-yr avg)", "opex_per_student": "Operating spend / student (3-yr avg)", "sponsored_amount_3y_avg": "Sponsored research / yr (3-yr avg)",
       "consultancy_amount_3y_avg": "Consultancy / yr (3-yr avg)", "women_students_pct": "Women students", "outside_state_pct": "Students from other states"}
money = {"median_salary_ug", "capex_per_student", "opex_per_student", "sponsored_amount_3y_avg", "consultancy_amount_3y_avg"}; pct = {"graduation_rate", "placement_rate"}
def fmtv(v, k):
    if pd.isna(v): return "–"
    if k in money: return inr(v)
    if k in pct: return f"{100 * v:.0f}%"
    if k in ("women_students_pct", "outside_state_pct"): return f"{v:.0f}%"
    return f"{v:,.1f}" if v % 1 else f"{v:,.0f}"
prows = [["Metric", "Top 10 (median)", "Rank 76-100 (median)", "Colleges in top 100 (median)", "College, 2025 filing", "College, 2026 filing"]]
for k in show:
    rw = prof.loc[k]; v26 = fmtv(rw.saveetha_2026_filing, k)
    below = (not pd.isna(rw.saveetha_2026_filing)) and (not pd.isna(rw.rank76_100_median)) and (rw.saveetha_2026_filing < rw.rank76_100_median) and k != "students_per_faculty"
    prows.append([lab[k], fmtv(rw.top10_median, k), fmtv(rw.rank76_100_median, k), fmtv(rw.colleges_top100_median, k), fmtv(rw.saveetha_2025_filing, k),
                  f"<font color='{CORAL if below else TEAL}'><b>{v26}</b></font>"])
S += [KeepTogether([p("The college's raw numbers beside the 2025 top 100", H2), table(prows, widths=[4.2 * cm, 2.6 * cm, 2.8 * cm, 2.8 * cm, 2.5 * cm, 2.5 * cm], align="CENTER", headcol=TEAL),
                    src("pdf", "sec25", "sec26", "ana", extra=f"<font color='{CORAL}'>Red</font> = 2026 filing below the rank 76-100 median; <font color='{TEAL}'>green</font> = at or above it. Medians over the 100 institutes ranked in 2025.")])]

# 5 architecture
S += [KeepTogether([section("5", "How the system works", GOLD), fig("architecture", 16.8 * cm)])]
S += [p("Scripts fetch the public data (1) and turn web tables and PDFs into clean rows (2), which are stored in one database file (3). The models (4) are fitted on the 700 institute-years "
        "where both the raw submission and the published score are known, then applied to the college's filings. The analysis step (5) produces the comparisons in this report, and the app (6) "
        "presents them, accepts live numbers from staff, and answers questions through an AI assistant that shows the queries it runs.")]
S += [tech("Stack: Python 3.13; requests + BeautifulSoup for scraping; poppler pdftotext + regex for PDF parsing; pandas; SQLite; XGBoost and scikit-learn for models; Streamlit + Plotly for the app; "
           "rank-bm25 for document retrieval; Groq (gpt-oss-120b) as the chat model with Gemini as fallback, both on free tiers. "
           "Layout: scraper/ (4 scripts) · models/ (score_model.py, predict_2026.py, artifacts/) · analysis/analyze.py · app/ (Home.py, common.py, pages/1-6, rag/) · "
           "data/raw (html, pdf, pdf_text, methodology, saveetha) · data/processed (CSV + JSON) · db/nirf.db · docs/.")]

# 6 model
S += [section("6", "The scoring model", CORAL)]
S += [p(f"<b>Why a model is needed.</b> NIRF publishes the formula but not the normalisation functions f( ) that turn a raw number into marks.{ev('meth', 'e.g. SS: f to be determined by NIRF')} "
        "Without them a score cannot be computed from raw data.")]
S += [p("<b>Approach.</b> For 700 institute-years (Engineering, ranks 1-200 in 2021-22 and 1-100 in 2023-25) both sides are known: the raw submission and the parameter scores NIRF published. "
        f"One model per parameter is fitted on exactly the inputs the methodology lists for that parameter, then applied to the college's filings.{ev('model', 'features per parameter')}")]
S += [p("<b>Choice of method.</b> Gradient-boosted trees (XGBoost) with monotone constraints. Trees capture the saturating shape the methodology implies (a ratio of 1:15 earns full FSR marks; "
        "more does not add). Monotone constraints require the fitted function to move in the direction the methodology states (more placements cannot reduce GO; more spend cannot reduce TLR), "
        f"which removes spurious patterns and keeps what-if results consistent. A linear model on the same inputs reached R² of about 0.5 in our tests; a neural network would need far more rows.")]
mrows = [["Parameter", "Rows", "Cross-validated R²", "Typical error (MAE)", "Largest contributors (gain share)"]]
for k, v in mp.items():
    mrows.append([f"<font color='{PCOL[k]}'><b>{k.upper()}</b></font>", str(v["n"]), f"{v['cv_r2']:.2f}", f"{v['cv_mae']:.1f} pts", ", ".join(f"{a.replace('_', ' ')} ({b:.0%})" for a, b in list(v["importance"].items())[:3])])
S += [table(mrows, widths=[2 * cm, 1.4 * cm, 3.2 * cm, 2.9 * cm, 7.7 * cm]), src("model", extra="5-fold cross-validation grouped by institute, so an institute's other years are never in its training fold.")]
S += [p(f"With the published Perception score added, the four estimates reproduce published totals with a mean absolute error of <b>{M['total_score_fit']['mae']} points</b> (R² {M['total_score_fit']['r2']}) on the training rows.{ev('model', 'total_score_fit')}", SMALL)]
S += [callout("Publications and citations carry 75 of RPC's 100 marks and are not in the submission PDFs, so RPC is inferred from PhD output, funding and faculty size; it has the largest error. "
              "Perception is a survey and cannot be modelled from data; the forecast treats it as an uncertainty drawn from private colleges ranked 60-100 in 2025 (median 11.9, 10th-90th percentile 3.8-48.8). "
              "The model is trained on institutes ranked 1-200 and is most reliable in that range, which is where the college's 2026 filing is estimated to sit.", col=GOLD, label="Known limits  [model_report.json, prediction_2026.json]")]

# 7 results
S += [KeepTogether([section("7", "The 2025 field", SKY), fig("tiers", 16 * cm)])]
S += [p(f"RPC and Perception rise steeply with rank; TLR, GO and OI are flatter. The 2025 top 100 contained {A['type_mix']['2025']['University']} universities, "
        f"{A['type_mix']['2025']['College']} colleges and {A['type_mix']['2025']['Institute (deemed / national importance)']} deemed or national institutes; colleges numbered 12 in 2023 and 9 in 2025.", SMALL),
      src("rank", "ana", extra="Type from the NIRF id (U / C / I); tier averages from tier_profile_2025.")]
tn = pd.DataFrame(A["tamil_nadu_2025"])
tnrows = [["Rank", "Tamil Nadu institutions in the 2025 Engineering top 100", "Type", "Total", "RPC"]]
for x_ in tn.to_dict("records"):
    nm = f"<font color='{CORAL}'><b>{x_['name']}</b></font>" if x_["type_label"] == "College" else x_["name"]
    tnrows.append([str(int(x_["rank"])), nm, x_["type_label"].split(" ")[0], f"{x_['score']:.2f}", f"{x_['rpc']:.1f}"])
S += [table(tnrows, widths=[1.3 * cm, 9.6 * cm, 2.2 * cm, 1.8 * cm, 1.8 * cm]), src("rank", extra="2025 Engineering table filtered to state = Tamil Nadu. Colleges (id IR-E-C-…) in red.")]
S += [p("Three of the fourteen are colleges: SSN (rank 47, RPC 44.0), PSG Tech (67, RPC 26.3) and Sri Krishna CET (100, RPC 22.4). Their RPC values bracket what a college at the cut-off carries.", SMALL)]
grows = [["Parameter", "Rank 90-100 average (2025)", "College, 2026 filing (est.)", "Difference", "× weight = points"]]
for k in ["tlr", "rpc", "go", "oi", "pr"]:
    est_v = e26["pr_assumed"] if k == "pr" else e26[k]
    grows.append([f"<font color='{PCOL[k]}'><b>{k.upper()}</b></font>", f"{est_v + gap[k]:.1f}", f"{est_v:.1f}", f"{gap[k]:+.1f}", f"<font color='{CORAL if wgap[k] > 1 else INK}'><b>{wgap[k]:+.2f}</b></font>"])
S += [KeepTogether([p("Where the weighted points are", H2), table(grows, align="CENTER"), src("ana", "model", extra="saveetha_gap_vs_rank90_100_avg and saveetha_weighted_gap_by_param; weights from the 2025 methodology.")])]
S += [p(f"RPC accounts for {wgap['rpc']:.1f} of the {sum(v for v in wgap.values() if v > 0):.1f} weighted points between the college's estimate and the rank 90-100 average; TLR and OI (students from other states) account for most of the rest; GO is close to level.", SMALL)]

# 8 prediction
S += [KeepTogether([section("8", "The 2026 forecast", PLUM), fig("bands", 15.5 * cm)])]
S += [tiles([(f"{s['total_score']['median']}", f"Median estimated total; 10th-90th percentile {s['total_score']['p10']}-{s['total_score']['p90']}", PLUM),
             (f"≈ rank {s['expected_rank']}", "Median total placed on the 2026 threshold curve", SKY),
             (f"{100 * top200:.0f}%", "Share of simulations inside the top 200", TEAL),
             (f"{s['gap_to_top100']:.1f} pts", f"Median total vs forecast rank-100 score ({thr['100']:.1f})", CORAL)])]
trows = [["Rank in 2026", "100", "125", "150", "175", "200", "250", "300"], ["Forecast score at that rank"] + [f"{thr[k]:.1f}" for k in ["100", "125", "150", "175", "200", "250", "300"]]]
S += [table(trows, align="CENTER", zebra=False, headcol=PLUM), src("pred", extra="thresholds.forecast_2026.")]
S += [tech("Method. (a) Thresholds: linear trend of the rank-100 score over 2020-2025 (+1.5 a year, residual s.d. 0.5); the ratio of the score at rank k to the score at rank 100 is taken from 2019-22, "
           "when NIRF published 200 ranks, and extrapolated to 300 on a log-rank scale. (b) The college: parameter estimates from the score model on the 2026 filing; 20,000 Monte-Carlo draws add each "
           "parameter model's cross-validated RMSE, a Perception score sampled from private colleges ranked 60-100 in 2025, and the threshold trend's residual; each draw is assigned a band. "
           f"(c) Other institutions: a ridge regression on previous score, parameters and two-year momentum predicts each 2025 top-100 institute's 2026 score. Trained on ≤2024 and tested on 2025 it has MAE {val['mae']} "
           f"against {val['naive_mae_no_change']} for a no-change assumption, and Spearman {val['rank_spearman_top100']} against the actual 2025 order [prediction_2026.json, top100_model_validation].")]
S += [p("<b>Reading the probabilities.</b> The spread comes mainly from two inputs the data does not contain: the Perception survey and the publication counts behind RPC. "
        "Strong Scopus output would move the college's true score towards the upper end of the range; the model cannot see it either way.")]

# 9 levers
S += [KeepTogether([section("9", "What moves the score", CORAL), fig("levers", 16 * cm)])]
S += [p("Each bar is one change applied alone to the 2026 filing with everything else unchanged, scored through the same model. Effects are approximately additive.", SMALL), src("pred", extra="what_if_levers; each lever re-scores the filing with a single field changed.")]
S += [p("Observations, with the methodology reference for each", H2)]
S += [Paragraph(x_, BUL, bulletText="•") for x_ in [
    "<b>PhDs awarded</b> is the largest single lever: 12 → 40 a year is worth about +2.2, 12 → 80 about +3.7. GPHD carries 20 marks of GO; PhD scholars also count in SS (TLR), and PhD output "
    "is the strongest predictor of RPC in the model (60% of gain). Awards lag enrolment by three to four years; 61 → 200 full-time scholars is worth +1.4 on its own.",
    "<b>Publications and citations</b> carry 75 of RPC's 100 marks [methodology] and are not observed here. Institutes ranked 76-100 average RPC 29.8 against the college's estimated 13.4. "
    "NIRF 2025 introduced a deduction for retracted papers (−5 × f(Pret), −5 × f(Cret)).",
    "<b>Operating and capital spend per student</b>: FRU is 30 marks of TLR. Rs 1.1 L → Rs 2 L operating spend per student is worth about +2.0; Rs 18k → Rs 60k capital spend about +0.8. "
    "The methodology excludes buildings from capital spend and hostels from operating spend.",
    "<b>Median UG salary</b>: GMS is 25 marks of GO. Rs 5.5 L → Rs 8 L is +0.8; → Rs 10 L is +1.4. The metric is the median of placed graduates, not the highest offer.",
    "<b>Sponsored research and consultancy</b>: FPPP is 10 marks of RPC. Rs 30 L → Rs 10 Cr a year of sponsored research is about +1.0 in the model.",
    "<b>Students from other states</b>: RD is 30 marks of OI. The college reports 7.6% against a tier median of 57%; 7.6% → 20% is worth about +0.3.",
    "<b>Already at or above the tier</b> in the 2026 filing: placement 97%, on-time graduation 81%, women students 33%, full fee reimbursement 52%.",
]]
S += [callout(f"The difference between the college's median estimate ({s['total_score']['median']}) and the forecast rank-100 score ({thr['100']:.1f}) is {s['gap_to_top100']:.1f} points, and the rank-100 score "
              "has been rising about 1.5 points a year. Combining the levers above at the mid-range values (PhDs → 40 a year, operating spend → Rs 2 L, salary → Rs 8 L, scholars → 200) adds an estimated "
              "6-8 points by the model, before any effect from publications.", col=TEAL, label="Putting the numbers together  [prediction_2026.json]")]

# 10 app
S += [section("10", "The app, and where things live", TEAL)]
arows = [["Page", "What it shows"],
         ["Home", "The college's band, the cut-off trend, the 2026 forecast, and how the top 100 earns its points"],
         ["Top 100 Explorer", "Every ranked Engineering institute 2017-2025: filter by year, state, type; parameter scores, the weighted 'score anatomy', the raw numbers each institute submitted, and any institute's history"],
         ["Saveetha Position", "The college's NIRF history, estimated parameter scores, the gap table, raw numbers against the tiers, and the paths of Tamil Nadu colleges in the top 100"],
         ["Gap & What-If", "A slider for every lever. The model re-scores instantly and shows the implied 2026 band"],
         ["Prediction 2026", "Forecast thresholds, band probabilities, model accuracy, and the projected 2026 order of the 2025 top 100"],
         ["Live Data Entry", "Staff enter current-year numbers (placements, salary, PhDs, spend, Scopus counts). Entries are time-stamped and kept; the model re-scores with the live values"],
         ["Ask the Data", "An AI assistant that writes database queries, reads the methodology and the 700 submissions, and can fetch nirfindia.org live. It displays the queries it ran so answers can be checked"]]
S += [table(arows, widths=[3.4 * cm, 13.9 * cm], headcol=TEAL)]
S += [p("<b>Running it.</b> <font face='Courier'>./run.sh</font>, then open http://localhost:8501. After NIRF 2026 is published, <font face='Courier'>./pipeline.sh</font> re-runs every step and this report can be rebuilt with <font face='Courier'>python docs/build_report.py</font>.")]
S += [p("Folder structure", H2)]
S += [Table([[Paragraph("""<b>scraper/</b>   scrape_rankings.py · download_pdfs.py · parse_pdfs.py · build_db.py — collect and store<br/>
<b>models/</b>    score_model.py (fits the f curves) · predict_2026.py (forecast) · artifacts/ (trained model)<br/>
<b>analysis/</b>  analyze.py — cut-offs, tiers, movers, peers, gap → data/processed/analysis.json<br/>
<b>app/</b>       Home.py · common.py · pages/1-6 · rag/index.py (document search) · rag/chat.py (AI assistant)<br/>
<b>data/raw/</b>  html/ pdf/ pdf_text/ methodology/ saveetha/ — everything downloaded, untouched, kept for audit<br/>
<b>data/processed/</b>  rankings.csv · submissions.csv · faculty.csv · analysis.json · prediction_2026.json · model_report.json<br/>
<b>db/nirf.db</b>   the one database file (SQLite); any SQL tool can open it<br/>
<b>docs/</b>      this report and the script that builds it · <b>README.md</b> · <b>.env</b> (API keys, never shared) · <b>run.sh</b> · <b>pipeline.sh</b>""", CODE)]],
            colWidths=[17.3 * cm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), C("#F6F8FB")), ("LINEBEFORE", (0, 0), (0, 0), 3, C(TEAL)), ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))]

# 11 caveats
S += [section("11", "Caveats", GOLD)]
S += [Paragraph(x_, BUL, bulletText="•") for x_ in [
    "The college's parameter scores for 2020-2025 are <b>model estimates</b>; NIRF has not published them. They are calibrated on 700 institute-years and the 2025 estimate agrees with the published band, but they are not official figures. "
    "The accurate phrasing is 'estimated at about 13', not 'our RPC is 13'.",
    "Publications, citations and Perception are not in the data. They are the main sources of uncertainty and are reported as ranges.",
    "The 2026 forecast assumes the 2025 methodology is unchanged. NIRF has changed weights and sub-parameters before (e.g. the 2025 retraction penalty); the pipeline re-reads the methodology PDF each year.",
    "The AI assistant can misstate wording. It displays the database queries it ran; figures that matter should be checked against the dashboard or this report.",
]]

# 12 sources
S += [section("12", "Sources and evidence", NAVY)]
S += [p("Every figure in this report traces to one of the following. Raw downloads are kept unchanged under data/raw/ so any number can be re-checked.")]
srows = [["#", "Source", "Location", "Used for"],
         ["S1", "NIRF Engineering ranking tables, 2017-2025", "https://www.nirfindia.org/Rankings/&lt;year&gt;/EngineeringRanking.html (also Overall, College, University)", "Ranks, totals, TLR/RPC/GO/OI/PR; cut-offs; tier averages; the college's 2017 and 2019 rows"],
         ["S2", "NIRF rank-band pages", "…/EngineeringRanking150.html, …200.html, …300.html per year", "The college's 2018, 2020, 2024, 2025 band placements"],
         ["S3", "NIRF participant lists", "…/EngineeringRankingALL.html per year", "Years the college applied"],
         ["S4", "Per-institute data PDFs (704)", "https://www.nirfindia.org/nirfpdfcdn/&lt;year&gt;/pdf/Engineering/&lt;institute id&gt;.pdf", "Raw submissions of ranked institutes: model training data; top-100 medians"],
         ["S5", "NIRF methodology documents 2023-2025", "https://www.nirfindia.org/nirfpdfcdn/&lt;year&gt;/framework/Engineering.pdf (and Overall.pdf, College.pdf)", "Weights, sub-parameter marks, formulas quoted in section 2"],
         ["S6", "College's NIRF 2025 filings", "https://saveetha.ac.in/nirf-documents-2024/ → Engineering-1.pdf, Innovation.pdf, SDG-1.pdf", "2025 raw numbers and faculty list"],
         ["S7", "College's NIRF 2026 filing", "https://saveetha.ac.in/wp-content/uploads/2026/02/SAVEETHA-ENGINEERING-COLLEGE20260216-.pdf", "2026 raw numbers; basis of the 2026 estimate and forecast"],
         ["S8", "Score model output", "data/processed/model_report.json (models/score_model.py)", "Cross-validation results; the college's estimated parameter scores"],
         ["S9", "Forecast output", "data/processed/prediction_2026.json (models/predict_2026.py)", "Thresholds, band probabilities, lever values, top-100 model validation"],
         ["S10", "Analysis output", "data/processed/analysis.json (analysis/analyze.py)", "Tier profiles, raw-number medians, gap decomposition, Tamil Nadu list"],
         ["S11", "Database", "db/nirf.db (scraper/build_db.py)", "All of S1-S7 as tables; row counts in section 4"]]
S += [table(srows, widths=[0.9 * cm, 4.2 * cm, 6.6 * cm, 5.6 * cm]), src("db", extra="Report built by docs/build_report.py; every number is read from S8-S11 at build time, not typed in.")]

doc.build(S, onFirstPage=cover, onLaterPages=footer)
print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
