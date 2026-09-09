"""Parse NIRF per-institute data PDFs (pdftotext -layout output) into structured records.

Each PDF is the data an institute submitted: intake, enrolment/diversity, placements & median
salary, PhD numbers, capital/operational expenditure, IPR, sponsored research, consultancy,
facilities for physically challenged students and the faculty list.

Output: data/processed/submissions.csv (one row per PDF, wide) plus
        data/processed/faculty.csv (one row per faculty member)  and raw text kept for RAG.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "raw" / "pdf"
SEC_DIR = ROOT / "data" / "raw" / "saveetha"
TXT_DIR = ROOT / "data" / "raw" / "pdf_text"
OUT = ROOT / "data" / "processed"

NUM = r"(\d[\d,]*)"


def pdf_text(path: Path) -> str:
    TXT_DIR.mkdir(parents=True, exist_ok=True)
    cache = TXT_DIR / (path.stem + f"_{path.parent.parent.name}_{path.parent.name}.txt"
                       if path.parent.parent.name.isdigit() else path.stem + ".txt")
    if cache.exists():
        return cache.read_text()
    txt = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True).stdout
    cache.write_text(txt)
    return txt


def _i(s: str | None) -> int | None:
    if s is None:
        return None
    s = s.replace(",", "").strip()
    return int(s) if s.isdigit() else None


def section(txt: str, start: str, end_pat: str) -> str:
    m = re.search(start, txt)
    if not m:
        return ""
    rest = txt[m.end():]
    e = re.search(end_pat, rest)
    return rest[: e.start()] if e else rest


def parse_header(txt: str) -> dict:
    m = re.search(r"Institute Name:\s*(.+?)\s*\[(IR-[A-Z]-[A-Z]-\d+)\]", txt)
    y = re.search(r"NIRF\s*'?(\d{4})'?|India Rankings\s*'?(\d{4})'?", txt)
    return {
        "name": m.group(1).strip() if m else None,
        "institute_id": m.group(2) if m else None,
        "year": int(y.group(1) or y.group(2)) if y else None,
    }


def parse_intake(txt: str) -> dict:
    sec = section(txt, r"Sanctioned \(Approved\) Intake", r"Total Actual Student Strength")
    out = {}
    for m in re.finditer(r"^(UG|PG)\s*\[(\d)\s*Years?\s*Program\(s\)\]\s+(.+)$", sec, re.M):
        vals = re.findall(r"(\d+|-)", m.group(3))
        key = f"intake_{m.group(1).lower()}{m.group(2)}y"
        out[key] = _i(vals[0]) if vals and vals[0] != "-" else None
        out[key + "_prev"] = _i(vals[1]) if len(vals) > 1 and vals[1] != "-" else None
    out["intake_total_latest"] = sum(v for k, v in out.items() if k.startswith("intake_") and not k.endswith("_prev") and k != "intake_total_latest" and v) or None
    return out


STRENGTH_COLS = ["male", "female", "total", "within_state", "outside_state", "outside_country",
                 "econ_backward", "socially_challenged", "fee_reimb_govt", "fee_reimb_inst",
                 "fee_reimb_private", "no_fee_reimb"]


def parse_strength(txt: str) -> dict:
    sec = section(txt, r"Total Actual Student Strength", r"Placement & Higher Studies")
    rows = re.findall(r"^(UG|PG)\s*\[(\d)\s*Years?\s+(?:Program\(s\)\]\s+)?((?:\d+\s+){11}\d+)", sec, re.M)
    out = {}
    tot = [0] * 12
    for prog, yrs, nums in rows:
        vals = [int(v) for v in nums.split()]
        for c, v in zip(STRENGTH_COLS, vals):
            out[f"str_{prog.lower()}{yrs}y_{c}"] = v
        tot = [a + b for a, b in zip(tot, vals)]
    for c, v in zip(STRENGTH_COLS, tot):
        out[f"students_{c}"] = v if rows else None
    return out


def parse_placement(txt: str) -> dict:
    sec = section(txt, r"Placement & Higher Studies", r"Ph\.?D Student Details|Ph\.D \(Student")
    out, blocks = {}, {}
    for m in re.finditer(r"^(UG|PG)\s*\[(\d)\s*Years?\s*Program\(s\)\]:\s*Placement", sec, re.M):
        blocks[f"{m.group(1).lower()}{m.group(2)}y"] = m.end()
    keys = list(blocks)
    for i, k in enumerate(keys):
        body = sec[blocks[k]: blocks[keys[i + 1]] if i + 1 < len(keys) else None]
        # row: yr intake admitted [yr lateral] yr graduated placed salary(words) higher
        rows = re.findall(
            r"^(\d{4}-\d{2})\s+(\d+)\s+(\d+)\s+(?:(\d{4}-\d{2})\s+(\d+)\s+)?(\d{4}-\d{2})\s+(\d+)\s+(\d+)\s+(\d+)\s*\([^\n]*?(?:\s(\d+))?\s*$",
            body, re.M)
        if not rows:
            continue
        last = rows[-1]
        g, p, sal, hs = int(last[6]), int(last[7]), int(last[8]), _i(last[9])
        out[f"plc_{k}_grad_year"] = last[5]
        out[f"plc_{k}_graduated"] = g
        out[f"plc_{k}_placed"] = p
        out[f"plc_{k}_median_salary"] = sal
        out[f"plc_{k}_higher_studies"] = hs
        out[f"plc_{k}_admitted"] = int(last[2])
        out[f"plc_{k}_intake"] = int(last[1])
        # 3-year averages
        out[f"plc_{k}_grad_3y_avg"] = round(sum(int(r[6]) for r in rows) / len(rows), 1)
        out[f"plc_{k}_placed_3y_avg"] = round(sum(int(r[7]) for r in rows) / len(rows), 1)
        out[f"plc_{k}_intake_3y_avg"] = round(sum(int(r[1]) for r in rows) / len(rows), 1)
        out[f"plc_{k}_salary_3y_avg"] = round(sum(int(r[8]) for r in rows) / len(rows))
    # aggregates across programmes (latest year)
    grads = [v for k, v in out.items() if k.endswith("_graduated")]
    placed = [v for k, v in out.items() if k.endswith("_placed")]
    hs = [v for k, v in out.items() if k.endswith("_higher_studies") and v]
    intakes = [v for k, v in out.items() if k.endswith("_intake") and not k.endswith("_3y_avg")]
    if grads:
        out["graduated_total"] = sum(grads)
        out["placed_total"] = sum(placed)
        out["higher_studies_total"] = sum(hs)
        out["intake_for_grad_cohort"] = sum(intakes)
        out["placement_rate"] = round(sum(placed) / sum(grads), 4) if sum(grads) else None
        out["placed_or_hs_rate"] = round((sum(placed) + sum(hs)) / sum(grads), 4) if sum(grads) else None
        out["graduation_rate"] = round(sum(grads) / sum(intakes), 4) if sum(intakes) else None
    ug = out.get("plc_ug4y_median_salary")
    out["median_salary_ug"] = ug
    return out


def parse_phd(txt: str) -> dict:
    sec = section(txt, r"Ph\.?D Student Details|Ph\.D \(Student pursuing", r"Financial Resources")
    out = {}
    m = re.search(r"Full Time\s+(\d+)\s*\n.*?Part Time\s+(\d+)", sec, re.S)
    if m:
        out["phd_pursuing_ft"], out["phd_pursuing_pt"] = int(m.group(1)), int(m.group(2))
    g = re.search(r"graduated.*?\n.*?Full Time\s+(\d+)\s+(\d+)\s+(\d+).*?Part Time\s+(\d+)\s+(\d+)\s+(\d+)", sec, re.S)
    if g:
        ft = [int(g.group(i)) for i in (1, 2, 3)]
        pt = [int(g.group(i)) for i in (4, 5, 6)]
        out["phd_grad_ft_latest"], out["phd_grad_pt_latest"] = ft[0], pt[0]
        out["phd_grad_3y_avg"] = round((sum(ft) + sum(pt)) / 3, 1)
    return out


def _amounts(sec: str, label_pat: str) -> list[int]:
    m = re.search(label_pat + r".*?" + NUM + r"\s*\(.*?" + NUM + r"\s*\(.*?" + NUM + r"\s*\(", sec, re.S)
    return [int(m.group(i).replace(",", "")) for i in (1, 2, 3)] if m else []


def parse_finance(txt: str) -> dict:
    cap = section(txt, r"Financial Resources: Utilised Amount for the Capital", r"Financial Resources: Utilised Amount for the Operational")
    ope = section(txt, r"Financial Resources: Utilised Amount for the Operational", r"\nIPR|Sponsored Research Details|PCS Facilities")
    out = {}
    cap_items = {"lib": r"Library", "equip": r"New Equipment", "workshop": r"Engineering Workshops", "other_cap": r"Other expenditure on creation"}
    ope_items = {"salary": r"Salaries", "maint": r"Maintenance of Academic", "seminar": r"Seminars/Conferences"}
    cap_tot, ope_tot = [0, 0, 0], [0, 0, 0]
    for k, pat in cap_items.items():
        v = _amounts(cap, pat)
        if v:
            out[f"capex_{k}_latest"] = v[0]
            cap_tot = [a + b for a, b in zip(cap_tot, v)]
    for k, pat in ope_items.items():
        v = _amounts(ope, pat)
        if v:
            out[f"opex_{k}_latest"] = v[0]
            ope_tot = [a + b for a, b in zip(ope_tot, v)]
    if any(cap_tot):
        out["capex_3y_avg"] = round(sum(cap_tot) / 3)
    if any(ope_tot):
        out["opex_3y_avg"] = round(sum(ope_tot) / 3)
    return out


def parse_research(txt: str) -> dict:
    out = {}
    ipr = section(txt, r"\nIPR\s*\n", r"Sponsored Research Details")
    m = re.search(r"Patents Published\s+(\d+)\s+(\d+)\s+(\d+)", ipr)
    if m:
        out["patents_published_3y"] = sum(int(m.group(i)) for i in (1, 2, 3))
    m = re.search(r"Patents Granted\s+(\d+)\s+(\d+)\s+(\d+)", ipr)
    if m:
        out["patents_granted_3y"] = sum(int(m.group(i)) for i in (1, 2, 3))
    spo = section(txt, r"Sponsored Research Details", r"Consultancy Project Details")
    m = re.search(r"Total no\. of Sponsored Projects\s+(\d+)\s+(\d+)\s+(\d+)", spo)
    if m:
        out["sponsored_projects_3y"] = sum(int(m.group(i)) for i in (1, 2, 3))
    m = re.search(r"Total Amount Received \(Amount in Rupees\)\s+(\d+)\s+(\d+)\s+(\d+)", spo)
    if m:
        out["sponsored_amount_3y_avg"] = round(sum(int(m.group(i)) for i in (1, 2, 3)) / 3)
    con = section(txt, r"Consultancy Project Details", r"Executive Development|PCS Facilities")
    m = re.search(r"Total no\. of Consultancy Projects\s+(\d+)\s+(\d+)\s+(\d+)", con)
    if m:
        out["consultancy_projects_3y"] = sum(int(m.group(i)) for i in (1, 2, 3))
    m = re.search(r"Total Amount Received \(Amount in Rupees\)\s+(\d+)\s+(\d+)\s+(\d+)", con)
    if m:
        out["consultancy_amount_3y_avg"] = round(sum(int(m.group(i)) for i in (1, 2, 3)) / 3)
    edp = section(txt, r"Executive Development Program", r"PCS Facilities")
    m = re.search(r"Total Annual Earnings.*?\s+(\d+)\s+(\d+)\s+(\d+)", edp, re.S)
    if m:
        out["edp_earnings_3y_avg"] = round(sum(int(m.group(i)) for i in (1, 2, 3)) / 3)
    return out


def parse_pcs(txt: str) -> dict:
    sec = section(txt, r"PCS Facilities", r"Faculty Details")
    score = 0
    for q in ("Lifts/Ramps", "walking aids", "specially designed toilets"):
        m = re.search(q + r".*?(Yes[^\n]*|No[^\n]*)", sec, re.S | re.I)
        if m:
            a = m.group(1).lower()
            score += 1.0 if ("more than 80" in a or a.strip().startswith("yes") and "%" not in a) else 0.5 if "yes" in a else 0
    return {"pcs_score_0_3": score if sec else None}


FAC_RE = re.compile(
    r"^\s*(\d+)\s+(.+?)\s+(\d{2})\s+"
    r"(Professor|Associate Professor|Assistant Professor|Dean / Principal / Director / Vice Chancellor|Dean|Principal|Director|Lecturer|Reader|Other|Vice Chancellor|Emeritus Professor|Adjunct Professor|Professor of Practice)\s+"
    r"(Male|Female|Transgender)\s+(\S+)\s+(\d+)\s+(Yes|No)\s+(\S+)\s+(\S+)\s+(Regular|Adhoc\s*/\s*Contractual|Visiting|Contractual|Other)\s*$",
    re.M)


def parse_faculty(txt: str, meta: dict) -> tuple[dict, list[dict]]:
    sec = section(txt, r"Faculty Details", r"\Z")
    out = {}
    m = re.search(r"Number of faculty members entered\s+(\d+)", sec)
    if m:
        out["faculty_entered"] = int(m.group(1))
    rows = []
    for g in FAC_RE.finditer(sec):
        exp_m = int(g.group(7))
        rows.append({
            **{k: meta[k] for k in ("year", "institute_id", "category")},
            "srno": int(g.group(1)), "name": g.group(2).strip(), "age": int(g.group(3)),
            "designation": g.group(4), "gender": g.group(5), "qualification": g.group(6),
            "experience_months": exp_m, "currently_working": g.group(8) == "Yes",
            "joining_date": g.group(9), "association": g.group(11),
        })
    if rows:
        df = pd.DataFrame(rows)
        n = len(df)
        yrs = df.experience_months / 12
        out.update({
            "faculty_parsed": n,
            "faculty_phd_pct": round(100 * df.qualification.str.contains(r"Ph\.?D", case=False).mean(), 1),
            "faculty_female_pct": round(100 * (df.gender == "Female").mean(), 1),
            "faculty_regular_pct": round(100 * (df.association == "Regular").mean(), 1),
            "faculty_exp_le8_frac": round((yrs <= 8).mean(), 3),
            "faculty_exp_8_15_frac": round(((yrs > 8) & (yrs <= 15)).mean(), 3),
            "faculty_exp_gt15_frac": round((yrs > 15).mean(), 3),
            "faculty_professor_pct": round(100 * (df.designation == "Professor").mean(), 1),
            "faculty_avg_age": round(df.age.mean(), 1),
        })
    return out, rows


def parse_pdf(path: Path, category: str | None = None) -> tuple[dict, list[dict]]:
    txt = pdf_text(path)
    rec = parse_header(txt)
    rec["category"] = category or {"E": "Engineering", "O": "Overall", "C": "College", "I": "Innovation", "B": "SDG", "U": "University"}.get(
        (rec["institute_id"] or "IR-X")[3], "Unknown")
    rec["source_pdf"] = str(path.resolve().relative_to(ROOT))
    for fn in (parse_intake, parse_strength, parse_placement, parse_phd, parse_finance, parse_research, parse_pcs):
        try:
            rec.update(fn(txt))
        except Exception as e:  # keep going, log
            rec[f"err_{fn.__name__}"] = str(e)[:80]
    fac, rows = parse_faculty(txt, rec)
    rec.update(fac)
    # derived ratios NIRF actually uses
    n_students = (rec.get("students_total") or 0) + (rec.get("phd_pursuing_ft") or 0)
    f = rec.get("faculty_parsed") or rec.get("faculty_entered")
    if n_students and f:
        rec["students_per_faculty"] = round(n_students / f, 2)
    if rec.get("students_total"):
        rec["women_students_pct"] = round(100 * rec["students_female"] / rec["students_total"], 1)
        rec["outside_state_pct"] = round(100 * rec["students_outside_state"] / rec["students_total"], 1)
        rec["outside_country_pct"] = round(100 * rec["students_outside_country"] / rec["students_total"], 2)
        rec["full_fee_reimb_pct"] = round(100 * (rec["students_fee_reimb_govt"] + rec["students_fee_reimb_inst"] + rec["students_fee_reimb_private"]) / rec["students_total"], 1)
        if rec.get("capex_3y_avg"):
            rec["capex_per_student"] = round(rec["capex_3y_avg"] / rec["students_total"])
        if rec.get("opex_3y_avg"):
            rec["opex_per_student"] = round(rec["opex_3y_avg"] / rec["students_total"])
    return rec, rows


def main(paths: list[Path]) -> None:
    recs, fac = [], []
    for p in paths:
        cat = p.parent.name if p.parent.parent.name.isdigit() else None
        r, rows = parse_pdf(p, cat)
        recs.append(r)
        fac += rows
    OUT.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(recs)
    df.to_csv(OUT / "submissions.csv", index=False)
    pd.DataFrame(fac).to_csv(OUT / "faculty.csv", index=False)
    print(f"parsed {len(df)} PDFs, {len(fac)} faculty rows")
    key = ["students_total", "placement_rate", "median_salary_ug", "phd_grad_3y_avg", "capex_3y_avg", "opex_3y_avg", "faculty_parsed", "faculty_phd_pct"]
    print("field coverage (% non-null):")
    print((df[[k for k in key if k in df]].notna().mean() * 100).round(1).to_string())


if __name__ == "__main__":
    files = sorted(PDF_DIR.rglob("*.pdf")) + sorted(SEC_DIR.glob("*.pdf"))
    if len(sys.argv) > 1:
        files = [Path(a) for a in sys.argv[1:]]
    main(files)
