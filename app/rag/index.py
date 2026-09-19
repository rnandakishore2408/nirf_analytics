"""Lightweight retrieval index over everything in the database's `documents` table
(methodology PDFs, 700+ institute submissions, Saveetha filings) plus the analysis/prediction
JSON. BM25 over ~600-token chunks; no external services needed.
"""
from __future__ import annotations

import json
import pickle  # nosec B403 - only for the index this module builds itself (git-ignored cache)
import re
import sqlite3
from pathlib import Path

from rank_bm25 import BM25Okapi

ROOT = Path(__file__).resolve().parents[1].parent
DB = ROOT / "db" / "nirf.db"
CACHE = ROOT / "app" / "rag" / "bm25_index.pkl"
CHUNK_WORDS = 350


def _tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower())


def _chunks(text: str, meta: dict) -> list[dict]:
    words = re.sub(r"[ \t]+", " ", text).split()
    out = []
    for i in range(0, max(len(words), 1), CHUNK_WORDS):
        piece = " ".join(words[i: i + CHUNK_WORDS])
        if piece.strip():
            out.append({**meta, "chunk": i // CHUNK_WORDS, "text": piece})
    return out


def build(force: bool = False) -> dict:
    if CACHE.exists() and not force:
        with open(CACHE, "rb") as f:
            return pickle.load(f)  # nosec B301 - self-generated file, never user-supplied
    con = sqlite3.connect(DB)
    docs = []
    for doc_id, doc_type, year, cat, inst, title, text in con.execute(
            "SELECT doc_id, doc_type, year, category, institute_id, title, text FROM documents"):
        # institute submissions: keep the informative first part (numbers), skip long faculty lists
        if doc_type == "institute_submission":
            text = text.split("Faculty Details")[0]
        docs += _chunks(text, {"doc_id": doc_id, "doc_type": doc_type, "year": year, "category": cat, "institute_id": inst, "title": title})
    for name in ("analysis.json", "prediction_2026.json", "model_report.json"):
        p = ROOT / "data" / "processed" / name
        if p.exists():
            docs += _chunks(json.dumps(json.loads(p.read_text()), indent=0), {"doc_id": name, "doc_type": "analysis", "year": 2026, "category": "Engineering", "institute_id": None, "title": name})
    con.close()
    bm25 = BM25Okapi([_tok(d["text"]) for d in docs])
    idx = {"docs": docs, "bm25": bm25}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(idx, f)
    return idx


def search(query: str, k: int = 6, doc_type: str | None = None, year: int | None = None, idx: dict | None = None) -> list[dict]:
    idx = idx or build()
    scores = idx["bm25"].get_scores(_tok(query))
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    out = []
    for i in order:
        d = idx["docs"][i]
        if doc_type and d["doc_type"] != doc_type:
            continue
        if year and d["year"] != year:
            continue
        out.append({**d, "score": round(float(scores[i]), 2)})
        if len(out) >= k:
            break
    return out


if __name__ == "__main__":
    ix = build(force=True)
    print(f"indexed {len(ix['docs'])} chunks")
    for r in search("how is graduation outcome GO calculated median salary", 3):
        print(r["title"], r["score"], r["text"][:120])
