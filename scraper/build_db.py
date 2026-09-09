"""Build the SQLite database (db/nirf.db) from the processed CSVs, methodology text and
Saveetha documents. Re-runnable: drops and recreates every table it owns.

Tables
  institutions      canonical id -> name/city/state/type (U=university, I=institute of national
                    importance/deemed, C=college) with a name key for cross-year matching
  rankings          published scores: year, category, institute, TLR/RPC/GO/OI/PR, score, rank
  rank_bands        institutes placed in rank bands (no scores published)
  participants      every institution that applied, per year & category
  submissions       raw data parsed from per-institute PDFs (wide)
  faculty           faculty rows where the PDF included the list (Saveetha)
  methodology       parameter / sub-parameter marks and weights per year & category
  documents         full text of every PDF (institute data, methodology, Saveetha) for RAG
  saveetha_live     live data entered by college staff through the app
  predictions       model outputs (filled by models/predict_2026.py)
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "db" / "nirf.db"
P = ROOT / "data" / "processed"
SEC_ID = "IR-E-C-16590"
SEC_NAME = "Saveetha Engineering College"


def name_key(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", str(s)).lower()
    s = s.replace("&", "and")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"\b(the|of|and)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_rankings() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    r = pd.read_csv(P / "rankings.csv")
    b = pd.read_csv(P / "rank_bands.csv")
    p = pd.read_csv(P / "participants.csv")
    # 2016 pages on nirfindia.org serve the 2017 tables (identical content) -> drop
    r, b, p = r[r.year != 2016], b[b.year != 2016], p[p.year != 2016]
    # when a year/category has numeric ranks to 200, the "101-150"/"151-200" band pages hold 201-250/251-300
    max_rank = r.groupby(["year", "category"])["rank"].max()
    def relabel(row):
        mr = max_rank.get((row.year, row.category), 100)
        if mr >= 200:
            return {"101-150": "201-250", "151-200": "251-300"}.get(row.band, row.band)
        return row.band
    b = b.copy()
    b["band"] = b.apply(relabel, axis=1)
    b["band_low"] = b.band.str.split("-").str[0].astype(int)
    b["band_high"] = b.band.str.split("-").str[1].astype(int)
    for df in (r, b, p):
        df["name_key"] = df["name"].map(name_key)
    return r, b, p


def build_institutions(r: pd.DataFrame, b: pd.DataFrame, s: pd.DataFrame) -> pd.DataFrame:
    latest = r.sort_values("year").groupby("institute_id").last().reset_index()
    inst = latest[["institute_id", "name", "city", "state", "name_key"]].copy()
    inst["inst_type"] = inst.institute_id.str[5]
    inst["type_label"] = inst.inst_type.map({"U": "University", "I": "Institute (deemed / national importance)", "C": "College"})
    inst["is_saveetha_engineering"] = inst.institute_id.eq(SEC_ID)
    # Saveetha Engineering College only appears with an ID in its own PDFs
    if SEC_ID not in set(inst.institute_id):
        inst = pd.concat([inst, pd.DataFrame([{
            "institute_id": SEC_ID, "name": SEC_NAME, "city": "Sriperumbudur", "state": "Tamil Nadu",
            "name_key": name_key(SEC_NAME), "inst_type": "C", "type_label": "College", "is_saveetha_engineering": True}])])
    return inst.reset_index(drop=True)


def load_methodology() -> pd.DataFrame:
    """Marks per sub-parameter, parsed from the yearly framework text (summary table)."""
    rows = []
    for txt_file in sorted((ROOT / "data" / "raw" / "methodology").glob("*.txt")):
        year, cat = txt_file.stem.split("_")
        txt = txt_file.read_text()
        m = re.search(r"Summary of Ranking Parameters.*?(?=\n\s*1\. Teaching|\Z)", txt, re.S)
        block = m.group(0) if m else txt[:6000]
        weights = dict(re.findall(r"(Teaching, Learning & Resources|Research and Professional Practice|Graduation Outcomes|Outreach and Inclusivity|Perception)\s+100\s+(0\.\d+)", block))
        code = {"Teaching, Learning & Resources": "TLR", "Research and Professional Practice": "RPC", "Graduation Outcomes": "GO", "Outreach and Inclusivity": "OI", "Perception": "PR"}
        current = None
        for line in block.splitlines():
            h = re.search(r"(Teaching, Learning & Resources|Research and Professional Practice|Graduation Outcomes|Outreach and Inclusivity|Perception)\s*\((TLR|RP|GO|OI|PR)\)", line)
            if h:
                current = code[h.group(1)]
                continue
            sm = re.search(r"^\s*[A-F]\.\s+(.+?)\s*\(([A-Za-z]+)\)\s*:\s*(\d+)\s*marks", line, re.I)
            if sm and current:
                rows.append({"year": int(year), "category": cat, "parameter": current,
                             "parameter_weight": float(weights.get({v: k for k, v in code.items()}[current], "nan")),
                             "sub_parameter": sm.group(1).strip(), "sub_code": sm.group(2), "marks": int(sm.group(3))})
        # sub-parameters whose "(CODE): N marks" wrapped onto the next line
        joined = re.sub(r"\n\s+", " ", block)
        for h in re.finditer(r"([A-F])\.\s+(.+?)\s*\(([A-Za-z]+)\)\s*:\s*(\d+)\s*marks", joined):
            if not any(x["sub_code"] == h.group(3) and x["year"] == int(year) and x["category"] == cat for x in rows):
                # find which parameter block it belongs to by position
                pos = h.start()
                heads = [(mm.start(), code[mm.group(1)]) for mm in re.finditer(r"(Teaching, Learning & Resources|Research and Professional Practice|Graduation Outcomes|Outreach and Inclusivity|Perception)\s*\((TLR|RP|GO|OI|PR)\)", joined)]
                par = max([hh for hh in heads if hh[0] < pos], default=(0, None))[1]
                if par:
                    rows.append({"year": int(year), "category": cat, "parameter": par,
                                 "parameter_weight": float(weights.get({v: k for k, v in code.items()}[par], "nan")),
                                 "sub_parameter": h.group(2).strip(), "sub_code": h.group(3), "marks": int(h.group(4))})
    return pd.DataFrame(rows).drop_duplicates(["year", "category", "sub_code"])


def load_documents() -> pd.DataFrame:
    docs = []
    for f in sorted((ROOT / "data" / "raw" / "methodology").glob("*.txt")):
        y, c = f.stem.split("_")
        docs.append({"doc_id": f"methodology_{f.stem}", "doc_type": "methodology", "year": int(y), "category": c,
                     "institute_id": None, "title": f"NIRF {y} ranking methodology: {c}", "text": f.read_text()})
    for f in sorted((ROOT / "data" / "raw" / "pdf_text").glob("*.txt")):
        txt = f.read_text()
        m = re.search(r"Institute Name:\s*(.+?)\s*\[(IR-[A-Z]-[A-Z]-\d+)\]", txt)
        y = re.search(r"NIRF\s*'?(\d{4})'?|India Rankings\s*'?(\d{4})'?", txt)
        year = int(y.group(1) or y.group(2)) if y else None
        parts = f.stem.split("_")
        cat = parts[-1] if len(parts) >= 3 and parts[-2].isdigit() else None
        inst = m.group(2) if m else None
        if inst and inst.startswith("IR-E-C-16590"):
            cat = {"E": "Engineering", "I": "Innovation", "B": "SDG"}[inst[3]]
        elif not cat and inst:
            cat = {"E": "Engineering", "O": "Overall", "C": "College", "U": "University", "I": "Innovation", "B": "SDG"}.get(inst[3])
        name = m.group(1).strip() if m else f.stem
        docs.append({"doc_id": f"submission_{f.stem}", "doc_type": "institute_submission", "year": year, "category": cat,
                     "institute_id": inst, "title": f"{name} — NIRF {year} {cat} submitted data", "text": txt})
    return pd.DataFrame(docs)


def main() -> None:
    r, b, p = load_rankings()
    s = pd.read_csv(P / "submissions.csv")
    s = s.loc[:, ~s.columns.str.startswith("err_")]
    fac = pd.read_csv(P / "faculty.csv")
    inst = build_institutions(r, b, s)
    meth = load_methodology()
    docs = load_documents()
    # link band rows to institute ids via name_key (bands have no IDs)
    key_to_id = inst.drop_duplicates("name_key").set_index("name_key")["institute_id"]
    b["institute_id"] = b.name_key.map(key_to_id)
    p["institute_id"] = p.name_key.map(key_to_id)

    DB.parent.mkdir(exist_ok=True)
    con = sqlite3.connect(DB)
    for t in ("institutions", "rankings", "rank_bands", "participants", "submissions", "faculty", "methodology", "documents"):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    inst.to_sql("institutions", con, index=False)
    r.drop(columns=["graph_url"]).to_sql("rankings", con, index=False)
    b.to_sql("rank_bands", con, index=False)
    p.to_sql("participants", con, index=False)
    s.to_sql("submissions", con, index=False)
    fac.to_sql("faculty", con, index=False)
    meth.to_sql("methodology", con, index=False)
    docs.to_sql("documents", con, index=False)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS saveetha_live (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entered_at TEXT DEFAULT (datetime('now')),
        entered_by TEXT,
        academic_year TEXT,
        metric TEXT NOT NULL,
        value REAL NOT NULL,
        note TEXT
    );
    CREATE TABLE IF NOT EXISTS predictions (
        run_at TEXT, model TEXT, target_year INTEGER, institute_id TEXT, name TEXT,
        pred_tlr REAL, pred_rpc REAL, pred_go REAL, pred_oi REAL, pred_pr REAL,
        pred_score REAL, pred_rank REAL, pred_band TEXT, score_low REAL, score_high REAL, notes TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_rank ON rankings(year, category, rank);
    CREATE INDEX IF NOT EXISTS ix_rank_inst ON rankings(institute_id);
    CREATE INDEX IF NOT EXISTS ix_sub ON submissions(year, institute_id);
    CREATE VIEW IF NOT EXISTS v_engineering_top100 AS
        SELECT r.year, r.rank, r.institute_id, r.name, r.city, r.state, i.type_label,
               r.tlr, r.rpc, r."go", r.oi, r.pr, r.score
        FROM rankings r LEFT JOIN institutions i USING(institute_id)
        WHERE r.category='Engineering' AND r.rank<=100;
    CREATE VIEW IF NOT EXISTS v_saveetha_history AS
        SELECT year, 'Engineering' AS category, 'ranked' AS status, rank AS rank_or_band_low, rank AS rank_or_band_high, score, tlr, rpc, "go", oi, pr
          FROM rankings WHERE category='Engineering' AND name_key LIKE 'saveetha engineering%'
        UNION ALL
        SELECT year, category, 'band', band_low, band_high, NULL, NULL, NULL, NULL, NULL, NULL
          FROM rank_bands WHERE name_key LIKE 'saveetha engineering%'
        ORDER BY year;
    """)
    con.commit()
    for t in ("institutions", "rankings", "rank_bands", "participants", "submissions", "faculty", "methodology", "documents"):
        print(f"{t:14s} {con.execute(f'select count(*) from {t}').fetchone()[0]:>7} rows")
    print("\nSaveetha Engineering College history:")
    print(pd.read_sql("select * from v_saveetha_history", con).to_string(index=False))
    print("\nmethodology rows per year/category:")
    print(meth.groupby(["year", "category"]).size().to_string())
    con.close()
    print(f"\nDB -> {DB}")


if __name__ == "__main__":
    main()
