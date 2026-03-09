import argparse
import json
from dataclasses import dataclass

import pandas as pd
from pykrx import stock


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
    df = df.rename(columns=mapping)
    df.index = pd.to_datetime(df.index)
    return df


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = pd.DataFrame()
    out["open"] = df["open"].resample(rule).first()
    out["high"] = df["high"].resample(rule).max()
    out["low"] = df["low"].resample(rule).min()
    out["close"] = df["close"].resample(rule).last()
    out["volume"] = df["volume"].resample(rule).sum()
    return out.dropna(subset=["open", "high", "low", "close"])


def add_common_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["ma120"] = df["close"].rolling(120).mean()

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
    df["volume_ma20"] = df["volume"].rolling(20).mean()
    df["volume_ratio_20"] = df["volume"] / df["volume_ma20"]
    df["distance_ma20_pct"] = (df["close"] / df["ma20"] - 1) * 100
    df["distance_ma60_pct"] = (df["close"] / df["ma60"] - 1) * 100
    return df


def score_band(value: float, low: float, high: float, soft_margin: float = 0.0) -> float:
    if pd.isna(value):
        return 0.0
    if low <= value <= high:
        return 1.0
    if soft_margin <= 0:
        return 0.0
    if value < low:
        dist = low - value
    else:
        dist = value - high
    return max(0.0, 1.0 - dist / soft_margin)


def score_binary(cond: bool) -> float:
    return 1.0 if cond else 0.0


@dataclass
class PatternScore:
    name: str
    score: float
    reasons: list[str]


def weighted_score(parts: list[tuple[str, float, float]]) -> tuple[float, list[str]]:
    total_weight = sum(weight for _, _, weight in parts)
    raw = sum(value * weight for _, value, weight in parts)
    score = round((raw / total_weight) * 100, 1) if total_weight else 0.0
    reasons = [f"{label}: {round(value * 100)}" for label, value, _ in parts]
    return score, reasons


def score_a(daily: pd.Series, weekly: pd.Series, monthly: pd.Series) -> PatternScore:
    parts = [
        ("월20선 위", score_binary(monthly["close"] > monthly["ma20"]), 1.2),
        ("주20/60선 위", score_binary((weekly["close"] > weekly["ma20"]) or (weekly["close"] > weekly["ma60"])), 1.2),
        ("일60선 위", score_binary(daily["close"] > daily["ma60"]), 1.2),
        ("20이격 적합", score_band(daily["distance_ma20_pct"], -5.0, 2.0, 3.0), 1.4),
        ("RSI 적합", score_band(daily["rsi14"], 35.0, 55.0, 10.0), 1.0),
        ("거래량 과열 아님", score_band(daily["volume_ratio_20"], 0.3, 1.2, 0.6), 0.8),
        ("고이격 아님", score_band(abs(daily["distance_ma20_pct"]), 0.0, 6.0, 4.0), 1.2),
    ]
    score, reasons = weighted_score(parts)
    return PatternScore("A", score, reasons)


def score_b(daily: pd.Series, weekly: pd.Series, monthly: pd.Series) -> PatternScore:
    parts = [
        ("월20선 위", score_binary(monthly["close"] > monthly["ma20"]), 1.0),
        ("주20/60선 위", score_binary((weekly["close"] > weekly["ma20"]) or (weekly["close"] > weekly["ma60"])), 1.0),
        ("일60선 위", score_binary(daily["close"] > daily["ma60"]), 1.4),
        ("일20선 아래", score_binary(daily["close"] < daily["ma20"]), 1.2),
        ("20이격 적합", score_band(daily["distance_ma20_pct"], -10.0, -3.0, 3.0), 1.4),
        ("RSI 적합", score_band(daily["rsi14"], 25.0, 40.0, 8.0), 1.0),
        ("거래량 과열 아님", score_band(daily["volume_ratio_20"], 0.3, 1.3, 0.7), 0.6),
    ]
    score, reasons = weighted_score(parts)
    return PatternScore("B", score, reasons)


def score_c(daily: pd.Series, weekly: pd.Series, monthly: pd.Series) -> PatternScore:
    ma_gap_pct = abs(daily["ma20"] - daily["ma60"]) / daily["close"] * 100 if daily["close"] else 999.0
    parts = [
        ("월20선 위", score_binary(monthly["close"] > monthly["ma20"]), 1.0),
        ("주20/60선 위", score_binary((weekly["close"] > weekly["ma20"]) or (weekly["close"] > weekly["ma60"])), 1.0),
        ("일20선 위", score_binary(daily["close"] > daily["ma20"]), 1.2),
        ("일60선 위", score_binary(daily["close"] > daily["ma60"]), 1.2),
        ("20이격 적합", score_band(daily["distance_ma20_pct"], -1.0, 3.0, 2.0), 1.2),
        ("이평 수렴", score_band(ma_gap_pct, 0.0, 6.0, 4.0), 1.4),
        ("RSI 적합", score_band(daily["rsi14"], 40.0, 60.0, 8.0), 0.8),
        ("고이격 아님", score_band(abs(daily["distance_ma20_pct"]), 0.0, 5.0, 3.0), 1.6),
    ]
    score, reasons = weighted_score(parts)
    return PatternScore("C", score, reasons)


def fetch_latest_frame(ticker: str, end_date: str | None = None) -> tuple[str, pd.Timestamp, pd.Series, pd.Series, pd.Series]:
    end = end_date or pd.Timestamp.today().strftime("%Y%m%d")
    df = normalize_ohlcv(stock.get_market_ohlcv_by_date("20200101", end, ticker))
    df = add_common_indicators(df)
    if df.empty:
        raise ValueError(f"No data for ticker {ticker}")

    weekly = resample_ohlcv(df, "W-FRI")
    weekly = add_common_indicators(weekly)

    monthly = resample_ohlcv(df, "MS")
    monthly = add_common_indicators(monthly)

    latest_dt = df.index[-1]
    latest_daily = df.iloc[-1]
    latest_weekly = weekly.loc[:latest_dt].iloc[-1]
    latest_monthly = monthly.loc[:latest_dt].iloc[-1]
    name = stock.get_market_ticker_name(ticker)
    return name, latest_dt, latest_daily, latest_weekly, latest_monthly


def main() -> None:
    parser = argparse.ArgumentParser(description="Score current chart position against A/B/C pattern rules.")
    parser.add_argument("ticker", help="KR ticker, e.g. 000150")
    parser.add_argument("--date", help="Optional end date YYYYMMDD", default=None)
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    name, latest_dt, daily, weekly, monthly = fetch_latest_frame(args.ticker, args.date)
    scores = [
        score_a(daily, weekly, monthly),
        score_b(daily, weekly, monthly),
        score_c(daily, weekly, monthly),
    ]
    scores.sort(key=lambda x: x.score, reverse=True)

    payload = {
        "ticker": args.ticker,
        "name": name,
        "date": latest_dt.strftime("%Y-%m-%d"),
        "daily": {
            "close": round(float(daily["close"]), 2),
            "ma20": round(float(daily["ma20"]), 2),
            "ma60": round(float(daily["ma60"]), 2),
            "rsi14": round(float(daily["rsi14"]), 2),
            "distance_ma20_pct": round(float(daily["distance_ma20_pct"]), 2),
            "distance_ma60_pct": round(float(daily["distance_ma60_pct"]), 2),
            "volume_ratio_20": round(float(daily["volume_ratio_20"]), 2),
        },
        "scores": [{"pattern": s.name, "score": s.score, "reasons": s.reasons} for s in scores],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"{payload['name']} ({payload['ticker']}) {payload['date']}")
    print(
        "close={close} ma20={ma20} ma60={ma60} rsi14={rsi14} dist20={distance_ma20_pct}% "
        "dist60={distance_ma60_pct}% vr20={volume_ratio_20}".format(**payload["daily"])
    )
    for s in payload["scores"]:
        print(f"{s['pattern']}형 {s['score']}%")
        print("  " + ", ".join(s["reasons"]))


if __name__ == "__main__":
    main()
