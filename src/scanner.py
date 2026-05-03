from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import contextlib
import io
import logging
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import yfinance as yf


BENCHMARK_TICKER = "^NSEI"
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


@dataclass(frozen=True)
class RuleConfig:
    max_ipo_age_days: int = 240
    min_price: float = 20.0
    min_avg_value_cr: float = 5.0
    min_rs_percent: float = 0.0
    min_volume_ratio: float = 1.2
    min_score: int = 55
    max_atr_percent: float = 12.0
    lookback_days: int = 42

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def load_universe(path: Path) -> pd.DataFrame:
    return normalize_universe(pd.read_csv(path))


def normalize_universe(universe: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "name", "listing_date"}
    missing = required.difference(universe.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    cleaned = universe.copy()
    cleaned["symbol"] = cleaned["symbol"].astype(str).str.upper().str.strip()
    cleaned["name"] = cleaned["name"].astype(str).str.strip()
    cleaned["listing_date"] = pd.to_datetime(cleaned["listing_date"], errors="coerce").dt.date
    cleaned = cleaned.dropna(subset=["symbol", "listing_date"])
    cleaned = cleaned.drop_duplicates(subset=["symbol"], keep="first")
    if "ticker" in cleaned.columns:
        cleaned["ticker"] = cleaned["ticker"].fillna("").astype(str).str.upper().str.strip()
        cleaned["ticker"] = cleaned.apply(
            lambda row: row["ticker"] if row["ticker"] else to_nse_ticker(row["symbol"]),
            axis=1,
        )
    else:
        cleaned["ticker"] = cleaned["symbol"].map(to_nse_ticker)
    return cleaned.sort_values("listing_date", ascending=False).reset_index(drop=True)


def to_nse_ticker(symbol: str) -> str:
    symbol = symbol.upper().strip()
    return symbol if symbol.endswith(".NS") else f"{symbol}.NS"


def filter_by_ipo_age(universe: pd.DataFrame, max_age_days: int, as_of: date | None = None) -> pd.DataFrame:
    as_of = as_of or date.today()
    filtered = universe.copy()
    filtered["ipo_age_days"] = filtered["listing_date"].map(lambda listing: (as_of - listing).days)
    return filtered[(filtered["ipo_age_days"] >= 0) & (filtered["ipo_age_days"] <= max_age_days)]


def fetch_history(tickers: Iterable[str], period: str = "18mo") -> dict[str, pd.DataFrame]:
    tickers = sorted({ticker for ticker in tickers if ticker})
    histories: dict[str, pd.DataFrame] = {}
    if not tickers:
        return histories

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        data = yf.download(
            tickers=tickers,
            period=period,
            auto_adjust=True,
            progress=False,
            threads=True,
            group_by="ticker",
        )

    if data.empty:
        return histories

    if isinstance(data.columns, pd.MultiIndex):
        available = set(data.columns.get_level_values(0))
        for ticker in tickers:
            if ticker not in available:
                continue
            ticker_data = data[ticker].dropna(how="all")
            if not ticker_data.empty:
                histories[ticker] = ticker_data
    else:
        histories[tickers[0]] = data.dropna(how="all")

    return histories


def fetch_benchmark(period: str = "18mo") -> pd.Series:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        data = yf.download(BENCHMARK_TICKER, period=period, auto_adjust=True, progress=False, threads=False)
    if data.empty:
        return pd.Series(dtype=float)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    return data["Close"].dropna()


def scan_universe(universe: pd.DataFrame, config: RuleConfig) -> pd.DataFrame:
    normalized = normalize_universe(universe)
    candidates = filter_by_ipo_age(normalized, config.max_ipo_age_days)
    if candidates.empty:
        return pd.DataFrame()

    histories = fetch_history(candidates["ticker"].tolist())
    benchmark = fetch_benchmark()
    rows = []

    for row in candidates.itertuples(index=False):
        history = histories.get(row.ticker)
        if history is None or len(history) < 25:
            continue
        metrics = calculate_metrics(history, benchmark, config.lookback_days)
        if metrics is None:
            continue
        scored = score_stock(metrics, config)
        rows.append(
            {
                "symbol": row.symbol,
                "name": row.name,
                "ticker": row.ticker,
                "listing_date": row.listing_date,
                "ipo_age_days": row.ipo_age_days,
                "scan_date": date.today().isoformat(),
                **metrics,
                **scored,
            }
        )

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result["passes"] = (
        (result["last_close"] >= config.min_price)
        & (result["avg_value_cr"] >= config.min_avg_value_cr)
        & (result["rs_percent"] >= config.min_rs_percent)
        & (result["volume_ratio"] >= config.min_volume_ratio)
        & (result["atr_percent"] <= config.max_atr_percent)
        & (result["score"] >= config.min_score)
    )
    return result.sort_values(["passes", "score", "rs_percent"], ascending=[False, False, False]).reset_index(drop=True)


def calculate_metrics(history: pd.DataFrame, benchmark: pd.Series, lookback_days: int) -> dict[str, float] | None:
    data = history.dropna(subset=["Close", "Volume"]).copy()
    if len(data) < 25:
        return None

    close = data["Close"]
    high = data["High"]
    low = data["Low"]
    volume = data["Volume"]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else np.nan
    ma150 = close.rolling(150).mean().iloc[-1] if len(close) >= 150 else np.nan
    avg_volume_window = min(50, len(volume))
    avg_vol = volume.iloc[-avg_volume_window:].mean()
    recent_volume_window = min(10, len(volume))
    value_window = min(20, len(close))
    avg_value_cr = (close.iloc[-value_window:] * volume.iloc[-value_window:]).mean() / 10_000_000
    volume_ratio = volume.iloc[-recent_volume_window:].mean() / avg_vol if avg_vol else np.nan

    effective_lookback = min(lookback_days, len(close) - 1)
    stock_return = close.iloc[-1] / close.iloc[-effective_lookback] - 1
    benchmark_return = 0.0
    if not benchmark.empty:
        aligned_benchmark = benchmark.reindex(close.index, method="ffill").dropna()
        if len(aligned_benchmark) >= effective_lookback:
            benchmark_return = aligned_benchmark.iloc[-1] / aligned_benchmark.iloc[-effective_lookback] - 1

    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    atr14 = true_range.rolling(14).mean().iloc[-1]
    high_window = min(55, len(close))
    distance_from_high = close.iloc[-1] / close.rolling(high_window).max().iloc[-1] - 1

    return {
        "last_close": round(float(close.iloc[-1]), 2),
        "ma20": round(float(ma20), 2),
        "ma50": round(float(ma50), 2),
        "ma150": round(float(ma150), 2) if not np.isnan(ma150) else np.nan,
        "avg_value_cr": round(float(avg_value_cr), 2),
        "volume_ratio": round(float(volume_ratio), 2),
        "return_percent": round(float(stock_return * 100), 2),
        "benchmark_return_percent": round(float(benchmark_return * 100), 2),
        "effective_lookback_days": int(effective_lookback),
        "rs_percent": round(float((stock_return - benchmark_return) * 100), 2),
        "atr_percent": round(float(atr14 / close.iloc[-1] * 100), 2),
        "distance_from_55d_high_percent": round(float(distance_from_high * 100), 2),
    }


def score_stock(metrics: dict[str, float], config: RuleConfig) -> dict[str, object]:
    score = 0
    notes: list[str] = []
    last_close = metrics["last_close"]
    ma20 = metrics["ma20"]
    ma50 = metrics["ma50"]
    ma150 = metrics["ma150"]

    if not np.isnan(ma50) and last_close > ma20 > ma50:
        score += 25
        notes.append("price stacked above 20/50 DMA")
    elif not np.isnan(ma50) and last_close > ma50:
        score += 15
        notes.append("price above 50 DMA")
    elif last_close > ma20:
        score += 15
        notes.append("price above 20 DMA")

    if not np.isnan(ma150) and last_close > ma150:
        score += 10
        notes.append("price above 150 DMA")

    if metrics["rs_percent"] >= config.min_rs_percent:
        score += min(25, max(0, int(metrics["rs_percent"] * 1.5)))
        notes.append("outperforming Nifty")

    if metrics["volume_ratio"] >= config.min_volume_ratio:
        score += min(20, int(metrics["volume_ratio"] * 8))
        notes.append("volume expansion")

    if metrics["avg_value_cr"] >= config.min_avg_value_cr:
        score += 10
        notes.append("liquid enough")

    if metrics["atr_percent"] <= config.max_atr_percent:
        score += 10
        notes.append("volatility acceptable")

    if metrics["distance_from_55d_high_percent"] >= -8:
        score += 10
        notes.append("near 55-day high")

    return {"score": min(score, 100), "setup_notes": "; ".join(notes)}
