"""Run the AI Portfolio Analyst and produce today's report.

Usage:
    python run_agent.py                 # full analysis + new ideas
    python run_agent.py --no-screener   # holdings only (faster)
    python run_agent.py --open          # open the HTML report when done
"""
import argparse
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agent.analyst import PortfolioAnalyst  # noqa: E402


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="AI Portfolio Analyst")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--portfolio", help="CSV with columns symbol,quantity,avg_cost")
    ap.add_argument("--no-screener", action="store_true", help="skip new-stock idea screening")
    ap.add_argument("--open", action="store_true", help="open the HTML report in your browser")
    a = ap.parse_args()

    agent = PortfolioAnalyst(ROOT, Path(a.config), Path(a.portfolio) if a.portfolio else None,
                             run_screener=False if a.no_screener else None)
    res = agent.run()
    print(f"\nHTML report : {res['html']}\nMarkdown    : {res['markdown']}")
    if a.open:
        webbrowser.open(res["html"].as_uri())


if __name__ == "__main__":
    main()
