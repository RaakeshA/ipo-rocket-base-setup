# IPO Rocket Base Setup

IPO Rocket Base Setup is a local Streamlit dashboard for scanning recently listed Indian IPO stocks and narrowing them into a potential upside watchlist.

This is a decision-support tool, not an auto-trading system. It helps surface candidates that look technically strong so they can be reviewed manually before any trading decision.

## What The Project Does

- Maintains a recent Indian IPO universe in `data/ipo_universe.csv`.
- Pulls daily OHLCV price and volume data from Yahoo Finance.
- Filters IPOs by listing age, currently tuned for the last 6-8 months.
- Scores stocks using trend, relative strength, volume expansion, liquidity, volatility, and proximity to recent highs.
- Saves daily scan outputs in `outputs/scans`.
- Shows the latest scan and manual rule-testing workflow in a Streamlit dashboard.

## Current Setup Logic

The scanner currently focuses on mainboard IPO stocks listed within roughly the last 8 months.

Default rules are stored in `config/rules.json`:

```json
{
  "max_ipo_age_days": 240,
  "min_price": 20.0,
  "min_avg_value_cr": 5.0,
  "min_rs_percent": 0.0,
  "min_volume_ratio": 1.2,
  "min_score": 55,
  "max_atr_percent": 12.0,
  "lookback_days": 42
}
```

The dashboard sidebar lets you adjust these values without editing code.

## Metrics Used

- **IPO age:** keeps the scan focused on recently listed stocks.
- **Minimum price:** avoids very low-priced stocks where spreads and noise can be worse.
- **Average traded value:** liquidity filter based on recent traded value in crore rupees.
- **Relative strength vs Nifty:** stock return minus Nifty 50 return over the selected lookback.
- **Volume expansion ratio:** recent average volume divided by normal average volume.
- **ATR volatility %:** 14-day average true range as a percentage of price.
- **Setup score:** composite score from trend, RS, volume, liquidity, volatility, and proximity to highs.
- **Distance from 55-day high:** helps identify stocks trading near breakout/high-tight areas.

For newer IPOs, the scanner can work with shorter available history. It requires roughly 25 trading sessions and records the actual `RS lookback used` in the result table.

## Project Structure

```text
app.py                         Streamlit dashboard
config/rules.json              Default scanner rules
data/ipo_universe.csv          IPO stock universe
outputs/scans/latest.csv       Most recent scan output
scripts/daily_scan.py          Daily scan job
scripts/run_daily_scan.ps1     Windows scheduler helper
src/scanner.py                 Core data fetching, metrics, scoring
requirements.txt               Python dependencies
```

## IPO Universe

The IPO universe file supports these columns:

```csv
symbol,name,listing_date,ticker
FIRSTCRY,Brainbees Solutions,2024-08-13,FIRSTCRY.NS
```

- `symbol`: readable NSE/base symbol used in the dashboard.
- `name`: company name.
- `listing_date`: IPO listing date in `YYYY-MM-DD` format.
- `ticker`: optional exact Yahoo Finance ticker. Use this when the IPO name and traded symbol do not map cleanly.

The current universe was expanded from the original sample into a broader mainboard IPO list from May 2024 onward. It intentionally excludes SME IPOs for now because the setup depends on clean liquidity and volume behavior.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If you already installed the dependencies globally during development, the app may also run without activating the virtual environment. A project-level virtual environment is still recommended.

## Run A Daily Scan Manually

```powershell
python scripts\daily_scan.py
```

This writes:

- `outputs/scans/ipo_scan_YYYY-MM-DD.csv`
- `outputs/scans/latest.csv`
- `outputs/scans/latest_summary.csv`

## Open The Dashboard

```powershell
streamlit run app.py
```

Then open:

```text
http://localhost:8501
```

`localhost` means the app is running only on your own computer. Other people cannot access that URL unless the app is deployed or explicitly exposed on a network.

## Private Deployment

Recommended private deployment path:

1. Create a **private** GitHub repository.
2. Push this project to that private repository.
3. Deploy the repo on Streamlit Community Cloud.
4. Keep the Streamlit app private.
5. Invite only specific viewer email addresses from Streamlit's sharing settings.

Important distinction:

- A public app can be opened by anyone with the URL and may be searchable.
- A private app is not available to the public. Viewers must be explicitly invited and sign in.
- A pure "anyone with the link" mode is not the same as private access because links can be forwarded.

Streamlit Community Cloud supports private apps from private GitHub repositories, but free accounts may have private-app limits. Check the current Streamlit Community Cloud settings before relying on it for multiple private apps.

## Dashboard Workflow

The dashboard has two tabs:

- **Latest daily scan:** reads `outputs/scans/latest.csv`.
- **Manual scan:** lets you adjust sidebar rules and rerun the scan immediately.

The sidebar includes explanations for each adjustable metric. If saved files change and the browser still shows old data, use **Refresh saved data** in the sidebar.

## Schedule Daily After Market Close

On Windows, create a Task Scheduler task that runs after NSE market close, for example around 3:45 PM IST:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_daily_scan.ps1
```

The dashboard will automatically use the newest `latest.csv` scan output.

## Important Notes

- Yahoo Finance is used for price and volume data.
- Yahoo Finance does not reliably provide a complete Indian IPO universe, so the universe is maintained in `data/ipo_universe.csv`.
- Some recent IPO tickers may need manual correction in the `ticker` column.
- Stocks without enough valid Yahoo history are skipped until enough sessions are available.
- This tool produces a watchlist, not buy/sell advice.

## Next Improvements

- Add an automated IPO universe updater from a reliable NSE/BSE or IPO data source.
- Add watchlist labels such as Watch, Avoid, Entered, Rejected.
- Add breakout levels, suggested stop references, and base quality notes.
- Add backtesting for the setup rules.
- Add deployment instructions for Streamlit Cloud or a private server.
