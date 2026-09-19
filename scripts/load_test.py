"""Stress test a running copy of the app the way browsers use it.

Each simulated user opens the Streamlit websocket, loads the sign-in page, signs in through the real
form, then opens the heaviest pages one after another. All users run at the same time. The script
reports sign-in and page timings (median / 95th percentile / worst) and every failure.

  python scripts/load_test.py --url http://localhost:8501 --users 30 --username <u> --password <p>

Use a dedicated test account: every simulated sign-in is recorded in the sign-in log.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from collections import defaultdict
from urllib.parse import urlsplit

import websockets
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

PAGES = ["", "prediction", "live-data", "what-if", "explorer", "position"]


class Session:
    def __init__(self, ws):
        self.ws = ws
        self.pages: dict[str, str] = {}

    async def run(self, page_hash: str = "", widgets: list[dict] | None = None, timeout: float = 120) -> dict:
        """Ask for a script run and read until it finishes. Returns what the page drew."""
        msg = BackMsg()
        cs = msg.rerun_script
        cs.query_string = ""
        cs.page_script_hash = page_hash
        for w in widgets or []:
            ws_ = cs.widget_states.widgets.add()
            ws_.id = w["id"]
            if "string" in w:
                ws_.string_value = w["string"]
            if w.get("trigger"):
                ws_.trigger_value = True
        await self.ws.send(msg.SerializeToString())
        seen = {"headings": [], "inputs": {}, "buttons": {}, "exceptions": [], "errors": []}
        deadline = time.monotonic() + timeout
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=max(1, deadline - time.monotonic()))
            fm = ForwardMsg()
            fm.ParseFromString(raw)
            kind = fm.WhichOneof("type")
            if kind == "navigation":
                self.pages = {p.url_pathname: p.page_script_hash for p in fm.navigation.app_pages}
            elif kind == "delta" and fm.delta.WhichOneof("type") == "new_element":
                el = fm.delta.new_element
                t = el.WhichOneof("type")
                if t == "heading":
                    seen["headings"].append(el.heading.body)
                elif t == "text_input":
                    seen["inputs"][el.text_input.label] = el.text_input.id
                elif t == "button":
                    seen["buttons"][el.button.label] = el.button.id
                elif t == "exception":
                    seen["exceptions"].append(el.exception.message[:200])
                elif t == "alert" and el.alert.format == 1:  # ERROR
                    seen["errors"].append(el.alert.body[:200])
            elif kind == "script_finished":
                # 0 = finished successfully, 2 = finished early because st.rerun() started a new run
                if fm.script_finished == ForwardMsg.FINISHED_EARLY_FOR_RERUN:
                    seen = {"headings": [], "inputs": {}, "buttons": {}, "exceptions": [], "errors": []}
                    continue
                seen["status"] = fm.script_finished
                return seen


async def one_user(i: int, args, stats: dict, failures: list) -> None:
    u = urlsplit(args.url)
    ws_url = f"{'wss' if u.scheme == 'https' else 'ws'}://{u.netloc}/_stcore/stream"
    await asyncio.sleep(i * args.ramp)  # stagger arrivals
    try:
        async with websockets.connect(ws_url, subprotocols=["streamlit"], origin=f"{u.scheme}://{u.netloc}",
                                      max_size=None, open_timeout=60) as ws:
            s = Session(ws)
            t = time.perf_counter()
            first = await s.run()
            stats["sign-in page"].append(time.perf_counter() - t)
            if "Username" not in first["inputs"] or "Sign in" not in first["buttons"]:
                failures.append((i, "sign-in form not shown", first["headings"], first["exceptions"]))
                return
            t = time.perf_counter()
            after = await s.run(widgets=[{"id": first["inputs"]["Username"], "string": args.username},
                                         {"id": first["inputs"]["Password"], "string": args.password},
                                         {"id": first["buttons"]["Sign in"], "trigger": True}])
            stats["sign in"].append(time.perf_counter() - t)
            if not after["headings"] or after["errors"]:
                failures.append((i, "sign-in failed", after["errors"], after["exceptions"]))
                return
            for _ in range(args.rounds):
                for p in PAGES[1:]:
                    h = s.pages.get(p)
                    if not h:
                        failures.append((i, f"page {p} not in navigation", list(s.pages)))
                        continue
                    t = time.perf_counter()
                    r = await s.run(page_hash=h)
                    stats[p].append(time.perf_counter() - t)
                    if r["exceptions"] or not r["headings"]:
                        failures.append((i, f"page {p} failed", r["exceptions"][:1], r["errors"][:1]))
    except Exception as e:  # noqa: BLE001
        failures.append((i, f"{type(e).__name__}: {str(e)[:160]}"))


async def main_async(args) -> int:
    stats: dict[str, list[float]] = defaultdict(list)
    failures: list = []
    t0 = time.perf_counter()
    await asyncio.gather(*(one_user(i, args, stats, failures) for i in range(args.users)))
    wall = time.perf_counter() - t0
    print(f"\n{args.users} concurrent users x {args.rounds} round(s) against {args.url}  ·  wall time {wall:.1f}s")
    print(f"{'step':16s} {'n':>5s} {'median':>8s} {'p95':>8s} {'worst':>8s}")
    for k, v in stats.items():
        v = sorted(v)
        p95 = v[min(len(v) - 1, int(round(0.95 * (len(v) - 1))))]
        print(f"{k:16s} {len(v):5d} {statistics.median(v):7.2f}s {p95:7.2f}s {v[-1]:7.2f}s")
    total = sum(len(v) for v in stats.values())
    print(f"requests: {total}  ·  failures: {len(failures)}")
    for f in failures[:15]:
        print("  FAIL", f)
    return 1 if failures else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8501")
    ap.add_argument("--users", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--ramp", type=float, default=0.1, help="seconds between user arrivals")
    ap.add_argument("--username", required=True)
    ap.add_argument("--password", required=True)
    raise SystemExit(asyncio.run(main_async(ap.parse_args())))


if __name__ == "__main__":
    main()
