"""AI analyst over the NIRF database (RAG + tools), on free providers.

Order: Groq openai/gpt-oss-120b -> Groq qwen/qwen3.8-27b -> Google Gemini gemini-3.1-flash-lite (all free tiers, no card).
Override with GROQ_MODEL / GEMINI_MODEL in .env if a model is retired.
Both are used through their OpenAI-compatible endpoints, so one code path serves both.

Tools the model can call:
  query_database       read-only SQL over db/nirf.db (rankings, submissions, methodology, live data…)
  search_documents     BM25 search over methodology PDFs, institute submissions and analysis JSON
  fetch_web_page       fetch & extract text from a public URL (nirfindia.org, saveetha.ac.in, news)
  get_saveetha_status  compact summary of Saveetha's history, estimates, 2026 prediction, live data
Credentials: GROQ_API_KEY and/or GEMINI_API_KEY in the environment or in <project>/.env
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Callable

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from openai import APIStatusError, OpenAI, RateLimitError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
DB = ROOT / "db" / "nirf.db"
SEC_ID = "IR-E-C-16590"

PROVIDERS = {
    "groq": {"env": "GROQ_API_KEY", "base_url": "https://api.groq.com/openai/v1",
             "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")},
    "groq-backup": {"env": "GROQ_API_KEY", "base_url": "https://api.groq.com/openai/v1",
                    "model": os.getenv("GROQ_BACKUP_MODEL", "qwen/qwen3.8-27b")},
    "gemini": {"env": "GEMINI_API_KEY", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "model": os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")},
}

SYSTEM = """You are the NIRF analytics assistant for Saveetha Engineering College (Sriperumbudur, Tamil Nadu,
NIRF id IR-E-C-16590). You help the college's staff understand India's NIRF rankings (Engineering category
above all), where the college stands, and what it must change to reach the top 100.

You have a SQLite database with: rankings (2017-2025, all categories, TLR/RPC/GO/OI/PR scores, ranks 1-100 and
1-200 for 2019-22), rank_bands (101-300 bands), participants, submissions (raw data parsed from each institute's
NIRF PDF: intake, enrolment, placements, median salary, PhDs, expenditure, research funding), faculty (Saveetha's
faculty list), methodology (sub-parameter marks per year), documents (full text), saveetha_live (staff-entered
live metrics), predictions (2026 forecasts). Also analysis.json / prediction_2026.json / model_report.json.

Important facts to keep straight:
- "Saveetha Engineering College" (IR-E-C-16590, a college in Sriperumbudur) is NOT "Saveetha Institute of
  Medical and Technical Sciences" (IR-E-I-1441, a deemed university in Chennai ranked ~45). Never mix them up.
- Saveetha Engineering College: rank 91 (2017), band 101-150 (2018), rank 124 (2019), band 201-250 (2020),
  unranked 2021-2023, band 201-300 (2024, 2025). NIRF publishes no scores for band placements; its
  TLR/RPC/GO/OI estimates come from our calibrated model, so say "estimated".
- The five parameters and their official names: TLR = Teaching, Learning & Resources; RPC (NIRF also writes RP) =
  Research and Professional Practice; GO = Graduation Outcomes; OI = Outreach and Inclusivity; PR = Perception.
  Engineering weights: TLR 0.30, RPC 0.30, GO 0.20, OI 0.10, PR 0.10. Total = weighted sum, max 100.
- The rank-100 cut-off rose from 41.93 (2023) to 43.95 (2024) to 45.55 (2025); forecast ~47 for 2026.

How to work: ALWAYS use the tools before answering with numbers; never guess figures. Use query_database for
anything numeric (SQLite syntax; the column go must be written as "go"), search_documents for methodology/formula
questions and for an institute's raw submission, fetch_web_page when asked about live or external information
(nirfindia.org pages, news), get_saveetha_status for anything about the college's position or prediction.
Quote figures with their year. Be concise, use small markdown tables when listing institutes, and end with a
practical takeaway for the college when relevant. Mention uncertainty honestly (model estimates, unknown
Perception score). Answer in the user's language."""

TOOLS = [
    {"type": "function", "function": {
        "name": "query_database",
        "description": "Run a read-only SQL (SQLite) query against the NIRF database; returns rows as JSON (max 200). Tables: rankings(year, category, institute_id, name, city, state, tlr, rpc, \"go\", oi, pr, score, rank), rank_bands(year, category, band, band_low, band_high, name, city, state, institute_id), participants(year, category, name, city, state), institutions(institute_id, name, city, state, inst_type, type_label), submissions(year, institute_id, name, category, students_total, students_female, students_outside_state, faculty_entered, students_per_faculty, phd_pursuing_ft, phd_grad_3y_avg, graduated_total, placed_total, higher_studies_total, placement_rate, placed_or_hs_rate, graduation_rate, median_salary_ug, capex_per_student, opex_per_student, sponsored_projects_3y, sponsored_amount_3y_avg, consultancy_amount_3y_avg, patents_published_3y, patents_granted_3y, women_students_pct, outside_state_pct, full_fee_reimb_pct, pcs_score_0_3), faculty(year, institute_id, name, designation, gender, qualification, experience_months), methodology(year, category, parameter, parameter_weight, sub_parameter, sub_code, marks), saveetha_live(entered_at, entered_by, academic_year, metric, value, note), predictions(model, target_year, institute_id, name, pred_score, pred_rank, pred_band, score_low, score_high, notes); views v_engineering_top100, v_saveetha_history. Categories: Engineering, Overall, College, University.",
        "parameters": {"type": "object", "properties": {"sql": {"type": "string", "description": "A single SELECT statement with a LIMIT."}}, "required": ["sql"]}}},
    {"type": "function", "function": {
        "name": "search_documents",
        "description": "Full-text search over NIRF methodology documents (formulas, sub-parameters, weights per year), every institute's submitted-data PDF text, Saveetha's filings, and the analysis/prediction JSON. Use for 'how is X computed', 'what did institute Y submit', formula and definition questions.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"},
                                                        "doc_type": {"type": "string", "enum": ["methodology", "institute_submission", "analysis", "any"], "description": "Restrict to a document type (default any)."},
                                                        "year": {"type": "integer", "description": "Restrict to a ranking year; 0 = any."},
                                                        "k": {"type": "integer", "description": "Number of chunks to return (default 6)."}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "fetch_web_page",
        "description": "Fetch a public web page (or PDF) and return its readable text (max ~12k chars). Use for live checks: nirfindia.org ranking pages (e.g. https://www.nirfindia.org/Rankings/2026/EngineeringRanking.html), saveetha.ac.in NIRF page, news.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "get_saveetha_status",
        "description": "Compact JSON summary of Saveetha Engineering College: NIRF history, estimated parameter scores from its filings, the 2026 prediction with band probabilities, what-if levers, and any live metrics staff have entered.",
        "parameters": {"type": "object", "properties": {}}}},
]


# ---------- tool implementations ----------
def query_database(sql: str) -> str:
    s = sql.strip().rstrip(";")
    if not re.match(r"^(select|with)\b", s, re.I) or re.search(r"\b(insert|update|delete|drop|alter|create|attach|pragma)\b", s, re.I):
        return json.dumps({"error": "only read-only SELECT queries are allowed"})
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        cur = con.execute(s)
        cols = [c[0] for c in cur.description]
        rows = cur.fetchmany(200)
        return json.dumps({"columns": cols, "rows": rows, "truncated": len(rows) == 200}, default=str)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": str(e)})
    finally:
        con.close()


def search_documents(query: str, doc_type: str = "any", year: int = 0, k: int = 6) -> str:
    from app.rag.index import search
    hits = search(query, k=k or 6, doc_type=None if doc_type in ("any", "", None) else doc_type, year=year or None)
    return json.dumps([{"title": h["title"], "doc_type": h["doc_type"], "year": h["year"], "institute_id": h["institute_id"], "text": h["text"][:1800]} for h in hits])


def fetch_web_page(url: str) -> str:
    if not re.match(r"^https?://", url):
        return json.dumps({"error": "url must start with http(s)://"})
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 NIRF-analytics"}, timeout=40)
        r.raise_for_status()
    except requests.RequestException as e:
        return json.dumps({"error": str(e)})
    if "pdf" in r.headers.get("content-type", "") or url.lower().endswith(".pdf"):
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(r.content)
        txt = subprocess.run(["pdftotext", "-layout", f.name, "-"], capture_output=True, text=True).stdout
        return json.dumps({"url": url, "text": re.sub(r"\n{3,}", "\n\n", txt)[:12000]})
    soup = BeautifulSoup(r.text, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))
    return json.dumps({"url": url, "status": r.status_code, "title": soup.title.get_text(strip=True) if soup.title else "", "text": text[:12000]})


def get_saveetha_status() -> str:
    out = {}
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out["history"] = [dict(zip(["year", "category", "status", "low", "high", "score", "tlr", "rpc", "go", "oi", "pr"], r)) for r in con.execute("SELECT * FROM v_saveetha_history")]
    out["live_metrics"] = [dict(zip(["metric", "value", "academic_year", "entered_at", "entered_by", "note"], r)) for r in con.execute(
        "SELECT metric, value, academic_year, entered_at, entered_by, note FROM saveetha_live WHERE id IN (SELECT MAX(id) FROM saveetha_live GROUP BY metric)")]
    con.close()
    for name, keys in (("prediction_2026.json", ["thresholds", "saveetha", "what_if_levers", "top100_model_validation"]),
                       ("model_report.json", ["params", "saveetha_estimates", "total_score_fit"]),
                       ("analysis.json", ["saveetha_gap_vs_rank90_100_avg", "saveetha_weighted_gap_by_param", "saveetha_gap_total_vs_2025_cutoff", "cutoffs"])):
        p = ROOT / "data" / "processed" / name
        if p.exists():
            d = json.loads(p.read_text())
            out[name] = {k: d.get(k) for k in keys}
    return json.dumps(out, default=str)


TOOL_FNS: dict[str, Callable[..., str]] = {
    "query_database": query_database, "search_documents": search_documents,
    "fetch_web_page": fetch_web_page, "get_saveetha_status": get_saveetha_status,
}


# ---------- providers ----------
def available_providers() -> list[str]:
    return [p for p, cfg in PROVIDERS.items() if os.getenv(cfg["env"])]


def has_credentials() -> bool:
    return bool(available_providers())


def provider_label() -> str:
    return " → ".join(f"{p} ({PROVIDERS[p]['model']})" for p in available_providers()) or "none"


def _client(provider: str) -> OpenAI:
    cfg = PROVIDERS[provider]
    return OpenAI(api_key=os.getenv(cfg["env"]), base_url=cfg["base_url"], timeout=90, max_retries=1)


def _complete(provider: str, messages: list[dict]):
    return _client(provider).chat.completions.create(
        model=PROVIDERS[provider]["model"], messages=messages, tools=TOOLS, tool_choice="auto", temperature=0.2, max_tokens=4000,
    )


def run_turn(messages: list[dict], on_tool: Callable[[str, dict, str], None] | None = None, max_steps: int = 10) -> tuple[str, list[dict]]:
    """Run one user turn with the tool loop. `messages` excludes the system prompt. Returns (answer, messages).
    Tries Groq first; on rate-limit / server error falls back to Gemini (and vice-versa) for the whole turn."""
    order = available_providers()
    if not order:
        return "No API key configured. Put GROQ_API_KEY (and optionally GEMINI_API_KEY) in the .env file.", messages
    errors = []
    for provider in order:
        work = list(messages)
        seen: set[tuple[str, str]] = set()
        try:
            for _ in range(max_steps):
                resp = _complete(provider, [{"role": "system", "content": SYSTEM}] + work)
                msg = resp.choices[0].message
                calls = msg.tool_calls or []
                work.append({"role": "assistant", "content": msg.content or "", **({"tool_calls": [c.model_dump() for c in calls]} if calls else {})})
                if not calls:
                    return (msg.content or "").strip(), work
                for c in calls:
                    try:
                        args = json.loads(c.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    key = (c.function.name, json.dumps(args, sort_keys=True))
                    if key in seen:
                        out = json.dumps({"note": "You already ran this exact call; use its earlier result and answer now."})
                    else:
                        seen.add(key)
                        try:
                            out = TOOL_FNS[c.function.name](**args)
                        except Exception as e:  # noqa: BLE001
                            out = json.dumps({"error": str(e)})
                    if on_tool:
                        on_tool(c.function.name, args, out)
                    work.append({"role": "tool", "tool_call_id": c.id, "name": c.function.name, "content": out[:40000]})
            return "Stopped after too many tool steps; please narrow the question.", work
        except (RateLimitError, APIStatusError) as e:
            errors.append(f"{provider}: HTTP {getattr(e, 'status_code', '')} {str(e)[:160]}")
            continue
    return "All providers failed. " + " | ".join(errors) + " — try again in a minute.", messages


if __name__ == "__main__":
    print("providers:", provider_label())
    q = " ".join(sys.argv[1:]) or "Which Tamil Nadu colleges (not universities) are in the 2025 Engineering top 100, with scores?"
    ans, _ = run_turn([{"role": "user", "content": q}], on_tool=lambda n, a, o: print(f"  [tool] {n} {json.dumps(a)[:120]} -> {o[:100]}"))
    print("\n" + ans)
