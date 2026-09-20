from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scanner import RuleConfig, load_universe, scan_universe


UNIVERSE_PATH = ROOT / "data" / "ipo_universe.csv"
RULES_PATH = ROOT / "config" / "rules.json"
OUTPUT_DIR = ROOT / "outputs" / "scans"
WATCHLIST_HISTORY_PATH = OUTPUT_DIR / "watchlist_history.csv"


def load_rules() -> RuleConfig:
    if not RULES_PATH.exists():
        return RuleConfig()
    with RULES_PATH.open("r", encoding="utf-8") as handle:
        return RuleConfig(**json.load(handle))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    universe = load_universe(UNIVERSE_PATH)
    config = load_rules()
    results = scan_universe(universe, config)

    stamp = datetime.now().strftime("%Y-%m-%d")
    output_path = OUTPUT_DIR / f"ipo_scan_{stamp}.csv"
    latest_path = OUTPUT_DIR / "latest.csv"
    results.to_csv(output_path, index=False)
    results.to_csv(latest_path, index=False)
    update_watchlist_history(results, stamp)

    summary = pd.DataFrame(
        [
            {
                "scan_date": stamp,
                "stocks_scanned": len(results),
                "stocks_passing": int(results["passes"].sum()) if "passes" in results else 0,
                "output_path": str(output_path),
            }
        ]
    )
    summary.to_csv(OUTPUT_DIR / "latest_summary.csv", index=False)
    print(summary.to_string(index=False))


def update_watchlist_history(results: pd.DataFrame, stamp: str) -> None:
    if results.empty or "passes" not in results:
        return

    passing = results[results["passes"] == True].copy()
    if passing.empty:
        return

    history_columns = [
        "scan_date",
        "symbol",
        "name",
        "ticker",
        "entry_close",
        "score",
        "rs_percent",
        "volume_ratio",
        "avg_value_cr",
        "atr_percent",
        "ipo_age_days",
    ]
    passing["entry_close"] = passing["last_close"]
    passing["scan_date"] = stamp
    passing = passing[[column for column in history_columns if column in passing.columns]]

    if WATCHLIST_HISTORY_PATH.exists():
        existing = pd.read_csv(WATCHLIST_HISTORY_PATH)
        combined = pd.concat([existing, passing], ignore_index=True)
    else:
        combined = passing

    combined = combined.drop_duplicates(subset=["scan_date", "symbol"], keep="last")
    combined = combined.sort_values(["scan_date", "score"], ascending=[False, False])
    combined.to_csv(WATCHLIST_HISTORY_PATH, index=False)


if __name__ == "__main__":
    main()
