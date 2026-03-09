import json
from collections import defaultdict
from pathlib import Path

import pandas as pd
import yfinance as yf
from pykrx import stock


ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "_cache" / "chart_case_notes.json"
OUT_PATH = ROOT / "_cache" / "chart_case_scores.json"


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


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
    df = df.rename(columns=mapping)
    df.index = pd.to_datetime(df.index)
    return df


def normalize_yf(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower().replace(" ", "_") for c in df.columns]
    else:
        df.columns = [str(c).lower().replace(" ", "_") for c in df.columns]
    df.index = pd.to_datetime(df.index)
    keep = ["open", "high", "low", "close", "volume"]
    return df[keep].copy()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for n in [5, 20, 60, 120, 240]:
        df[f"ma{n}"] = df["close"].rolling(n).mean()
        df[f"dist{n}"] = (df["close"] / df[f"ma{n}"] - 1) * 100
        df[f"ma{n}_slope5"] = df[f"ma{n}"].diff(5)

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi14"] = 100 - (100 / (1 + rs))

    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    df["atr_pct"] = df["atr14"] / df["close"] * 100
    df["vr20"] = df["volume"] / df["volume"].rolling(20).mean()
    df["gap20_60"] = (df["ma20"] - df["ma60"]).abs() / df["close"] * 100
    df["gap60_120"] = (df["ma60"] - df["ma120"]).abs() / df["close"] * 100
    df["ret14"] = (df["close"] / df["close"].shift(14) - 1) * 100
    box_high = df["high"].rolling(20).max().shift(1)
    box_low = df["low"].rolling(20).min().shift(1)
    df["box_range_pct"] = (box_high - box_low) / df["close"] * 100
    df["big_bear"] = (
        (df["close"] < df["open"])
        & (((df["open"] - df["close"]) / df["open"]) > 0.04)
    ).astype(int)
    df["threat_prev3"] = df["big_bear"].rolling(3).max().shift(1).fillna(0)
    return df


def fetch_history(market: str, ticker: str, start: str, end: str) -> pd.DataFrame:
    if market == "KR":
        df = stock.get_market_ohlcv_by_date(start, end, ticker)
        return add_indicators(normalize_kr(df))
    df = yf.download(ticker, start=start, end=end, auto_adjust=False, progress=False)
    return add_indicators(normalize_yf(df))


def score_buyable(row: pd.Series) -> tuple[float, dict]:
    score = 0.0
    details = {}

    near20 = abs(row["dist20"]) <= 3
    near60 = abs(row["dist60"]) <= 4
    near120 = abs(row["dist120"]) <= 5
    under20_above60 = (-9 <= row["dist20"] <= -2) and row["close"] > row["ma60"]

    support_score = 0
    support_score += 15 if near20 else 0
    support_score += 25 if near60 else 0
    support_score += 25 if near120 else 0
    support_score += 10 if under20_above60 else 0
    score += support_score
    details["support"] = support_score

    trend_score = 0
    trend_score += 10 if row["ma20"] > row["ma60"] else 0
    trend_score += 10 if row["ma60"] > row["ma120"] else 0
    trend_score += 5 if row["ma20_slope5"] > 0 else 0
    trend_score += 5 if row["ma60_slope5"] > 0 else 0
    score += trend_score
    details["trend"] = trend_score

    quality_score = 0
    quality_score += 5 if 35 <= row["rsi14"] <= 58 else 0
    quality_score += 5 if row["vr20"] < 1.2 else 0
    quality_score += 5 if 8 <= row["box_range_pct"] <= 35 else 0
    quality_score += 5 if row["threat_prev3"] == 1 else 0
    score += quality_score
    details["quality"] = quality_score

    penalty = 0
    penalty += 15 if row["dist120"] > 20 else 0
    penalty += 10 if row["ret14"] > 20 else 0
    penalty += 15 if (row["close"] < row["ma20"] and row["close"] < row["ma60"]) else 0
    penalty += 10 if row["dist20"] > 8 else 0
    score -= penalty
    details["penalty"] = penalty

    return clamp(score), details


def score_result(future: pd.DataFrame, entry_close: float) -> tuple[float, dict]:
    if future.empty:
        return 0.0, {"peak20": 0.0, "close20": 0.0, "dd10": 0.0}

    f10 = future.iloc[:10] if len(future) >= 10 else future
    f20 = future.iloc[:20] if len(future) >= 20 else future

    peak20 = (f20["high"].max() / entry_close - 1) * 100
    close20 = (f20.iloc[-1]["close"] / entry_close - 1) * 100
    dd10 = (f10["low"].min() / entry_close - 1) * 100

    peak_score = clamp(peak20 / 30 * 40, 0, 40)
    close_score = clamp(close20 / 15 * 30, 0, 30)
    dd_score = clamp(((10 + dd10) / 10) * 30, 0, 30)
    score = peak_score + close_score + dd_score

    return round(score, 1), {
        "peak20": round(float(peak20), 2),
        "close20": round(float(close20), 2),
        "dd10": round(float(dd10), 2),
    }


def score_extension_risk(row: pd.Series) -> tuple[float, dict]:
    score = 0.0
    score += clamp((row["dist20"] - 5) * 3, 0, 25)
    score += clamp((row["dist60"] - 10) * 1.8, 0, 25)
    score += clamp((row["dist120"] - 15) * 1.2, 0, 20)
    score += clamp((row["rsi14"] - 60) * 2.0, 0, 15)
    score += clamp((row["ret14"] - 15) * 1.5, 0, 15)
    return round(clamp(score), 1), {
        "dist20": round(float(row["dist20"]), 2),
        "dist60": round(float(row["dist60"]), 2),
        "dist120": round(float(row["dist120"]), 2),
        "rsi14": round(float(row["rsi14"]), 2),
        "ret14": round(float(row["ret14"]), 2),
    }


def label_result(result_score: float) -> str:
    if result_score >= 75:
        return "good"
    if result_score >= 50:
        return "ok"
    return "bad"


def main() -> None:
    with open(CASES_PATH, encoding="utf-8") as f:
        data = json.load(f)

    by_key = defaultdict(list)
    for case in data["cases"]:
        by_key[(case["market"], case["ticker"])].append(case)

    output = {
        "generated_at": pd.Timestamp.now(tz="Asia/Seoul").isoformat(),
        "cases": [],
    }

    for (market, ticker), cases in by_key.items():
        dates = sorted(pd.Timestamp(c["date"]) for c in cases)
        start = (dates[0] - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
        end = (dates[-1] + pd.Timedelta(days=40)).strftime("%Y-%m-%d")
        history = fetch_history(market, ticker, start, end)
        if history.empty:
            continue

        for case in cases:
            dt = pd.Timestamp(case["date"])
            if dt not in history.index:
                continue
            row = history.loc[dt]
            pos = history.index.get_loc(dt)
            future = history.iloc[pos + 1 : pos + 21]

            buyable_score, buyable_details = score_buyable(row)
            result_score, result_details = score_result(future, float(row["close"]))
            extension_risk, extension_details = score_extension_risk(row)

            output["cases"].append(
                {
                    "ticker": case["ticker"],
                    "name": case["name"],
                    "market": case["market"],
                    "date": case["date"],
                    "classification": case["classification"],
                    "buyable_score": round(float(buyable_score), 1),
                    "result_score": round(float(result_score), 1),
                    "extension_risk_score": round(float(extension_risk), 1),
                    "result_label": label_result(result_score),
                    "buyable_details": buyable_details,
                    "result_details": result_details,
                    "extension_details": extension_details,
                }
            )

    output["cases"] = sorted(output["cases"], key=lambda x: (x["market"], x["ticker"], x["date"]))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"wrote {len(output['cases'])} scored cases to {OUT_PATH}")


if __name__ == "__main__":
    main()
