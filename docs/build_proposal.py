"""Build docs/NIRF_Proposal_and_Progress_Report.pdf

Part A is a proposal (background, problem, objectives, solution, method, plan, resources, risks).
Part B reports the work completed, the findings, recommendations, pending items and resources.
All figures are read from db/nirf.db and data/processed/*.json. Charts are produced by
docs/build_report.py into docs/img/, so run that first.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Flowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)


class Mark(Flowable):
    """Invisible marker that records the page it lands on."""

    def __init__(self, key):
        super().__init__()
        self.key = key
        self.width = self.height = 0

    def draw(self):
        pass

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "NIRF_Proposal_and_Progress_Report.pdf"
IMG = ROOT / "docs" / "img"
P = json.loads((ROOT / "data/processed/prediction_2026.json").read_text())
A = json.loads((ROOT / "data/processed/analysis.json").read_text())
M = json.loads((ROOT / "data/processed/model_report.json").read_text())
con = sqlite3.connect(ROOT / "db/nirf.db")
W, H = A4

# ------------------------------------------------------------------ palette & styles
NAVY, CORAL, GOLD, TEAL, SKY, PLUM = "#1B2A4A", "#E4572E", "#F3A712", "#17A398", "#3E92CC", "#7B4B94"
INK, MUTED, LINE, PAPER = "#1F2937", "#5B6B7F", "#D9DEE7", "#F6F8FB"
TINT = {SKY: "#E8F1FA", CORAL: "#FCEAE4", GOLD: "#FEF3DC", TEAL: "#E3F5F2", PLUM: "#EFE7F3", NAVY: "#E6E9F0",
        MUTED: "#F3F5F8"}
C = colors.HexColor

ss = getSampleStyleSheet()
BODY = ParagraphStyle("B", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14.6, spaceAfter=7,
                      textColor=C(INK))
LEAD = ParagraphStyle("Lead", parent=BODY, fontSize=11.2, leading=16.4, textColor=C(NAVY))
SMALL = ParagraphStyle("S", parent=BODY, fontSize=8.4, leading=11.4, textColor=C(MUTED))
SRC = ParagraphStyle("Src", parent=SMALL, fontSize=7.3, leading=9.4, textColor=C("#6B7A90"), spaceBefore=1,
                     spaceAfter=9)
H2 = ParagraphStyle("H2", parent=BODY, fontName="Helvetica-Bold", fontSize=12, leading=15.5, textColor=C(NAVY),
                    spaceBefore=9, spaceAfter=4, keepWithNext=1)
BUL = ParagraphStyle("Bul", parent=BODY, leftIndent=14, bulletIndent=3, spaceAfter=4)
HEADCELL = ParagraphStyle("Head", parent=SMALL, textColor=colors.white, fontName="Helvetica-Bold", fontSize=8.2,
                          leading=10.2)
CELL = ParagraphStyle("Cell", parent=SMALL, textColor=C(INK), fontSize=8.3, leading=10.8)


def p(t, st=BODY):
    return Paragraph(t, st)


def src(text):
    return Paragraph("Source: " + text, SRC)


def bullets(items):
    return [Paragraph(i, BUL, bulletText="•") for i in items]


def section(num, title, col=NAVY):
    n = Paragraph(f"<font color='white'><b>{num}</b></font>",
                  ParagraphStyle("n", parent=BODY, fontSize=11.5, leading=13, alignment=TA_CENTER))
    t = Paragraph(f"<b>{title}</b>", ParagraphStyle("t", parent=BODY, fontSize=16, leading=19, textColor=C(NAVY)))
    tb = Table([[n, t]], colWidths=[1.15 * cm, 16.2 * cm], rowHeights=[0.95 * cm])
    tb.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), C(col)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (1, 0), (1, 0), 8), ("LINEBELOW", (0, 0), (-1, 0), 1.2, C(col)),
                            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    tail = Spacer(1, 8)
    tb.keepWithNext = 1
    tail.keepWithNext = 1
    return [Spacer(1, 6), tb, tail]


def callout(text, col=SKY, label=None):
    body = [Paragraph(text, ParagraphStyle("co", parent=BODY, spaceAfter=0))]
    if label:
        body.insert(0, Paragraph(f"<font color='{col}'><b>{label.upper()}</b></font>",
                                 ParagraphStyle("cl", parent=SMALL, fontSize=7.5, spaceAfter=3)))
    t = Table([["", body]], colWidths=[0.18 * cm, 17.1 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), C(col)), ("BACKGROUND", (1, 0), (1, 0), C(TINT[col])),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (1, 0), (1, 0), 10),
                           ("RIGHTPADDING", (1, 0), (1, 0), 10), ("TOPPADDING", (1, 0), (1, 0), 8),
                           ("BOTTOMPADDING", (1, 0), (1, 0), 8)]))
    return KeepTogether([Spacer(1, 3), t, Spacer(1, 8)])


def tiles(items):
    cells = [[Paragraph(f"<font color='{col}'><b>{num}</b></font>",
                        ParagraphStyle("tn", parent=BODY, fontSize=17, leading=20, spaceAfter=2)),
              Paragraph(lab, ParagraphStyle("tl", parent=SMALL, fontSize=8.1, leading=10.4))]
             for num, lab, col in items]
    t = Table([cells], colWidths=[17.3 * cm / len(items)] * len(items))
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9),
          ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 8),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]
    for i, (_, _, col) in enumerate(items):
        st += [("BACKGROUND", (i, 0), (i, 0), C(TINT[col])), ("LINEABOVE", (i, 0), (i, 0), 3, C(col))]
    t.setStyle(TableStyle(st))
    return KeepTogether([t, Spacer(1, 10)])


STATUS = {"Complete": TEAL, "In progress": GOLD, "Pending": CORAL, "Optional": MUTED}


def status(s):
    return f"<font color='{STATUS[s]}'><b>{s}</b></font>"


def table(data, widths, head=True, align="LEFT", headcol=NAVY, zebra=True):
    data = [[c if not isinstance(c, str) else Paragraph(c, HEADCELL if (head and i == 0) else CELL) for c in row]
            for i, row in enumerate(data)]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, C(LINE)),
          ("ALIGN", (1, 1), (-1, -1), align), ("LEFTPADDING", (0, 0), (-1, -1), 5),
          ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 3.6),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), C(headcol)))
    if zebra:
        st += [("BACKGROUND", (0, i), (-1, i), C(PAPER)) for i in range(1 if head else 0, len(data)) if i % 2 == 0]
    t.setStyle(TableStyle(st))
    return t


def fig(name, w=16.2 * cm):
    im = Image(str(IMG / f"{name}.png"))
    im.drawWidth, im.drawHeight = w, w * im.imageHeight / im.imageWidth
    return im


def part_divider(letter, title, subtitle, col):
    """A full-width coloured band that opens Part A / Part B / Part C."""
    band = Table([[Paragraph(f"<font color='white'>PART {letter}</font>",
                             ParagraphStyle("pl", parent=BODY, fontSize=10, leading=12, fontName="Helvetica-Bold")),
                   ],
                  [Paragraph(f"<font color='white'><b>{title}</b></font>",
                             ParagraphStyle("pt", parent=BODY, fontSize=24, leading=28))],
                  [Paragraph(f"<font color='#DDE3EE'>{subtitle}</font>",
                             ParagraphStyle("ps", parent=BODY, fontSize=10.5, leading=15))]],
                 colWidths=[17.3 * cm])
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C(col)), ("LEFTPADDING", (0, 0), (-1, -1), 16),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 16), ("TOPPADDING", (0, 0), (0, 0), 16),
                              ("BOTTOMPADDING", (0, -1), (-1, -1), 18), ("LINEBELOW", (0, -1), (-1, -1), 4, C(GOLD))]))
    return [Mark(letter), band, Spacer(1, 14)]


# ------------------------------------------------------------------ data
hist = pd.read_sql("SELECT * FROM v_saveetha_history", con)
sec_est = M["saveetha_estimates"]
e25, e26 = sec_est[-2], sec_est[-1]
s = P["saveetha"]
thr = P["thresholds"]["forecast_2026"]
bp = s["band_probabilities"]
top200 = bp["top 100"] + bp["101-150"] + bp["151-200"]
wgap = A["saveetha_weighted_gap_by_param"]
mp = M["params"]
val = P["top100_model_validation"]
counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
          for t in ("rankings", "rank_bands", "participants", "submissions", "documents")}
cut = pd.read_sql("SELECT year, MIN(score) s FROM rankings WHERE category='Engineering' AND rank<=100 GROUP BY year",
                  con).set_index("year")["s"]
try:
    oa = json.loads((ROOT / "data/processed/openalex_ids.json").read_text())
    oa_matched = sum(1 for v in oa.values() if (v.get("id") if isinstance(v, dict) else v))
    oa_resolved = len(oa)
except FileNotFoundError:
    oa_matched = oa_resolved = 0
TODAY = date.today().strftime("%d %B %Y")

REPO = "https://github.com/rnandakishore2408/nirf_analytics"


# ------------------------------------------------------------------ page furniture
def cover(canvas, d):
    canvas.saveState()
    canvas.setFillColor(C(NAVY))
    canvas.rect(0, H - 13.2 * cm, W, 13.2 * cm, stroke=0, fill=1)
    canvas.setFillColor(C(CORAL))
    canvas.rect(0, H - 13.2 * cm, W, 0.32 * cm, stroke=0, fill=1)
    canvas.setFillColor(C(GOLD))
    canvas.rect(0, H - 13.52 * cm, 6.5 * cm, 0.32 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 10.5)
    canvas.drawString(1.8 * cm, H - 2.2 * cm, "SAVEETHA ENGINEERING COLLEGE  ·  SRIPERUMBUDUR")
    canvas.setFont("Helvetica-Bold", 30)
    canvas.drawString(1.8 * cm, H - 4.5 * cm, "NIRF Analytics &")
    canvas.drawString(1.8 * cm, H - 5.8 * cm, "Ranking Intelligence")
    canvas.setFont("Helvetica", 16)
    canvas.setFillColor(C("#DDE3EE"))
    canvas.drawString(1.8 * cm, H - 7.0 * cm, "Project Proposal and Progress Report")
    canvas.setFont("Helvetica", 10.5)
    for i, line in enumerate(["A data platform to understand the college's position in the NIRF Engineering",
                              "ranking, the factors that drive it, and the likely outcome in 2026."]):
        canvas.drawString(1.8 * cm, H - 8.4 * cm - i * 0.55 * cm, line)
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(C("#B9C3D6"))
    canvas.drawString(1.8 * cm, H - 11.3 * cm, f"Date: {TODAY}")
    canvas.drawString(1.8 * cm, H - 11.85 * cm, "Prepared by: R. Nanda Kishore")
    canvas.drawString(1.8 * cm, H - 12.4 * cm, "Status: platform built and operational; one data enhancement in progress")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(C(MUTED))
    canvas.drawString(1.8 * cm, 1.0 * cm, "NIRF Analytics · Proposal and Progress Report")
    canvas.drawRightString(W - 1.8 * cm, 1.0 * cm, "Page 1")
    canvas.restoreState()


def footer(canvas, d):
    canvas.saveState()
    canvas.setStrokeColor(C(CORAL))
    canvas.setLineWidth(1.2)
    canvas.line(1.8 * cm, 1.45 * cm, 4.3 * cm, 1.45 * cm)
    canvas.setStrokeColor(C(LINE))
    canvas.setLineWidth(0.5)
    canvas.line(4.3 * cm, 1.45 * cm, W - 1.8 * cm, 1.45 * cm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(C(MUTED))
    canvas.drawString(1.8 * cm, 1.0 * cm, "NIRF Analytics · Proposal and Progress Report · Saveetha Engineering College")
    canvas.drawRightString(W - 1.8 * cm, 1.0 * cm, f"Page {d.page}")
    canvas.restoreState()


# ------------------------------------------------------------------ story
def make_story(pages: dict) -> list:
    S = []

    # cover body: contents
    S += [Spacer(1, 12.9 * cm)]
    toc = [["", "Contents", ""],
           ["A", "<b>Proposal</b>: background, problem, objectives, proposed solution, method, plan, resources, risks", str(pages.get("A", ""))],
           ["B", "<b>Progress report</b>: work completed, findings, recommendations, pending items", str(pages.get("B", ""))],
           ["C", "<b>Resources and references</b>: data sources, tools, links, glossary", str(pages.get("C", ""))]]
    t = table(toc, [1.0 * cm, 14.3 * cm, 2.0 * cm], head=True, align="LEFT")
    S += [t, Spacer(1, 12)]
    S += [callout("Figures quoted for the college are <b>model estimates</b> unless stated otherwise, because NIRF "
                  "publishes no score for institutions placed in rank bands. Every figure carries its source in grey.",
                  col=GOLD, label="Reading this document")]
    S += [PageBreak()]

    # ================================================================== PART A
    S += part_divider("A", "Proposal", "Why this work is needed, what it will deliver, and what it takes.", NAVY)

    S += section("1", "Executive summary")
    S += [p("The National Institutional Ranking Framework (NIRF) is the Ministry of Education's annual ranking of Indian "
            "higher-education institutions. Saveetha Engineering College participates in the Engineering category every "
            "year. In 2024 and 2025 it was placed in the 201-300 band. For band placements NIRF publishes no score, so the "
            "college has no official view of how far it is from the next band, or which factors hold it back.", LEAD)]
    S += [p("This proposal sets out a data platform that closes that gap. It collects every published NIRF result and the "
            "underlying data institutions submit, reconstructs the scoring method, estimates the college's own parameter "
            "scores, forecasts the 2026 outcome, and gives staff a web application to track current figures and test "
            "improvement scenarios. It is built entirely on free, open tools.")]
    S += [tiles([("201-300", "NIRF 2025 Engineering band (same in 2024)", CORAL),
                 (f"≈ {e26['total_est']:.0f}", "Estimated score, 2026 filing", SKY),
                 (f"{thr['100']:.0f}", "Forecast score at rank 100 in 2026", GOLD),
                 ("₹ 0", "Recurring software cost; all free tiers", TEAL)])]
    S += [src("NIRF band pages (nirfindia.org); platform score model and 2026 forecast; resource plan in section 9.")]

    S += section("2", "Background: how NIRF ranks an institution", SKY)
    S += [p("Each institution receives a score out of 100 built from five parameters. For Engineering the weights are:")]
    wt = [["Parameter", "What it measures", "Weight"],
          [f"<font color='{SKY}'><b>TLR</b></font> Teaching, Learning & Resources",
           "Student strength, faculty-student ratio, faculty qualifications, spending per student", "30%"],
          [f"<font color='{CORAL}'><b>RPC</b></font> Research & Professional Practice",
           "Publications, citations, patents, research funding and consultancy", "30%"],
          [f"<font color='{TEAL}'><b>GO</b></font> Graduation Outcomes",
           "Placement and higher studies, graduation on time, median salary, PhDs awarded", "20%"],
          [f"<font color='{GOLD}'><b>OI</b></font> Outreach & Inclusivity",
           "Students from other states, women, economically disadvantaged students, accessibility", "10%"],
          [f"<font color='{PLUM}'><b>PR</b></font> Perception", "Survey of employers and academics", "10%"]]
    S += [table(wt, [5.4 * cm, 10.1 * cm, 1.8 * cm], align="LEFT", headcol=SKY),
          src("NIRF Engineering methodology 2025, nirfindia.org/nirfpdfcdn/2025/framework/Engineering.pdf")]
    S += [p("Only the top 100 receive a numeric rank. Institutions below are grouped into bands (101-150, 151-200, "
            "201-300) with no score. The formulas are published, but the normalisation step that converts raw figures "
            "into marks is not, so an institution cannot compute its own score from its own data.")]

    S += section("3", "Problem statement", CORAL)
    S += bullets([
        "<b>No visibility of the college's own score.</b> NIRF has published no score for the college since 2019. "
        "Leadership sees only a band, not the distance to the next one.",
        "<b>No clear picture of what drives the result.</b> Without parameter scores it is not possible to tell whether "
        "teaching, research, outcomes or diversity is holding the college back.",
        "<b>The bar keeps rising.</b> The score at rank 100 rose from "
        f"{cut[2023]:.2f} (2023) to {cut[2024]:.2f} (2024) to {cut[2025]:.2f} (2025). Standing still means falling behind.",
        "<b>Research output is invisible in public data.</b> Publications and citations carry 75 of the 100 marks in the "
        "research parameter, yet NIRF's public data forms do not include them.",
        "<b>No internal tracking.</b> Current-year figures are compiled once a year for the submission, not monitored "
        "during the year when they can still be improved.",
    ])
    S += [src("NIRF Engineering ranking tables 2023-2025; NIRF methodology 2025.")]

    S += section("4", "Objectives", TEAL)
    obj = [["#", "Objective", "Measure of success"],
           ["1", "Build a complete, verifiable record of NIRF Engineering results", "All years 2017-2025, checked against the live site"],
           ["2", "Reconstruct NIRF's scoring from public data", "Published scores reproduced within a few points"],
           ["3", "Estimate the college's parameter scores", "Estimate consistent with the band NIRF published"],
           ["4", "Identify the factors that separate the college from higher bands", "Gap quantified per parameter"],
           ["5", "Forecast the 2026 outcome with honest uncertainty", "Band probabilities, not a single guess"],
           ["6", "Give staff a tool to track figures and test scenarios", "Web app usable without technical skills"],
           ["7", "Keep running costs at zero", "Free and open-source components only"]]
    S += [table(obj, [0.8 * cm, 9.4 * cm, 7.1 * cm], headcol=TEAL)]

    S += section("5", "Proposed solution", SKY)
    S += [p("An end-to-end analytics platform in six layers. Each layer is a script that can be re-run when NIRF "
            "publishes new results.")]
    S += [fig("architecture", 16.6 * cm), Spacer(1, 4)]
    comp = [["Layer", "What it does"],
            ["1  Data collection", "Downloads NIRF ranking tables, band pages, applicant lists, 704 institution data forms, "
                                   "the methodology documents, and the college's own filings"],
            ["2  Processing", "Converts web pages and PDFs into clean, structured records (about 189 fields per institution)"],
            ["3  Database", "One file holding rankings, bands, submissions, methodology, documents, live staff data and forecasts"],
            ["4  Models", "Learns NIRF's hidden scoring step; estimates the college's scores; forecasts 2026"],
            ["5  Analysis", "Cut-offs, tier profiles, peer comparisons, the college's gap and improvement levers"],
            ["6  Application", "Six-page dashboard, what-if sliders, staff data entry, and a question-answering assistant"]]
    S += [table(comp, [3.6 * cm, 13.7 * cm], headcol=SKY)]

    S += section("6", "Methodology", PLUM)
    S += bullets([
        "<b>Reconstructing the score.</b> For 700 institution-years both the submitted figures and the published "
        "parameter scores are known. A gradient-boosting model (XGBoost) learns the mapping for each parameter, with "
        "monotone constraints so that a better input can never lower a score.",
        "<b>Validation.</b> Each institution is held out and predicted from the others (grouped 5-fold cross-validation). "
        "The college's 2025 estimate is checked against the band NIRF actually published.",
        "<b>Forecasting.</b> The rank-100 cut-off is projected from its 2020-2025 trend. The college's 2026 score is "
        "simulated 20,000 times to reflect model error and the unknown perception score, giving band probabilities.",
        "<b>Scenario analysis.</b> Each improvement lever is applied to the college's filing one at a time and re-scored.",
        "<b>Data quality.</b> Every figure is traceable to a stored source file. Known site anomalies are corrected, and "
        "safety checks stop incomplete data from distorting results.",
    ])
    S += [src("models/score_model.py, models/predict_2026.py in the project repository.")]

    S += section("7", "Scope and deliverables", GOLD)
    dl = [["Deliverable", "Description"],
          ["Research database", "NIRF results 2017-2025 and 704 parsed institution filings, in a single file"],
          ["Scoring and forecast models", "Parameter estimates for the college; 2026 band probabilities"],
          ["Web application", "Home, Top-100 Explorer, College Position, Gap & What-If, Prediction 2026, Live Data Entry, Ask the Data"],
          ["Live data store", "Hosted database so staff entries persist; local fallback when offline"],
          ["Reports", "This proposal and progress report; a staff analytics report; a handover document"],
          ["Source code", "Complete, version-controlled repository with a one-command refresh"]]
    S += [table(dl, [4.4 * cm, 12.9 * cm], headcol=GOLD)]
    S += [p("<b>Out of scope.</b> Official NIRF scores for band placements (not published), the perception survey "
            "(not observable), and categories other than Engineering, which can be added later.", SMALL)]

    S += section("8", "Implementation plan", NAVY)
    plan = [["Phase", "Activity", "Status"],
            ["1", "Study the NIRF methodology and weights", status("Complete")],
            ["2", "Collect rankings, bands, applicant lists and institution filings", status("Complete")],
            ["3", "Process and store the data; correct site anomalies", status("Complete")],
            ["4", "Build and validate the scoring model", status("Complete")],
            ["5", "Estimate the college's scores and quantify the gap", status("Complete")],
            ["6", "Forecast 2026 and model improvement scenarios", status("Complete")],
            ["7", "Build the web application and live data store", status("Complete")],
            ["8", "Reports, handover and source repository", status("Complete")],
            ["9", "Add peer publication data from an open research database", status("In progress")],
            ["10", "Collect the college's own publication and citation counts", status("Pending")],
            ["11", "Host the application online for staff", status("Pending")],
            ["12", "Extend to Innovation and SDG categories; yearly auto-refresh", status("Optional")]]
    S += [table(plan, [1.3 * cm, 12.8 * cm, 3.2 * cm], headcol=NAVY, align="LEFT")]

    S += section("9", "Resource requirements", TEAL)
    S += [p("People", H2)]
    ppl = [["Role", "Responsibility", "Effort"],
           ["Developer / analyst", "Builds and maintains the platform, refreshes data yearly", "Build complete; about 1 day a year to refresh"],
           ["NIRF / IQAC coordinator", "Enters current-year figures in the application", "A few hours per term"],
           ["Research office", "Supplies publication and citation counts (Scopus / Web of Science)", "Once a year"]]
    S += [table(ppl, [4.0 * cm, 7.8 * cm, 5.5 * cm], headcol=TEAL)]
    S += [p("Technology and cost", H2)]
    tech_rows = [["Component", "Used for", "Cost"],
                 ["Python and open-source libraries", "Data collection, processing, models, reports", "Free"],
                 ["SQLite", "Main database file", "Free"],
                 ["Streamlit Community Cloud", "Hosting the web application", "Free"],
                 ["Supabase (free tier)", "Storing staff-entered live data", "Free"],
                 ["Groq and Google Gemini (free tiers)", "Question-answering assistant", "Free"],
                 ["OpenAlex", "Open research-publication data for peer institutions", "Free (daily request limit)"],
                 ["GitHub", "Source code and version history", "Free"],
                 ["Hardware", "Any standard laptop", "Existing"]]
    S += [table(tech_rows, [5.6 * cm, 8.3 * cm, 3.4 * cm], headcol=TEAL)]
    S += [callout("Total recurring cost: <b>nil</b>. No card or paid plan is needed for any component.", col=TEAL)]

    S += section("10", "Risks and mitigations", CORAL)
    risk = [["Risk", "Impact", "Mitigation"],
            ["Estimates mistaken for official NIRF scores", "Misleading decisions",
             "Every figure labelled as an estimate; uncertainty shown as ranges"],
            ["NIRF changes its methodology", "Forecast becomes outdated",
             "Methodology re-read each year; one command refreshes everything"],
            ["Research output not visible in public data", "Research estimate least certain",
             "College enters its own counts; safety check blocks unreliable peer data"],
            ["Open research database covers smaller colleges poorly", "Biased research model",
             "Coverage checked by rank band before the data is used"],
            ["Free-tier limits (request quotas, database pausing)", "Temporary interruption",
             "Local fallback storage; resumable data collection"],
            ["Credentials exposed", "Security",
             "Keys kept in a private settings file excluded from the repository"]]
    S += [table(risk, [5.3 * cm, 3.8 * cm, 8.2 * cm], headcol=CORAL)]

    S += section("11", "Data handling and governance", MUTED)
    S += bullets([
        "All reference data is public: NIRF results, published institution filings and the college's own public filings.",
        "Staff entries are stored with the name of the person and the date, so every change is traceable.",
        "No personal student data is collected. Faculty names appear only where the college itself published them.",
        "API keys and the database password are held in a private file that is never committed or shared.",
    ])

    # ================================================================== PART B
    S += [PageBreak()]
    S += part_divider("B", "Progress report", "What has been built, what the data shows, and what remains.", CORAL)

    S += section("12", "Work completed", TEAL)
    done = [["Area", "Result"],
            ["Rankings collected", f"{counts['rankings']:,} scored entries across Engineering, Overall, College and University, 2017-2025"],
            ["Band placements", f"{counts['rank_bands']:,} entries for 101-150, 151-200 and 201-300"],
            ["Applicant records", f"{counts['participants']:,} entries"],
            ["Institution filings parsed", f"{counts['submissions']:,} PDFs, about 189 fields each"],
            ["Documents indexed for the assistant", f"{counts['documents']:,}"],
            ["Scoring model accuracy", f"Published totals reproduced within {M['total_score_fit']['mae']} points on average"],
            ["Forecast model check", f"2025 predicted from 2024 with average error {val['mae']} points"],
            ["Web application", "Seven pages, tested; live data saved to a hosted database"],
            ["Data corrections", "2016 duplicate pages removed; mislabelled band pages fixed; a missing 2021 placement recovered"]]
    S += [table(done, [5.0 * cm, 12.3 * cm], headcol=TEAL)]
    S += [src("Project database db/nirf.db; model_report.json; prediction_2026.json.")]

    S += section("13", "Findings", SKY)
    S += [p("13.1 The college's NIRF record", H2)]
    rec = [["Year", "Result", "Score"]]
    for _, h in hist[hist.category == "Engineering"].iterrows():
        pos = f"Rank {int(h.rank_or_band_low)}" if h.status == "ranked" else f"Band {int(h.rank_or_band_low)}-{int(h.rank_or_band_high)}"
        rec.append([str(int(h.year)), pos, "–" if pd.isna(h.score) else f"{h.score:.2f}"])
    rec.insert(6, ["2022", "Applied; not placed in a published list", "–"])
    rec.insert(7, ["2023", "Applied; not placed in a published list", "–"])
    S += [table(rec, [2.2 * cm, 10.5 * cm, 4.6 * cm], headcol=SKY, align="LEFT"),
          src("NIRF Engineering ranking and band pages, verified against nirfindia.org. A dash means no score was published.")]

    S += [KeepTogether([p("13.2 The rising bar", H2), fig("cutoff", 15.6 * cm),
                        src("NIRF ranking tables (cut-off); score model (college estimates, open circles).")])]
    S += [p(f"The score at rank 100 has risen about {P['thresholds']['trend_slope_per_year']:.1f} points a year since 2020. "
            f"The college's filings are estimated at {e25['total_est']:.1f} (2025) and {e26['total_est']:.1f} (2026): a real "
            f"improvement, but the bar is moving almost as fast.")]

    S += [KeepTogether([p("13.3 Where the gap is", H2), fig("compare", 15.6 * cm),
                        src("Score model estimates from the 2026 filing; averages of published 2025 scores.")])]
    gap_rows = [["Parameter", "Estimated points lost versus rank 90-100"]]
    for k, lab in (("rpc", "RPC  Research"), ("tlr", "TLR  Teaching & resources"), ("oi", "OI  Outreach"),
                   ("go", "GO  Graduation outcomes"), ("pr", "PR  Perception")):
        col = CORAL if wgap[k] > 1 else INK
        gap_rows.append([lab, f"<font color='{col}'><b>{wgap[k]:+.2f}</b></font>"])
    S += [table(gap_rows, [9 * cm, 8.3 * cm], headcol=SKY, align="CENTER"), src("analysis.json (computed from the database).")]
    S += [callout(f"Research accounts for about {wgap['rpc']:.1f} of the weighted points separating the college from the "
                  "rank 90-100 group. Placements, graduation on time and women's participation are already at or above "
                  "that group.", col=CORAL, label="Key finding")]

    S += [KeepTogether([p("13.4 2026 outlook", H2), fig("bands", 15.2 * cm),
                        src("prediction_2026.json: 20,000 simulations of the 2026 filing.")])]
    S += [tiles([(f"{s['total_score']['median']}", f"Estimated total (likely {s['total_score']['p10']}-{s['total_score']['p90']})", PLUM),
                 (s["most_likely_band"], f"Most likely band ({100 * bp[s['most_likely_band']]:.0f}%)", SKY),
                 (f"{100 * top200:.0f}%", "Chance of the top 200", TEAL),
                 (f"{100 * bp['top 100']:.0f}%", "Chance of the top 100", CORAL)])]
    S += [p("The adjacent bands are close (101-150 at "
            f"{100 * bp['101-150']:.0f}%, 201-250 at {100 * bp['201-250']:.0f}%), so the result is best read as "
            "\"the 100s to low 200s\". The range is wide because perception and publication counts cannot be observed.")]

    S += section("14", "Recommendations", GOLD)
    S += [KeepTogether([fig("levers", 15.6 * cm),
                        src("prediction_2026.json: each change applied alone to the 2026 filing and re-scored.")])]
    S += bullets([
        "<b>Expand the PhD pipeline.</b> PhDs awarded is the largest single lever. Enrolment decisions now determine "
        "awards three to four years later.",
        "<b>Grow publications and citations.</b> They are 75 of the 100 research marks. Track Scopus output per "
        "department and avoid retractions, which NIRF now penalises.",
        "<b>Raise spending per student</b> on laboratories, equipment and e-resources.",
        "<b>Lift the median graduate salary</b>, which depends on the middle of the batch rather than top offers.",
        "<b>Increase sponsored research and admissions from other states.</b>",
        "<b>Maintain current strengths</b> in placement, graduation on time and inclusion.",
    ])

    S += section("15", "Pending items and next steps", CORAL)
    pend = [["Item", "Status", "Detail", "Owner"],
            ["Peer publication data", status("In progress"),
             f"{oa_matched} of 277 institutions matched so far. Smaller colleges are poorly covered, so the data "
             "stays switched off until coverage is representative.", "Developer"],
            ["College publication counts", status("Pending"),
             "Papers and citations for the last three years. The college is not listed in the open database, so this "
             "must come from the research office.", "Research office"],
            ["Online hosting", status("Pending"),
             "Publish on Streamlit Community Cloud so staff can use it from any device.", "Developer"],
            ["Staff trial", status("Pending"),
             "Coordinator enters current figures and reviews each page.", "NIRF coordinator"],
            ["Further categories and auto-refresh", status("Optional"),
             "Innovation and SDG categories; refresh when NIRF 2026 is published.", "Developer"]]
    S += [table(pend, [3.6 * cm, 2.4 * cm, 8.3 * cm, 3.0 * cm], headcol=CORAL)]

    S += section("16", "Limitations", MUTED)
    S += bullets([
        "The college's parameter scores are estimates; NIRF has published none since 2019.",
        f"Research carries most of the uncertainty. Model accuracy for research is R² {mp['rpc']['cv_r2']:.2f}, "
        f"against {mp['go']['cv_r2']:.2f} for graduation outcomes.",
        "Perception is a survey and is treated as an assumption, not an estimate.",
        "The forecast assumes NIRF keeps its 2025 methodology.",
    ])
    acc = [["Parameter", "Institutions used", "Variation explained (R²)", "Typical error"]]
    for k, v in mp.items():
        acc.append([k.upper(), str(v["n"]), f"{v['cv_r2']:.2f}", f"{v['cv_mae']:.1f} points"])
    S += [table(acc, [3.4 * cm, 4.0 * cm, 5.4 * cm, 4.5 * cm], headcol=MUTED, align="CENTER"),
          src("model_report.json; grouped 5-fold cross-validation.")]

    # ================================================================== PART C
    S += [PageBreak()]
    S += part_divider("C", "Resources and references", "Where every figure comes from, and the tools used.", TEAL)

    S += section("17", "Data sources", TEAL)
    srcs = [["Source", "Content", "Address"],
            ["NIRF ranking tables", "Scores and ranks, 2017-2025", "nirfindia.org/Rankings/&lt;year&gt;/EngineeringRanking.html"],
            ["NIRF band pages", "Band placements without scores", "nirfindia.org/Rankings/&lt;year&gt;/EngineeringRanking150.html (…200, …300)"],
            ["NIRF applicant lists", "All participating institutions", "nirfindia.org/Rankings/&lt;year&gt;/EngineeringRankingALL.html"],
            ["Institution data forms", "Submitted figures of ranked institutions", "nirfindia.org/nirfpdfcdn/&lt;year&gt;/pdf/Engineering/&lt;id&gt;.pdf"],
            ["NIRF methodology", "Parameters, marks, weights, formulas", "nirfindia.org/nirfpdfcdn/2025/framework/Engineering.pdf"],
            ["College filings", "NIRF 2025 and 2026 submissions", "saveetha.ac.in (NIRF documents)"],
            ["OpenAlex", "Publication and citation counts of peer institutions", "openalex.org"]]
    S += [table(srcs, [3.6 * cm, 5.4 * cm, 8.3 * cm], headcol=TEAL)]
    S += [p("Copies of every downloaded page and document are stored unchanged in the repository under "
            "<font face='Courier'>data/raw</font>, so any figure can be checked.", SMALL)]

    S += section("18", "Tools and platform", SKY)
    tools = [["Area", "Tools"],
             ["Programming", "Python 3.13"],
             ["Collection and parsing", "requests, BeautifulSoup, poppler pdftotext"],
             ["Data and storage", "pandas, SQLite, PostgreSQL (Supabase)"],
             ["Modelling", "XGBoost, scikit-learn"],
             ["Application and charts", "Streamlit, Plotly, Matplotlib"],
             ["Reports", "ReportLab"],
             ["Assistant", "Groq and Google Gemini language models; BM25 document search"],
             ["Version control", "Git and GitHub"]]
    S += [table(tools, [4.4 * cm, 12.9 * cm], headcol=SKY)]

    S += section("19", "Project links", NAVY)
    links = [["Item", "Location"],
             ["Source code", REPO],
             ["Application (local)", "http://localhost:8501 after running ./run.sh"],
             ["Application (online)", "To be published on Streamlit Community Cloud"],
             ["Handover document", "docs/HANDOVER.md in the repository"],
             ["Staff analytics report", "docs/NIRF_Analytics_Report.pdf in the repository"],
             ["Refresh all data and models", "./pipeline.sh"]]
    S += [table(links, [4.4 * cm, 12.9 * cm], headcol=NAVY)]

    S += section("20", "Glossary", MUTED)
    gl = [["Term", "Meaning"],
          ["NIRF", "National Institutional Ranking Framework, Ministry of Education"],
          ["Band", "A range such as 201-300 used instead of a rank below 100; no score is published"],
          ["Cut-off", "The lowest score inside the top 100 in a given year"],
          ["Filing", "The data form an institution submits to NIRF, published as a PDF"],
          ["Estimate", "A score computed by the platform's model, not by NIRF"],
          ["R²", "Share of variation a model explains; 1.0 is perfect"],
          ["Cross-validation", "Testing a model on institutions it was not trained on"],
          ["Monte Carlo simulation", "Repeating a calculation many times with random variation to obtain a range"],
          ["OpenAlex", "A free, open index of research publications and institutions"]]
    S += [KeepTogether([table(gl, [4.4 * cm, 12.9 * cm], headcol=MUTED)])]

    return S


def build(pages: dict) -> dict:
    found = {}
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm,
                            bottomMargin=1.9 * cm, title="NIRF Analytics & Ranking Intelligence - Proposal and Progress Report",
                            author="R. Nanda Kishore", subject="Saveetha Engineering College")
    doc.afterFlowable = lambda f: found.setdefault(f.key, doc.page) if isinstance(f, Mark) else None
    doc.build(make_story(pages), onFirstPage=cover, onLaterPages=footer)
    return found


pages = build({})
build(pages)

print("wrote", OUT, OUT.stat().st_size // 1024, "KB")
