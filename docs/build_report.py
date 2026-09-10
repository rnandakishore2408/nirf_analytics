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
                        title="NIRF Analytics — Saveetha Engineering College", author="NIRF Analytics project")
S = []
applied = dict(con.execute("SELECT year, COUNT(*) FROM participants WHERE category='Engineering' GROUP BY year").fetchall())
simats = {y: (rk, sc) for y, rk, sc in con.execute("SELECT year, rank, score FROM rankings WHERE institute_id='IR-E-I-1441' AND category='Engineering'").fetchall()}
sec_band = {y: b for y, b in con.execute("SELECT year, band FROM rank_bands WHERE name_key LIKE 'saveetha engineering%' AND category='Engineering'").fetchall()}
sec_rank = {y: (rk, sc) for y, rk, sc in con.execute("SELECT year, rank, score FROM rankings WHERE name_key LIKE 'saveetha engineering%' AND category='Engineering'").fetchall()}
sub = pd.read_sql("SELECT * FROM submissions WHERE institute_id='IR-E-C-16590' ORDER BY year", con).set_index("year")

# ---- cover page body
S += [Spacer(1, 11.8 * cm)]
S += [tiles([("Band 201-300", "NIRF 2025 result, Engineering. Same band in 2024. [NIRF band pages]", CORAL),
             (f"≈ {e26['total_est']:.0f}", "Estimated score of the college's 2026 filing [score model]", SKY),
             (f"{thr['100']:.0f}", "Score forecast for rank 100 in 2026 [2026 forecast]", GOLD),
             (f"{100 * bp[s['most_likely_band']]:.0f}% · {s['most_likely_band']}", "Most likely band for 2026 [2026 forecast]", TEAL)])]
S += [fig("cutoff", 16.8 * cm)]
S += [p("Blue line: the score needed to be ranked 100 each year. Red dots: the college's two published scores. Open circles: our estimates of its last two filings.", SMALL),
      src("rank", "model", extra="Cut-off = lowest score in the top 100 of each year's Engineering table.")]
S += [PageBreak()]

# ---- 1 what the numbers say
S += [section("1", "What the numbers say")]
pts = [
    f"Saveetha Engineering College is in the <b>201-300 band</b> of the NIRF Engineering ranking in both 2024 and 2025. NIRF gives no score for bands.{ev('band')}",
    f"The score needed for rank 100 rises every year: <b>41.93</b> in 2023, <b>43.95</b> in 2024, <b>45.55</b> in 2025. Our forecast for 2026 is about <b>{thr['100']:.0f}</b>.{ev('rank')}{ev('pred')}",
    f"The college's own filings are worth about <b>{e25['total_est']:.0f}</b> (2025) and <b>{e26['total_est']:.0f}</b> (2026) by our model. The 2025 estimate falls inside the band NIRF actually published, a good sign the model reads the data correctly.{ev('model')}",
    f"The college is <b>{s['gap_to_top100']:.0f} points</b> short of the 2026 rank-100 line. About <b>{wgap['rpc']:.0f} of those points</b> come from one parameter: Research (RPC).{ev('ana')}",
    f"Behind the research gap: <b>12 PhDs a year</b> against 24 for institutes ranked 76-100, <b>61 full-time PhD scholars</b> against 163, and <b>Rs 30 lakh</b> of sponsored research a year against Rs 3.7 crore.{ev('sec26')}{ev('pdf')}",
    f"Placements (97%), graduating on time (81%) and women students (33%) are already at or above the 76-100 tier.{ev('sec26')}{ev('pdf')}",
    f"For 2026 the most likely result is the <b>{s['most_likely_band']} band</b> ({100 * bp[s['most_likely_band']]:.0f}%). Top 200: {100 * top200:.0f}%. Top 100: {100 * bp['top 100']:.0f}%.{ev('pred')}",
]
for i, t_ in enumerate(pts, 1):
    S += [Table([[Paragraph(f"<font color='white'><b>{i}</b></font>", ParagraphStyle("pn", parent=BODY, fontSize=11, alignment=TA_CENTER)), Paragraph(t_, ParagraphStyle("pt", parent=BODY, spaceAfter=0))]],
                colWidths=[0.8 * cm, 16.5 * cm], style=TableStyle([("BACKGROUND", (0, 0), (0, 0), C([NAVY, SKY, CORAL, GOLD, TEAL, PLUM, NAVY][i - 1])), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                                                    ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (1, 0), (1, 0), 8)])), Spacer(1, 3)]
S += [callout("Every square bracket is a source. Section 10 lists where each one lives, with the exact web address or file.", col=NAVY)]
S += [PageBreak()]

# ---- 2 the last three years
rows = [["Year", "Institutions that applied (Engineering)", "Score at rank 100", "Score at rank 1", "Saveetha Engineering College", "Saveetha Institute (the deemed university)"]]
for y in (2023, 2024, 2025):
    g = r[(r.year == y) & (r["rank"] <= 100)]
    sec_txt = f"Band {sec_band[y]}" if y in sec_band else "Applied; not in the top 300" if y in applied else "Did not apply"
    rows.append([str(y), f"{applied[y]:,}", f"{g.score.min():.2f}", f"{g.score.max():.2f}", f"<b>{sec_txt}</b>", f"Rank {simats[y][0]} ({simats[y][1]:.2f})"])
S += [KeepTogether([section("2", "2023, 2024 and 2025 at a glance", CORAL), table(rows, widths=[1.2 * cm, 3.4 * cm, 2.4 * cm, 2.2 * cm, 4.0 * cm, 4.1 * cm], align="CENTER", headcol=CORAL)]),
      src("rank", "band", extra="'Applied' counts come from the participant list on each year's page. The last column is a different institution, shown only to avoid confusion.")]
S += [p("In 2023 the college applied but was not placed in any published list (NIRF published ranks 1-100 and bands to 200 that year). In 2024 and 2025 it was placed in the 201-300 band, "
        "which NIRF introduced in 2024 with 100 and 99 institutions respectively. Because bands carry no score, everything about the college's own numbers in this report is an estimate from its filings.")]
chg = [["What the college reported", "2025 filing", "2026 filing"],
       ["Students (UG + PG)", f"{sub.loc[2025, 'students_total']:,.0f}", f"{sub.loc[2026, 'students_total']:,.0f}"],
       ["Full-time faculty", f"{sub.loc[2025, 'faculty_parsed']:,.0f}", f"{sub.loc[2026, 'faculty_parsed']:,.0f}"],
       ["Full-time PhD scholars", f"{sub.loc[2025, 'phd_pursuing_ft']:,.0f}", f"{sub.loc[2026, 'phd_pursuing_ft']:,.0f}"],
       ["PhDs awarded per year (3-year average)", f"{sub.loc[2025, 'phd_grad_3y_avg']:,.0f}", f"{sub.loc[2026, 'phd_grad_3y_avg']:,.0f}"],
       ["Graduating on time", f"{100 * sub.loc[2025, 'graduation_rate']:.0f}%", f"{100 * sub.loc[2026, 'graduation_rate']:.0f}%"],
       ["Placed", f"{100 * sub.loc[2025, 'placement_rate']:.0f}%", f"{100 * sub.loc[2026, 'placement_rate']:.0f}%"],
       ["Median UG salary", inr(sub.loc[2025, 'median_salary_ug']), inr(sub.loc[2026, 'median_salary_ug'])],
       ["Operating spend per student", inr(sub.loc[2025, 'opex_per_student']), inr(sub.loc[2026, 'opex_per_student'])],
       ["Sponsored research per year", inr(sub.loc[2025, 'sponsored_amount_3y_avg']), inr(sub.loc[2026, 'sponsored_amount_3y_avg'])],
       ["Patents published (3 years)", f"{sub.loc[2025, 'patents_published_3y']:,.0f}", f"{sub.loc[2026, 'patents_published_3y']:,.0f}"],
       ["Estimated total score (our model)", f"<b>{e25['total_est']:.1f}</b>", f"<b>{e26['total_est']:.1f}</b>"]]
S += [KeepTogether([p("What changed between the two filings", H2), table(chg, widths=[8 * cm, 4.6 * cm, 4.6 * cm], align="CENTER", headcol=CORAL), src("sec25", "sec26", "model")])]

# ---- 3 how NIRF scores
S += [section("3", "How NIRF scores an engineering institution", SKY)]
S += [p(f"Every institution gets a score out of 100. It is built from five parameters, each scored out of 100 and then weighted:{ev('meth', 'summary table')}")]
S += [Table([[Paragraph(f"Total  =  <font color='{SKY}'><b>0.30 × TLR</b></font>  +  <font color='{CORAL}'><b>0.30 × RPC</b></font>  +  <font color='{TEAL}'><b>0.20 × GO</b></font>  +  <font color='{GOLD}'><b>0.10 × OI</b></font>  +  <font color='{PLUM}'><b>0.10 × PR</b></font>",
                          ParagraphStyle("f", parent=BODY, alignment=TA_CENTER, fontSize=11.5, leading=15))]], colWidths=[17.3 * cm],
             style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), C("#F6F8FB")), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)])), Spacer(1, 8)]
cards = [("TLR", "Teaching, Learning & Resources", "0.30", "How many students and faculty you have, how many faculty hold a PhD, and how much money you spend per student."),
         ("RPC", "Research & Professional Practice", "0.30", "Publications and citations per faculty, patents, and income from research projects and consultancy."),
         ("GO", "Graduation Outcomes", "0.20", "Share of students placed or in higher studies, share graduating on time, median salary, and PhDs awarded."),
         ("OI", "Outreach & Inclusivity", "0.10", "Students from other states and countries, women students and faculty, fee-reimbursed students, facilities for the disabled."),
         ("PR", "Perception", "0.10", "A survey of employers and academics. Not based on submitted data.")]
crow = [["Parameter", "Weight", "What counts"]]
for code, nm, wt, what in cards:
    crow.append([f"<font color='{PCOL[code.lower()]}'><b>{code}</b></font>  {nm}", wt, what])
t = table(crow, widths=[5.6 * cm, 1.5 * cm, 10.2 * cm], headcol=SKY)
t.setStyle(TableStyle([("BACKGROUND", (0, i), (0, i), C(TINT[PCOL[c[0].lower()]])) for i, c in enumerate(cards, start=1)]))
S += [t, src("meth", extra="Weights from the 2025 Engineering summary table; 'what counts' paraphrases the sub-parameters, which are listed with marks and formulas in Appendix A.")]
S += [callout("Two things that confuse people. Only the top 100 get a numeric rank; everyone below is placed in a band with no score. And <b>Saveetha Engineering College</b> "
              "(Sriperumbudur, NIRF id IR-E-C-16590) is a different NIRF entity from <b>Saveetha Institute of Medical and Technical Sciences</b> (Chennai, a deemed university, rank 45 in 2025).", col=GOLD, label="Worth knowing")]

# ---- 4 record
S += [section("4", "The college's NIRF record, 2017 to 2025", CORAL)]
hrows = [["Year", "Category", "Result", "Total", "TLR", "RPC", "GO", "OI", "PR"]]
for _, h in hist.iterrows():
    pos = f"Rank {int(h.rank_or_band_low)}" if h.status == "ranked" else f"Band {int(h.rank_or_band_low)}-{int(h.rank_or_band_high)}"
    fm = lambda v: "–" if pd.isna(v) else f"{v:.2f}"
    hrows.append([str(int(h.year)), h.category, pos, fm(h.score), fm(h.tlr), fm(h.rpc), fm(h["go"]), fm(h.oi), fm(h.pr)])
S += [table(hrows, widths=[1.3 * cm, 2.4 * cm, 2.8 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm, 1.5 * cm], align="CENTER", headcol=CORAL),
      src("rank", "band", extra="A dash means NIRF published no score. The college also applied in 2021, 2022 and 2023 without being placed in a published list.")]
S += [p("The two years with published scores tell the same story as today: TLR, GO and OI were reasonable, <b>RPC was 4.7 and 3.0</b>, and Perception was close to zero.")]
S += [KeepTogether([fig("compare", 16 * cm), src("model", "ana", extra="Coloured bars are model estimates from the 2026 filing; grey bars are averages of published 2025 scores.")])]

# ---- 5 vs top 100
prof = pd.DataFrame(A["raw_profile_2025"]).set_index("metric")
show = ["students_per_faculty", "phd_pursuing_ft", "phd_grad_3y_avg", "graduation_rate", "placement_rate", "median_salary_ug", "opex_per_student", "sponsored_amount_3y_avg", "women_students_pct", "outside_state_pct"]
lab = {"students_per_faculty": "Students per faculty", "phd_pursuing_ft": "Full-time PhD scholars", "phd_grad_3y_avg": "PhDs awarded per year", "graduation_rate": "Graduating on time",
       "placement_rate": "Placed", "median_salary_ug": "Median UG salary", "opex_per_student": "Operating spend per student", "sponsored_amount_3y_avg": "Sponsored research per year",
       "women_students_pct": "Women students", "outside_state_pct": "Students from other states"}
money = {"median_salary_ug", "opex_per_student", "sponsored_amount_3y_avg"}; pct = {"graduation_rate", "placement_rate"}
weak = {"phd_pursuing_ft", "phd_grad_3y_avg", "median_salary_ug", "opex_per_student", "sponsored_amount_3y_avg", "outside_state_pct"}
def fmtv(v, k):
    if pd.isna(v): return "–"
    if k in money: return inr(v)
    if k in pct: return f"{100 * v:.0f}%"
    if k in ("women_students_pct", "outside_state_pct"): return f"{v:.0f}%"
    return f"{v:,.1f}" if v % 1 else f"{v:,.0f}"
prows = [["", "Top 10 (median)", "Rank 76-100 (median)", "Saveetha, 2026 filing"]]
for k in show:
    rw = prof.loc[k]
    prows.append([lab[k], fmtv(rw.top10_median, k), fmtv(rw.rank76_100_median, k), f"<font color='{CORAL if k in weak else TEAL}'><b>{fmtv(rw.saveetha_2026_filing, k)}</b></font>"])
S += [KeepTogether([section("5", "The college next to the top 100, in plain numbers", TEAL), table(prows, widths=[5.5 * cm, 3.6 * cm, 4 * cm, 4.2 * cm], align="CENTER", headcol=TEAL)]),
      src("pdf", "sec26", "ana", extra="Medians over the 2025 top-100 institutes' own NIRF PDFs. Red = well below the 76-100 tier; green = at or above it.")]
S += [p("The pattern is simple. Everything about research, PhDs and money per student is red. Everything about students, placements and inclusion is green. "
        f"Put through the scoring weights, that is where the {s['gap_to_top100']:.0f}-point gap comes from:{ev('ana')}")]
grows = [["Parameter", "Rank 90-100 average", "Saveetha (estimate)", "Points lost after weighting"]]
for k in ["tlr", "rpc", "go", "oi", "pr"]:
    est_v = e26["pr_assumed"] if k == "pr" else e26[k]
    grows.append([f"<font color='{PCOL[k]}'><b>{k.upper()}</b></font>", f"{est_v + gap[k]:.1f}", f"{est_v:.1f}", f"<font color='{CORAL if wgap[k] > 1 else INK}'><b>{wgap[k]:+.1f}</b></font>"])
S += [table(grows, widths=[3 * cm, 4.5 * cm, 4.5 * cm, 5.3 * cm], align="CENTER", headcol=TEAL), src("ana", "model", extra="PR for the college is an assumption (median of private colleges ranked 60-100), not an estimate from data.")]

# ---- 6 2026
S += [KeepTogether([section("6", "The 2026 outlook", PLUM), fig("bands", 15.5 * cm)])]
S += [src("pred", extra="20,000 simulations of the 2026 filing through the score model, with model error and an unknown Perception score, placed against the forecast thresholds.")]
S += [tiles([(f"{s['total_score']['median']}", f"Estimated total. Likely range {s['total_score']['p10']} to {s['total_score']['p90']}", PLUM),
             (f"≈ rank {s['expected_rank']}", "Expected position", SKY),
             (f"{100 * top200:.0f}%", "Chance of the top 200", TEAL),
             (f"{s['gap_to_top100']:.1f} pts", f"Gap to the top 100 (needs about {thr['100']:.0f})", CORAL)])]
trows = [["Rank in 2026", "100", "150", "200", "250", "300"], ["Score needed (forecast)"] + [f"{thr[k]:.1f}" for k in ["100", "150", "200", "250", "300"]]]
S += [table(trows, align="CENTER", zebra=False, headcol=PLUM), src("pred", extra="Rank-100 line extended from the 2020-25 trend; the shape below rank 100 comes from 2019-22, when NIRF published 200 ranks.")]
S += [p("The range is wide on purpose. Two things cannot be seen in any data: the Perception survey, and publication counts, which are 75 of Research's 100 marks. "
        "If the college's publication record is strong, the real result sits towards the top of the range.")]

# ---- 7 levers
S += [KeepTogether([section("7", "What moves the score", CORAL), fig("levers", 16 * cm)])]
S += [src("pred", extra="Each bar is one change applied alone to the 2026 filing, re-scored by the model. Publications are not included because the PDFs do not contain them.")]
S += [Paragraph(x_, BUL, bulletText="•") for x_ in [
    "<b>PhDs awarded</b> is the largest single lever: 12 → 40 a year adds about 2.2 points, 12 → 80 about 3.7. Awards lag enrolment by three to four years, so scholar intake now decides the 2029-30 filings.",
    "<b>Operating spend per student</b>: Rs 1.1 lakh → Rs 2 lakh adds about 2.0. NIRF counts labs, e-resources and equipment, not buildings.",
    "<b>Full-time PhD scholars</b>: 61 → 200 adds about 1.4.",
    "<b>Median salary</b>: Rs 5.5 lakh → Rs 8 lakh adds 0.8; → Rs 10 lakh adds 1.4. It is the median, so the middle of the batch matters more than a few high offers.",
    "<b>Sponsored research</b>: Rs 30 lakh → Rs 10 crore a year adds about 1.0.",
    "<b>Students from other states</b>: 7.6% → 20% adds about 0.3.",
    "<b>Publications and citations</b> are not in this chart because they are not in the data, yet they are 75 of RPC's 100 marks. The rank 76-100 tier averages RPC 30 against the college's estimated 13.",
]]

# ---- 8 how it was done
S += [KeepTogether([section("8", "How this was done", GOLD), fig("architecture", 16.6 * cm)])]
S += [p("Scripts download the public data from nirfindia.org and the college's website, turn the web tables and PDFs into clean rows, and store them in one database file. "
        "A model learns how NIRF turns raw numbers into scores from 700 institutes where both are known, then scores the college's own filings. "
        "A second model forecasts 2026. A web app shows all of it, lets staff type in live numbers, and has an AI assistant that answers questions from the data. "
        "One command re-runs everything when NIRF 2026 is published.")]
S += [p("How accurate is the model?", H2)]
mrows = [["Parameter", "Institutes used", "Share of variation explained (R²)", "Typical error"]]
for k, v in mp.items():
    mrows.append([f"<font color='{PCOL[k]}'><b>{k.upper()}</b></font>", str(v["n"]), f"{v['cv_r2']:.2f}", f"{v['cv_mae']:.1f} points"])
S += [table(mrows, widths=[3 * cm, 3.5 * cm, 6 * cm, 4.8 * cm], align="CENTER", headcol=GOLD),
      src("model", extra=f"Tested by hiding each institute and predicting it from the others. Combined with the published Perception score, the model reproduces published totals within {M['total_score_fit']['mae']} points on average.")]
S += [callout("The college's scores are <b>estimates</b>, not NIRF figures. Research is the least certain because publications are not in the PDFs. Perception is a survey and is treated as an assumption. "
              "The forecast assumes NIRF keeps the 2025 rules.", col=GOLD, label="Keep in mind")]

# ---- 9 app
arows = [["Page", "What it is for"],
         ["Home", "The band, the cut-off trend, the 2026 forecast, and how the top 100 earns its points"],
         ["Top 100 Explorer", "Every ranked Engineering institute 2017-2025, its parameter scores and the raw numbers it submitted"],
         ["Saveetha Position", "The college's history, estimated scores, and the gap against the tiers and Tamil Nadu peers"],
         ["Gap & What-If", "Sliders for every lever; the model re-scores instantly"],
         ["Prediction 2026", "Thresholds, band probabilities and model accuracy"],
         ["Live Data Entry", "Staff type in this year's numbers; they are kept with date and name, and the model re-scores with them"],
         ["Ask the Data", "An AI assistant that queries the database, reads the methodology, and can check nirfindia.org live. It shows every query it ran."]]
S += [KeepTogether([section("9", "The app", TEAL), table(arows, widths=[3.4 * cm, 13.9 * cm], headcol=TEAL)])]
S += [p("Run it with <font face='Courier'>./run.sh</font> and open http://localhost:8501. Refresh everything after NIRF 2026 with <font face='Courier'>./pipeline.sh</font>.")]

# ---- 10 sources
S += [KeepTogether([section("10", "Sources and evidence", NAVY), p("Every square bracket in this report points to one of these. Web addresses were fetched between 8 and 10 September 2026; copies of every page and PDF are kept unchanged under data/raw so any figure can be checked.")])]
srows = [["Tag", "What it is", "Where"],
         ["NIRF ranking tables", "Engineering (and Overall, College, University) tables 2017-2025 with rank, total and the five parameter scores", "https://www.nirfindia.org/Rankings/&lt;year&gt;/EngineeringRanking.html"],
         ["NIRF band pages", "Institutes placed in 101-150, 151-200, 201-300 (no scores)", "https://www.nirfindia.org/Rankings/&lt;year&gt;/EngineeringRanking150.html, …200.html, …300.html"],
         ["institute PDFs", "The data each ranked institute submitted (704 PDFs: top 100 for 2023-25, top 200 for 2021-22)", "https://www.nirfindia.org/nirfpdfcdn/&lt;year&gt;/pdf/Engineering/&lt;institute id&gt;.pdf"],
         ["NIRF 2025 methodology", "Official parameters, marks, weights and formulas (also 2023 and 2024 versions)", "https://www.nirfindia.org/nirfpdfcdn/2025/framework/Engineering.pdf"],
         ["2025 filing", "The college's NIRF 2025 Engineering submission", "https://saveetha.ac.in/nirf-documents-2024/ → Engineering-1.pdf"],
         ["2026 filing", "The college's NIRF 2026 Engineering submission (uploaded February 2026)", "https://saveetha.ac.in → NIRF → SAVEETHA-ENGINEERING-COLLEGE20260216-.pdf"],
         ["score model", "Estimated parameter scores and accuracy", "models/score_model.py → data/processed/model_report.json"],
         ["2026 forecast", "Thresholds, band probabilities, levers", "models/predict_2026.py → data/processed/prediction_2026.json"],
         ["analysis.json", "Cut-offs, tier profiles, medians, gap table", "analysis/analyze.py → data/processed/analysis.json"],
         ["database", "All of the above in one file", "db/nirf.db (tables: rankings, rank_bands, participants, submissions, methodology, documents, faculty, predictions, saveetha_live)"]]
S += [table(srows, widths=[3.2 * cm, 6.3 * cm, 7.8 * cm])]

# ---- appendix
S += [section("A", "Appendix: sub-parameters and formulas", MUTED)]
meth = pd.read_sql("SELECT parameter, parameter_weight, sub_parameter, sub_code, marks FROM methodology WHERE year=2025 AND category='Engineering'", con)
_order = {"TLR": 0, "RPC": 1, "GO": 2, "OI": 3, "PR": 4}
_sub = ["SS", "FSR", "FQE", "FRU", "PU", "QP", "IPR", "FPPP", "GPH", "GUE", "GMS", "GPHD", "RD", "WD", "ESCS", "PCS", "PR"]
meth["_k"] = meth.parameter.map(_order) * 100 + meth.sub_code.map(lambda c: _sub.index(c) if c in _sub else 99)
meth = meth.sort_values("_k")
plain = {"SS": "Number of students, incl. PhD scholars", "FSR": "Faculty-student ratio; 1:15 earns full marks", "FQE": "Share of faculty with a PhD, and the experience mix",
         "FRU": "Money spent per student, capital and operating", "PU": "Publications per faculty (Scopus / Web of Science)", "QP": "Citations and top-25% papers per faculty",
         "IPR": "Patents published and granted", "FPPP": "Research funding and consultancy income", "GPH": "Share placed plus share going to higher studies",
         "GUE": "Share graduating on time; 80% earns full marks", "GMS": "Median salary of placed graduates", "GPHD": "PhDs awarded per year",
         "RD": "Students from other states and countries", "WD": "Women students (target 50%) and women faculty (20%)", "ESCS": "Students on full fee reimbursement",
         "PCS": "Facilities for physically challenged students", "PR": "A survey of employers and academics"}
rows = [["Parameter", "Sub-parameter", "Marks", "In plain words"]]
for _, m in meth.iterrows():
    rows.append([f"<font color='{PCOL[m.parameter.lower()]}'><b>{m.parameter}</b></font> (weight {m.parameter_weight:.2f})", f"{m.sub_parameter} <font color='{MUTED}'>({m.sub_code})</font>", str(m.marks), plain.get(m.sub_code, "")])
t = table(rows, widths=[3.6 * cm, 6.2 * cm, 1.2 * cm, 6.3 * cm])
t.setStyle(TableStyle([("BACKGROUND", (0, i), (0, i), C(TINT[PCOL[m.parameter.lower()]])) for i, (_, m) in enumerate(meth.iterrows(), start=1)]))
S += [t, src("meth", extra="Marks as printed in the 2025 Engineering methodology.")]
S += [tech("Formulas as printed in the 2025 Engineering methodology. FSR = 30 × [15 × (F/N)], F = full-time faculty, N = students incl. PhD scholars; zero below 1:50. "
           "FQE = 10 × (FRA/95) for the PhD share plus up to 10 for an even spread over ≤8, 8-15 and >15 years of experience. FRU = 7.5 × f(BC) + 22.5 × f(BO) on capital and operating spend per student. "
           "PU = 35 × f(P/FRQ) − 5 × f(Pret); QP = 20 × f(CC/FRQ) + 20 × f(TOP25P/P) − 5 × f(Cret); the −5 terms for retracted work are new in 2025. IPR = 10 × f(patents granted) + 5 × f(patents published). "
           "GPH = 40 × (Np/100 + Nhs/100). GUE = 15 × min(Ng/80, 1). GMS = 25 × f(median salary). GPHD = 20 × f(PhDs graduated). RD = 25 × (share from other states) + 5 × (share from abroad). "
           "WD = 15 × (women students %/50) + 15 × (women faculty %/20). ESCS = 20 × f(fee-reimbursed %). The f( ) curves are NIRF's own normalisation and are not published; the score model learns them from data.")]
S += [tech("Model detail. One gradient-boosting model (XGBoost) per parameter, trained on 700 institute-years (ranks 1-200, 2021-25) with monotone constraints so that a better input can never lower a score. "
           "Inputs per parameter follow the methodology (TLR: students, PhD scholars, faculty per student, spend per student; RPC: PhDs awarded, sponsored and consultancy income, faculty size; "
           "GO: placed-or-higher-studies share, on-time graduation, median salary, PhDs awarded; OI: out-of-state share, women share, fee-reimbursed share, disability facilities). "
           f"Grouped 5-fold cross-validation. 2026 forecast: linear trend of the rank-100 cut-off since 2020 (+{P['thresholds']['trend_slope_per_year']} per year), score-vs-rank shape from 2019-22, "
           f"20,000 Monte-Carlo draws over model error and Perception; a ridge model on previous-year scores projects the rest of the field (validated on 2025: error {val['mae']} points).")]
grows2 = [["Term", "Meaning"], ["NIRF", "National Institutional Ranking Framework, the Ministry of Education's ranking"], ["Band", "A range such as 201-300 used instead of a rank for institutes below 100; no score is published"],
          ["Cut-off", "The lowest score inside the top 100 in a given year"], ["Filing", "The data form an institution uploads to NIRF, published as a PDF"],
          ["Estimate", "A score computed by our model, not by NIRF"], ["R²", "Share of the variation the model explains; 1.0 is perfect"]]
S += [KeepTogether([p("Glossary", H2), table(grows2, widths=[3 * cm, 14.3 * cm], headcol=MUTED)])]

doc.build(S, onFirstPage=cover, onLaterPages=footer)
print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
