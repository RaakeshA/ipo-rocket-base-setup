from __future__ import annotations

import json
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.scanner import RuleConfig, fetch_history, normalize_universe, scan_universe


ROOT = Path(__file__).parent
UNIVERSE_PATH = ROOT / "data" / "ipo_universe.csv"
RULES_PATH = ROOT / "config" / "rules.json"
LATEST_SCAN_PATH = ROOT / "outputs" / "scans" / "latest.csv"


st.set_page_config(page_title="IPO Rocket Base Setup", layout="wide")


APP_CSS = """
<style>
    :root {
        --app-bg: #f7f7f7;
        --app-surface: #ffffff;
        --app-surface-muted: #f2f2f2;
        --app-text: #111111;
        --app-text-muted: #5f5f5f;
        --app-border: #dddddd;
        --app-accent: #111111;
        --app-accent-soft: #eeeeee;
    }

    html, body, [data-testid="stAppViewContainer"] {
        background: var(--app-bg);
        color: var(--app-text);
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
    }

    [data-testid="stHeader"] {
        background: rgba(247, 247, 247, 0.88);
        backdrop-filter: saturate(180%) blur(18px);
        border-bottom: 1px solid rgba(221, 221, 221, 0.75);
    }

    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid var(--app-border);
    }

    [data-testid="stSidebar"] * {
        color: var(--app-text);
    }

    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {
        font-weight: 650;
        letter-spacing: 0;
    }

    .block-container {
        padding-top: 1.6rem;
        padding-bottom: 1.5rem;
        max-width: 1280px;
    }

    h1 {
        color: var(--app-text);
        font-size: 32px;
        line-height: 1.08;
        font-weight: 680;
        letter-spacing: 0;
        margin: 0 0 0.15rem;
    }

    h2, h3, p, label, span, div {
        letter-spacing: 0;
    }

    [data-testid="stCaptionContainer"] {
        color: var(--app-text-muted);
        font-size: 16px;
    }

    [data-testid="stMetric"] {
        background: var(--app-surface);
        border: 1px solid rgba(221, 221, 221, 0.95);
        border-radius: 8px;
        padding: 10px 12px 9px;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.035);
    }

    [data-testid="stMetricLabel"] {
        color: var(--app-text-muted);
        font-size: 12px;
        font-weight: 520;
    }

    [data-testid="stMetricValue"] {
        color: var(--app-text);
        font-weight: 650;
    }

    div[data-testid="stTabs"] button {
        color: var(--app-text-muted);
        font-weight: 560;
        padding-top: 0.25rem;
        padding-bottom: 0.35rem;
    }

    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: var(--app-accent);
    }

    div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
        background-color: var(--app-accent);
    }

    .stButton > button,
    .stDownloadButton > button {
        background: var(--app-accent);
        color: white;
        border: 1px solid var(--app-accent);
        border-radius: 8px;
        font-weight: 600;
        min-height: 36px;
        box-shadow: none;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover {
        background: #2b2b2b;
        border-color: #2b2b2b;
        color: white;
    }

    [data-testid="stSidebar"] .stButton > button {
        background: var(--app-surface-muted);
        color: var(--app-accent);
        border: 1px solid var(--app-border);
    }

    [data-baseweb="slider"] [role="slider"] {
        background-color: var(--app-accent);
        border-color: var(--app-accent);
    }

    [data-testid="stDataFrame"] {
        border: 1px solid rgba(221, 221, 221, 0.95);
        border-radius: 8px;
        overflow: hidden;
        background: var(--app-surface);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.035);
    }

    [data-testid="stExpander"] {
        background: var(--app-surface);
        border: 1px solid rgba(221, 221, 221, 0.95);
        border-radius: 8px;
        margin-bottom: 0.5rem;
    }

    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div {
        border-radius: 8px;
        border-color: var(--app-border);
        background: var(--app-surface);
    }

    .stAlert {
        border-radius: 8px;
    }

    hr {
        border-color: rgba(221, 221, 221, 0.8);
    }

    .app-hero {
        margin-bottom: 0.7rem;
        padding-bottom: 0.7rem;
        border-bottom: 1px solid rgba(221, 221, 221, 0.85);
    }

    .app-kicker {
        color: var(--app-text-muted);
        font-size: 12px;
        font-weight: 650;
        margin-bottom: 0.2rem;
        text-transform: uppercase;
    }

    [data-testid="stVerticalBlock"] {
        gap: 0.6rem;
    }

    [data-testid="stHorizontalBlock"] {
        gap: 0.6rem;
    }

    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.45rem;
    }

    [data-testid="stSidebar"] .stSlider,
    [data-testid="stSidebar"] .stNumberInput {
        padding-bottom: 0.1rem;
    }
</style>
"""


def inject_design() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


METRIC_HELP = {
    "passes": "True when the stock clears all active filters: price, liquidity, relative strength, volume expansion, volatility, and minimum score.",
    "symbol": "Trading symbol used for the stock. The app appends .NS when a separate Yahoo ticker is not supplied.",
    "name": "Company name from the IPO universe file.",
    "score": "Composite setup score from 0 to 100. Higher means more of the rocket-base conditions are aligned.",
    "last_close": "Latest adjusted daily close from Yahoo Finance.",
    "rs_percent": "Stock return minus Nifty 50 return over the selected lookback. Positive means the stock is outperforming Nifty.",
    "volume_ratio": "Average volume over the last 10 sessions divided by 50-session average volume. Above 1.0 means volume is expanding.",
    "avg_value_cr": "Average traded value over the last 20 sessions, in crore rupees. Higher values are generally easier to enter and exit.",
    "atr_percent": "14-day average true range as a percentage of price. Lower is calmer; very high values mean wider risk and position sizing pressure.",
    "distance_from_55d_high_percent": "Distance from the 55-session high. Values near 0 mean the stock is close to a breakout or high-tight area.",
    "effective_lookback_days": "Actual available lookback used for newer IPOs when the selected lookback is longer than the stock history.",
    "ipo_age_days": "Calendar days since listing. Controlled by the max IPO age slider.",
    "setup_notes": "Plain-English reasons the stock earned score points.",
}


@st.cache_data(show_spinner=False)
def load_universe(_file_mtime: float) -> pd.DataFrame:
    return pd.read_csv(UNIVERSE_PATH)


@st.cache_data(show_spinner=False)
def load_latest_scan(_file_mtime: float) -> pd.DataFrame:
    if not LATEST_SCAN_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(LATEST_SCAN_PATH)


@st.cache_data(show_spinner=True, ttl=900)
def run_scan(universe_csv: str, config: RuleConfig) -> pd.DataFrame:
    return scan_universe(pd.read_csv(StringIO(universe_csv)), config)


@st.cache_data(show_spinner=True, ttl=900)
def load_chart_history(ticker: str) -> pd.DataFrame:
    histories = fetch_history([ticker], period="12mo")
    return histories.get(ticker, pd.DataFrame())


def load_rules() -> RuleConfig:
    if RULES_PATH.exists():
        with RULES_PATH.open("r", encoding="utf-8") as handle:
            return RuleConfig(**json.load(handle))
    return RuleConfig()


def file_mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


def sidebar_config(defaults: RuleConfig) -> RuleConfig:
    st.sidebar.header("Setup Rules")
    if st.sidebar.button("Refresh saved data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    return RuleConfig(
        max_ipo_age_days=st.sidebar.slider(
            "Max IPO age, days",
            30,
            365,
            defaults.max_ipo_age_days,
            15,
            help="How recent the IPO must be. Use 180-240 days for the 6-8 month window you want to focus on.",
        ),
        min_price=st.sidebar.number_input(
            "Minimum price",
            min_value=1.0,
            max_value=5000.0,
            value=defaults.min_price,
            step=5.0,
            help="Avoids very low-priced names where spreads, volatility, and data quality can be worse.",
        ),
        min_avg_value_cr=st.sidebar.slider(
            "Minimum avg traded value, cr",
            1.0,
            100.0,
            defaults.min_avg_value_cr,
            1.0,
            help="Liquidity filter. This is average traded value over the recent window in crore rupees. Raise it to avoid hard-to-enter stocks.",
        ),
        min_rs_percent=st.sidebar.slider(
            "Minimum relative strength vs Nifty, %",
            -20.0,
            50.0,
            defaults.min_rs_percent,
            1.0,
            help="Stock return minus Nifty return over the selected lookback. Positive means the IPO is outperforming the market.",
        ),
        min_volume_ratio=st.sidebar.slider(
            "Minimum volume expansion ratio",
            0.5,
            5.0,
            defaults.min_volume_ratio,
            0.1,
            help="Recent average volume divided by normal average volume. Above 1.2 suggests renewed interest or accumulation.",
        ),
        max_atr_percent=st.sidebar.slider(
            "Maximum ATR volatility, %",
            2.0,
            30.0,
            defaults.max_atr_percent,
            0.5,
            help="14-day average true range as a percent of price. Lower is calmer; very high values need wider stops and smaller size.",
        ),
        min_score=st.sidebar.slider(
            "Minimum setup score",
            0,
            100,
            defaults.min_score,
            5,
            help="Composite score from trend, RS, volume, liquidity, volatility, and proximity to highs. Higher means stricter filtering.",
        ),
        lookback_days=st.sidebar.select_slider(
            "Relative strength lookback",
            options=[21, 42, 63, 126],
            value=defaults.lookback_days,
            help="Sessions used for stock-vs-Nifty relative strength. For recent IPOs, 21-42 sessions is usually more useful.",
        ),
    )


def render_chart(ticker: str) -> None:
    history = load_chart_history(ticker)
    if history.empty:
        st.info("No chart data available for this ticker.")
        return

    history = history.copy()
    history["MA20"] = history["Close"].rolling(20).mean()
    history["MA50"] = history["Close"].rolling(50).mean()

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=history.index,
            open=history["Open"],
            high=history["High"],
            low=history["Low"],
            close=history["Close"],
            name="Price",
        )
    )
    fig.add_trace(go.Scatter(x=history.index, y=history["MA20"], name="20 DMA", line=dict(width=1.4)))
    fig.add_trace(go.Scatter(x=history.index, y=history["MA50"], name="50 DMA", line=dict(width=1.4)))
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=20, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_results(results: pd.DataFrame, result_key: str, universe_count: int | None = None) -> None:
    if results.empty:
        st.warning("No scan results yet. Run a manual scan or wait for the scheduled scan.")
        return

    passing = results[results["passes"] == True] if "passes" in results else pd.DataFrame()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Universe", universe_count or "NA", help="Stocks currently listed in the IPO universe file.")
    c2.metric("Evaluated", len(results), help="Stocks with enough valid Yahoo Finance history to calculate the setup metrics.")
    c3.metric("Potential upside list", len(passing), help="Stocks that pass all active setup filters.")
    c4.metric("Top score", int(results["score"].max()), help=METRIC_HELP["score"])
    c5.metric("Median RS %", f"{results['rs_percent'].median():.1f}", help=METRIC_HELP["rs_percent"])

    display_columns = [
        "passes",
        "symbol",
        "name",
        "score",
        "last_close",
        "rs_percent",
        "volume_ratio",
        "avg_value_cr",
        "atr_percent",
        "distance_from_55d_high_percent",
        "effective_lookback_days",
        "ipo_age_days",
        "setup_notes",
    ]
    columns = [column for column in display_columns if column in results.columns]
    st.dataframe(
        results[columns],
        use_container_width=True,
        hide_index=True,
        height=310,
        column_config={
            "passes": st.column_config.CheckboxColumn("Pass", help=METRIC_HELP["passes"]),
            "symbol": st.column_config.TextColumn("Symbol", help=METRIC_HELP["symbol"]),
            "name": st.column_config.TextColumn("Company", help=METRIC_HELP["name"]),
            "score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, help=METRIC_HELP["score"]),
            "last_close": st.column_config.NumberColumn("Last close", help=METRIC_HELP["last_close"]),
            "rs_percent": st.column_config.NumberColumn("RS vs Nifty %", help=METRIC_HELP["rs_percent"]),
            "volume_ratio": st.column_config.NumberColumn("Volume ratio", help=METRIC_HELP["volume_ratio"]),
            "avg_value_cr": st.column_config.NumberColumn("Avg value, cr", help=METRIC_HELP["avg_value_cr"]),
            "atr_percent": st.column_config.NumberColumn("ATR %", help=METRIC_HELP["atr_percent"]),
            "distance_from_55d_high_percent": st.column_config.NumberColumn("From 55D high %", help=METRIC_HELP["distance_from_55d_high_percent"]),
            "effective_lookback_days": st.column_config.NumberColumn("RS lookback used", help=METRIC_HELP["effective_lookback_days"]),
            "ipo_age_days": st.column_config.NumberColumn("IPO age", help=METRIC_HELP["ipo_age_days"]),
            "setup_notes": st.column_config.TextColumn("Setup notes", help=METRIC_HELP["setup_notes"]),
        },
    )

    selected_symbol = st.selectbox("Chart", results["symbol"].tolist(), key=f"{result_key}_chart_symbol")
    selected_ticker = results.loc[results["symbol"] == selected_symbol, "ticker"].iloc[0]
    render_chart(selected_ticker)

    st.download_button(
        "Download scan results",
        data=results.to_csv(index=False),
        file_name="ipo_rocket_base_setup_scan.csv",
        mime="text/csv",
        use_container_width=True,
    )


def main() -> None:
    inject_design()
    st.markdown(
        """
        <div class="app-hero">
            <div class="app-kicker">Indian IPO momentum scanner</div>
            <h1>IPO Rocket Base Setup</h1>
            <div style="color:#5f5f5f;font-size:14px;max-width:760px;">
                A daily view of recent IPOs with improving trend, strength, volume, liquidity, and risk characteristics.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    defaults = load_rules()
    config = sidebar_config(defaults)
    universe = normalize_universe(load_universe(file_mtime(UNIVERSE_PATH)))

    with st.expander("IPO universe", expanded=False):
        st.dataframe(universe, use_container_width=True, hide_index=True)

    tab_latest, tab_manual = st.tabs(["Latest daily scan", "Manual scan"])
    with tab_latest:
        render_results(load_latest_scan(file_mtime(LATEST_SCAN_PATH)), "latest", len(universe))

    with tab_manual:
        st.write("Use this when you want to test rule changes before updating the scheduled scan config.")
        current_config = config.to_dict()
        previous_config = st.session_state.get("manual_scan_config")
        if previous_config and previous_config != current_config:
            st.info("Rule changes are ready. Click Run manual scan to refresh the results with the new settings.")

        if st.button("Run manual scan", type="primary", use_container_width=True, key="run_manual_scan"):
            with st.spinner("Running manual scan with the current sidebar rules..."):
                st.session_state["manual_scan_results"] = run_scan(universe.to_csv(index=False), config)
                st.session_state["manual_scan_config"] = current_config
                st.session_state["manual_scan_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        manual_results = st.session_state.get("manual_scan_results")
        if manual_results is None:
            st.info("No manual scan in this session yet. Adjust the sidebar rules, then click Run manual scan.")
        else:
            scan_time = st.session_state.get("manual_scan_time", "this session")
            st.caption(f"Manual scan generated at {scan_time}.")
            render_results(manual_results, "manual", len(universe))


if __name__ == "__main__":
    main()
