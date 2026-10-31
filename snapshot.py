"""Build the daily fundamentals snapshot (run by .github/workflows/snapshot.yml).

Fetches Yahoo profiles + annual/quarterly statements for the screener universe (plus optional SNAPSHOT_EXTRA
tickers), merges with the previous snapshot so temporary failures keep yesterday's data, and writes a gzip JSON.
The web app reads this file instead of calling Yahoo, which avoids cloud rate limits.

    python snapshot.py --out snapshot_out/fundamentals.json.gz
"""
import argparse
import gzip
import json
import os
import sys
import time
from pathlib import Path

os.environ["PA_NO_SNAPSHOT"] = "1"  # always fetch live here

import requests  # noqa: E402

from agent import data  # noqa: E402

KINDS = ["financials", "balance_sheet", "cashflow", "quarterly_financials", "quarterly_balance_sheet", "quarterly_cashflow"]


def previous() -> dict:
    try:
        r = requests.get(data.SNAPSHOT_URL, timeout=30)
        return json.loads(gzip.decompress(r.content)) if r.status_code == 200 else {}
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="snapshot_out/fundamentals.json.gz")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between stocks (be gentle with Yahoo)")
    args = ap.parse_args()

    cfg = json.loads(Path("config.json").read_text(encoding="utf-8"))
    syms = [s for m in cfg["screener"]["universe"].values() for s in m]
    syms += [s.strip().upper() for s in os.environ.get("SNAPSHOT_EXTRA", "").split(",") if s.strip()]
    syms = list(dict.fromkeys(syms))

    snap = previous()
    ok = fail = 0
    for i, s in enumerate(syms, 1):
        inf = data.info_live(s)
        if inf:
            st = {}
            for k in KINDS:
                df = data.statement_live(s, k)
                if not df.empty:
                    st[k] = data.df_to_json(df)
            snap[s] = {"t": time.time(), "info": json.loads(json.dumps(inf, default=str)), "st": st}
            ok += 1
        else:
            fail += 1
        print(f"[{i}/{len(syms)}] {s}: {'ok' if inf else 'FAILED (kept previous)'}", flush=True)
        time.sleep(args.pause)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(gzip.compress(json.dumps(snap, separators=(",", ":")).encode()))
    print(f"Snapshot: {ok} refreshed, {fail} failed, {len(snap)} total -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    if ok == 0:
        sys.exit("No stock could be fetched - Yahoo may be blocking this runner; previous snapshot left untouched.")


if __name__ == "__main__":
    main()
