import json
from pathlib import Path

import pandas as pd
import yfinance as yf
from pykrx import stock


ROOT = Path(__file__).resolve().parent
NOTES_PATH = ROOT / "_cache" / "chart_case_notes.json"


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    cols = list(df.columns)
    mapping = {
        cols[0]: "open",
        cols[1]: "high",
        cols[2]: "low",
        cols[3]: "close",
        cols[4]: "volume",
    }
    if len(cols) >= 6:
        mapping[cols[5]] = "value"
    if len(cols) >= 7:
        mapping[cols[6]] = "change"
    out = df.rename(columns=mapping)
    out.index = pd.to_datetime(out.index)
    return out


def normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower().replace(" ", "_") for c in df.columns]
    else:
        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    out = df[["open", "high", "low", "close", "volume"]].copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    return out


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for n in [5, 20, 60, 120]:
        out[f"ma{n}"] = out["close"].rolling(n).mean()
        out[f"dist{n}"] = (out["close"] / out[f"ma{n}"] - 1) * 100
    delta = out["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    out["rsi14"] = 100 - (100 / (1 + rs))
    return out


def future_stats(df: pd.DataFrame, idx: int) -> dict[str, float]:
    fut = df.iloc[idx + 1 : idx + 21]
    entry = float(df.iloc[idx]["close"])
    return {
        "peak20": float((fut["high"].max() / entry - 1) * 100),
        "close20": float((fut.iloc[-1]["close"] / entry - 1) * 100),
        "dd20": float((fut["low"].min() / entry - 1) * 100),
    }


def main() -> None:
    notes = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    tickers = sorted({c["ticker"] for c in notes["cases"] if c["market"] == "KR"})

    rows = []
    idx_df = yf.download("^KS11", start="2018-01-01", end="2026-03-12", auto_adjust=False, progress=False)
    idx_df = normalize_yf(idx_df)
    idx_df = add_indicators(idx_df)
    for ticker in tickers:
        try:
            price = normalize_ohlcv(stock.get_market_ohlcv_by_date("20180101", "20260311", ticker))
            if price.empty:
                continue
            price = add_indicators(price)
            merged = price.join(
                idx_df[["close", "dist20", "dist60", "rsi14"]],
                how="inner",
                rsuffix="_index",
            )
            for i in range(260, len(merged) - 21):
                row = merged.iloc[i]
                fut = future_stats(merged, i)
                rows.append(
                    {
                        "market_ok": bool(
                            row["dist20_index"] > -3 and row["dist60_index"] > -5 and row["rsi14_index"] >= 40
                        ),
                        **fut,
                    }
                )
        except Exception:
            continue

    df = pd.DataFrame(rows)
    print("=== MARKET SUPPORT BACKTEST (KR) ===")
    print(
        "baseline",
        len(df),
        "avg_close20",
        round(df["close20"].mean(), 2),
        "avg_peak20",
        round(df["peak20"].mean(), 2),
        "avg_dd20",
        round(df["dd20"].mean(), 2),
    )
    good = df[df["market_ok"]]
    print(
        "market_ok",
        len(good),
        "avg_close20",
        round(good["close20"].mean(), 2),
        "avg_peak20",
        round(good["peak20"].mean(), 2),
        "avg_dd20",
        round(good["dd20"].mean(), 2),
        "close>0",
        round((good["close20"] > 0).mean() * 100, 1),
    )

    sample = stock.get_market_fundamental_by_date("20210104", "20210108", "005930")
    print("=== FUNDAMENTAL HISTORY CHECK (KR) ===")
    if sample.empty:
        print("pykrx historical fundamentals unavailable in this environment; keep fundamental score weak and reference-only.")
    else:
        print("pykrx historical fundamentals available; broader factor test can be expanded.")

    print("=== US/CRYPTO NOTE ===")
    print("US historical fundamentals and crypto fundamentals are not reliably backtestable with the current repository sources.")
    print("Use market context only for crypto, and keep US fundamentals as weak reference until a historical provider is added.")


if __name__ == "__main__":
    main()
