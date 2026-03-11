import json
from collections import defaultdict
from pathlib import Path

import pandas as pd
from pykrx import stock


ROOT = Path(__file__).resolve().parent
NOTES_PATH = ROOT / "_cache" / "chart_case_notes.json"
SCORES_PATH = ROOT / "_cache" / "chart_case_scores.json"


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
        out[f"ma{n}_slope5"] = out[f"ma{n}"].diff(5)

    delta = out["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    out["rsi14"] = 100 - (100 / (1 + rs))

    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr14"] = tr.rolling(14).mean()
    out["atr_pct"] = out["atr14"] / out["close"] * 100
    out["vr20"] = out["volume"] / out["volume"].rolling(20).mean()
    out["ret14"] = (out["close"] / out["close"].shift(14) - 1) * 100
    out["runup30"] = (out["close"] / out["close"].shift(30) - 1) * 100
    hh20 = out["high"].rolling(20).max().shift(1)
    ll20 = out["low"].rolling(20).min().shift(1)
    out["from_hh20"] = (out["close"] / hh20 - 1) * 100
    out["box_range_pct"] = (hh20 - ll20) / out["close"] * 100
    hh252 = out["high"].rolling(252).max()
    ll252 = out["low"].rolling(252).min()
    out["from_52h"] = (out["close"] / hh252 - 1) * 100
    out["from_52l"] = (out["close"] / ll252 - 1) * 100
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
    scores = json.loads(SCORES_PATH.read_text(encoding="utf-8"))
    score_map = {(c["market"], c["ticker"], c["date"]): c for c in scores["cases"]}

    cases = []
    for case in notes["cases"]:
        if case["market"] != "KR":
            continue
        merged = dict(case)
        merged.update(score_map.get((case["market"], case["ticker"], case["date"]), {}))
        cases.append(merged)

    factor_defs = {
        "new_high_zone": lambda d, w, m: -12 <= d["from_52h"] <= -2,
        "new_low_zone": lambda d, w, m: 0 <= d["from_52l"] <= 12,
        "touch20": lambda d, w, m: -4.5 <= d["dist20"] <= 1.5,
        "touch60": lambda d, w, m: -2.5 <= d["dist60"] <= 3.5,
        "touch120": lambda d, w, m: -2.5 <= d["dist120"] <= 5.5,
        "touch240": lambda d, w, m: -3 <= d["dist240"] <= 6,
        "touch480": lambda d, w, m: -3 <= d["dist480"] <= 8,
        "under20_above60": lambda d, w, m: -9 <= d["dist20"] <= -2 and d["close"] > d["ma60"],
        "month_above5": lambda d, w, m: pd.notna(m["ma5"]) and m["close"] > m["ma5"],
        "week_above60": lambda d, w, m: pd.notna(w["ma60"]) and w["close"] > w["ma60"],
        "box_ready": lambda d, w, m: 10 <= d["box_range_pct"] <= 32,
        "volume_dry": lambda d, w, m: d["vr20"] <= 1.0,
        "rsi_band": lambda d, w, m: 34 <= d["rsi14"] <= 56,
        "pullback_from_high": lambda d, w, m: -14 <= d["from_hh20"] <= -4,
        "daily_strong_regime": lambda d, w, m: d["ma20"] > d["ma60"] > d["ma120"],
        "daily_mid_regime": lambda d, w, m: d["ma60"] > d["ma120"] and d["ma20"] <= d["ma60"],
        "daily_weak_regime": lambda d, w, m: d["ma240"] > d["ma120"] or d["close"] < d["ma120"],
    }

    histories: dict[str, tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]] = {}
    for ticker in sorted({case["ticker"] for case in cases}):
        daily = add_indicators(
            normalize_ohlcv(stock.get_market_ohlcv_by_date("20180101", "20260311", ticker))
        )
        weekly = add_indicators(resample_ohlcv(daily[["open", "high", "low", "close", "volume"]], "W-FRI"))
        monthly = add_indicators(resample_ohlcv(daily[["open", "high", "low", "close", "volume"]], "MS"))
        histories[ticker] = (daily, weekly, monthly)

    broad_rows = []
    case_rows = []

    for ticker, (daily_df, weekly_df, monthly_df) in histories.items():
        for i in range(500, len(daily_df) - 21):
            dt = daily_df.index[i]
            daily = daily_df.iloc[i]
            weekly = weekly_df.loc[:dt].iloc[-1]
            monthly = monthly_df.loc[:dt].iloc[-1]
            fut = future_stats(daily_df, i)
            for name, fn in factor_defs.items():
                broad_rows.append(
                    {
                        "factor": name,
                        "hit": bool(fn(daily, weekly, monthly)),
                        **fut,
                    }
                )

    for case in cases:
        daily_df, weekly_df, monthly_df = histories[case["ticker"]]
        dt = pd.Timestamp(case["date"])
        if dt not in daily_df.index:
            continue
        daily = daily_df.loc[dt]
        weekly = weekly_df.loc[:dt].iloc[-1]
        monthly = monthly_df.loc[:dt].iloc[-1]
        for name, fn in factor_defs.items():
            case_rows.append(
                {
                    "factor": name,
                    "hit": bool(fn(daily, weekly, monthly)),
                    "result_label": case.get("result_label", "unknown"),
                }
            )

    broad_df = pd.DataFrame(broad_rows)
    case_df = pd.DataFrame(case_rows)

    print("=== DAILY FACTOR BACKTEST ===")
    print("broad bars:", len(broad_df) // len(factor_defs))
    baseline = broad_df[broad_df["factor"] == "touch20"]
    print(
        "baseline avg_peak20",
        round(baseline["peak20"].mean(), 2),
        "avg_close20",
        round(baseline["close20"].mean(), 2),
        "avg_dd20",
        round(baseline["dd20"].mean(), 2),
    )

    summary_rows = []
    for name in factor_defs:
        hit_broad = broad_df[(broad_df["factor"] == name) & (broad_df["hit"])]
        all_case = case_df[case_df["factor"] == name]
        hit_case = all_case[all_case["hit"]]
        good_case = all_case[all_case["result_label"] == "good"]
        summary_rows.append(
            {
                "factor": name,
                "broad_hits": len(hit_broad),
                "hit_rate_pct": round(len(hit_broad) / (len(broad_df) / len(factor_defs)) * 100, 1),
                "avg_peak20": round(hit_broad["peak20"].mean(), 2) if len(hit_broad) else None,
                "avg_close20": round(hit_broad["close20"].mean(), 2) if len(hit_broad) else None,
                "avg_dd20": round(hit_broad["dd20"].mean(), 2) if len(hit_broad) else None,
                "peak_ge_8_pct": round((hit_broad["peak20"] >= 8).mean() * 100, 1) if len(hit_broad) else None,
                "close_pos_pct": round((hit_broad["close20"] > 0).mean() * 100, 1) if len(hit_broad) else None,
                "dd_le_neg8_pct": round((hit_broad["dd20"] <= -8).mean() * 100, 1) if len(hit_broad) else None,
                "case_hit_pct": round(all_case["hit"].mean() * 100, 1) if len(all_case) else None,
                "case_good_hit_pct": round(good_case["hit"].mean() * 100, 1) if len(good_case) else None,
            }
        )

    summary_df = pd.DataFrame(summary_rows).sort_values(
        ["avg_close20", "close_pos_pct", "avg_dd20"],
        ascending=[False, False, False],
    )

    for _, row in summary_df.iterrows():
        print(
            row["factor"],
            "| hits",
            int(row["broad_hits"]),
            "| avg_close20",
            row["avg_close20"],
            "| avg_peak20",
            row["avg_peak20"],
            "| avg_dd20",
            row["avg_dd20"],
            "| close_pos",
            row["close_pos_pct"],
            "| case_hit",
            row["case_hit_pct"],
            "| good_hit",
            row["case_good_hit_pct"],
        )


if __name__ == "__main__":
    main()
