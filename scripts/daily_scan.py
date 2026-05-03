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


if __name__ == "__main__":
    main()
