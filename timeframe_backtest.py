import json
from pathlib import Path

import pandas as pd
import yfinance as yf
from pykrx import stock


ROOT = Path(__file__).resolve().parent
NOTES_PATH = ROOT / "_cache" / "chart_case_notes.json"


def normalize_kr(df: pd.DataFrame) -> pd.DataFrame:
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
    return out[["open", "high", "low", "close", "volume"]]


def normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower().replace(" ", "_") for c in df.columns]
    else:
        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    out = df[["open", "high", "low", "close", "volume"]].copy()
    out.index = pd.to_datetime(out.index)
    if out.index.tz is not None:
        out.index = out.index.tz_convert("Asia/Seoul").tz_localize(None)
    return out


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = pd.DataFrame()
    out["open"] = df["open"].resample(rule).first()
    out["high"] = df["high"].resample(rule).max()
    out["low"] = df["low"].resample(rule).min()
    out["close"] = df["close"].resample(rule).last()
    out["volume"] = df["volume"].resample(rule).sum()
    return out.dropna(subset=["open", "high", "low", "close"])


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for n in [5, 20, 60, 120, 240, 480]:
        out[f"ma{n}"] = out["close"].rolling(n).mean()
        out[f"dist{n}"] = (out["close"] / out[f"ma{n}"] - 1) * 100

    delta = out["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    out["rsi14"] = 100 - (100 / (1 + rs))
    out["vr20"] = out["volume"] / out["volume"].rolling(20).mean()

    hh20 = out["high"].rolling(20).max().shift(1)
    ll20 = out["low"].rolling(20).min().shift(1)
    out["from_hh20"] = (out["close"] / hh20 - 1) * 100
    out["box_range_pct"] = (hh20 - ll20) / out["close"] * 100
    return out


def future_stats(df: pd.DataFrame, idx: int, bars: int) -> dict[str, float] | None:
    fut = df.iloc[idx + 1 : idx + 1 + bars]
    if len(fut) < bars:
        return None
    entry = float(df.iloc[idx]["close"])
    return {
        "peak": float((fut["high"].max() / entry - 1) * 100),
        "close": float((fut.iloc[-1]["close"] / entry - 1) * 100),
        "dd": float((fut["low"].min() / entry - 1) * 100),
    }


def sig_1h(row: pd.Series) -> bool:
    return bool(
        ((-4 <= row["dist20"] <= 1) or (-2 <= row["dist60"] <= 3))
        and 35 <= row["rsi14"] <= 58
        and row["vr20"] <= 1.15
    )


def sig_4h(row: pd.Series) -> bool:
    return bool(
        ((-4.5 <= row["dist20"] <= 1.5) or (-2.5 <= row["dist60"] <= 3.5))
        and -2 <= row["dist120"] <= 8
        and 34 <= row["rsi14"] <= 58
        and row["vr20"] <= 1.15
    )


def sig_1d(row: pd.Series) -> bool:
    return bool(
        (
            ((-4.5 <= row["dist20"] <= 1.5) and row["dist60"] > -4)
            or (-2.5 <= row["dist60"] <= 3.5)
            or (-2.5 <= row["dist120"] <= 5.5)
        )
        and 34 <= row["rsi14"] <= 56
        and row["vr20"] <= 1.1
        and 8 <= row["box_range_pct"] <= 35
    )


def sig_1w(row: pd.Series) -> bool:
    return bool(
        ((-6 <= row["dist20"] <= 2) or (-4 <= row["dist60"] <= 6))
        and 35 <= row["rsi14"] <= 60
    )


def sig_1mo(row: pd.Series) -> bool:
    return bool(
        ((-6 <= row["dist5"] <= 3) or (-8 <= row["dist20"] <= 5))
        and 38 <= row["rsi14"] <= 68
    )


def main() -> None:
    notes = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    tickers = sorted({c["ticker"] for c in notes["cases"] if c["market"] == "KR"})

    configs = [
        ("1h", "yf", "60m", None, 20, sig_1h),
        ("4h", "yf", "4h", None, 20, sig_4h),
        ("1d", "kr", None, None, 20, sig_1d),
        ("1w", "kr", None, "W-FRI", 8, sig_1w),
        ("1mo", "kr", None, "MS", 6, sig_1mo),
    ]

    rows = []
    for label, source, interval, rule, bars, sig_fn in configs:
        hits = []
        for ticker in tickers:
            try:
                if source == "yf":
                    raw = yf.download(
                        f"{ticker}.KS",
                        period="730d",
                        interval=interval,
                        auto_adjust=False,
                        progress=False,
                    )
                    if raw.empty:
                        continue
                    df = add_indicators(normalize_yf(raw))
                    start_i = 500 if len(df) > 600 else 200
                else:
                    raw = stock.get_market_ohlcv_by_date("20180101", "20260311", ticker)
                    if raw.empty:
                        continue
                    df = normalize_kr(raw)
                    if rule:
                        df = resample_ohlcv(df, rule)
                    df = add_indicators(df)
                    start_i = 30 if label == "1mo" else 100

                for i in range(start_i, len(df) - bars - 1):
                    row = df.iloc[i]
                    if not sig_fn(row):
                        continue
                    fut = future_stats(df, i, bars)
                    if fut:
                        hits.append(fut)
            except Exception:
                continue

        hit_df = pd.DataFrame(hits)
        if hit_df.empty:
            continue

        rows.append(
            {
                "timeframe": label,
                "signals": len(hit_df),
                "avg_peak": hit_df["peak"].mean(),
                "avg_close": hit_df["close"].mean(),
                "avg_dd": hit_df["dd"].mean(),
                "close_pos": (hit_df["close"] > 0).mean() * 100,
                "peak8": (hit_df["peak"] >= 8).mean() * 100,
                "dd_neg8": (hit_df["dd"] <= -8).mean() * 100,
            }
        )

    res = pd.DataFrame(rows)
    res["score"] = (
        res["avg_close"] * 3
        + res["avg_peak"] * 0.7
        + res["close_pos"] * 0.08
        - (-res["avg_dd"]) * 1.2
        - res["dd_neg8"] * 0.05
    )
    res = res.sort_values("score", ascending=False)
    print(
        res.to_string(
            index=False,
            formatters={
                "avg_peak": "{:.2f}".format,
                "avg_close": "{:.2f}".format,
                "avg_dd": "{:.2f}".format,
                "close_pos": "{:.1f}".format,
                "peak8": "{:.1f}".format,
                "dd_neg8": "{:.1f}".format,
                "score": "{:.2f}".format,
            },
        )
    )


if __name__ == "__main__":
    main()
