import importlib.util
import json
from pathlib import Path

import pandas as pd
from pykrx import stock


ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "chart_score_app.py"
NOTES_PATH = ROOT / "_cache" / "chart_case_notes.json"
REPORT_PATH = ROOT / "_cache" / "six_way_backtest_2026-03-11.md"


def load_app_module():
    spec = importlib.util.spec_from_file_location("chart_score_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def classify_regime_alt(daily: pd.Series, weekly: pd.Series, monthly: pd.Series) -> str:
    ma10 = monthly.get("ma10")
    regime = "중간"
    if pd.notna(ma10) and monthly["close"] > ma10 and weekly["close"] > weekly["ma60"] and daily["ma20"] > daily["ma60"]:
        regime = "강세"
    elif (pd.notna(ma10) and monthly["close"] < ma10) or daily["close"] < daily["ma120"]:
        regime = "약세"
    return regime


def classify_trade_horizon_alt(daily: pd.Series, weekly: pd.Series, monthly: pd.Series, scores: dict) -> dict:
    regime = classify_regime_alt(daily, weekly, monthly)
    trade_type = "중기"
    reasons: list[str] = []

    short_ready = (
        regime == "강세"
        and weekly["close"] > weekly["ma20"]
        and weekly["close"] > weekly["ma60"]
        and daily["ma20"] > daily["ma60"]
        and daily["runup30"] > 8
        and scores.get("breakout_setup_score", 0) >= 55
    )
    long_ready = (
        regime == "약세"
        or daily["close"] < daily["ma120"]
        or (-3 <= daily["dist240"] <= 6)
        or (-3 <= daily["dist480"] <= 8)
    )

    if short_ready:
        trade_type = "단기"
        reasons = ["급등/가속형", "20/60 중심 추세 대응", "5/20/60 분할 매도 우선"]
    elif long_ready:
        trade_type = "장기"
        reasons = ["전환/장기이평 반응형", "240/480 중심 해석", "120/240/480 이탈을 느리게 대응"]
    else:
        reasons = ["일반 추세 눌림형", "60/120 중심 매수", "120일선 이탈 매도 우선"]

    return {"trade_horizon": trade_type, "trade_horizon_notes": reasons, "regime_label": regime}


def simulate_trade(df: pd.DataFrame, idx: int, trade_type: str) -> dict[str, float] | None:
    fut = df.iloc[idx + 1 :]
    if fut.empty:
        return None
    entry = float(df.iloc[idx]["close"])
    if trade_type == "단기":
        fut = fut.iloc[:60]
        if fut.empty:
            return None
        weights = [("ma5", 0.4), ("ma20", 0.3), ("ma60", 0.3)]
        rets = []
        holds = []
        for ma_col, weight in weights:
            exit_row = fut.iloc[-1]
            hold = len(fut)
            for offset, (_, row) in enumerate(fut.iterrows(), start=1):
                if pd.notna(row[ma_col]) and row["close"] < row[ma_col]:
                    exit_row = row
                    hold = offset
                    break
            rets.append(weight * float((exit_row["close"] / entry - 1) * 100))
            holds.append(weight * hold)
        return {
            "ret": float(sum(rets)),
            "peak": float((fut["high"].max() / entry - 1) * 100),
            "dd": float((fut["low"].min() / entry - 1) * 100),
            "hold": float(sum(holds)),
        }

    if trade_type == "중기":
        fut = fut.iloc[:120]
        if fut.empty:
            return None
        exit_ma = "ma120"
    else:
        fut = fut.iloc[:240]
        if fut.empty:
            return None
        entry_row = df.iloc[idx]
        exit_ma = "ma240" if entry_row["close"] >= entry_row["ma240"] else "ma480"

    exit_row = fut.iloc[-1]
    hold = len(fut)
    for offset, (_, row) in enumerate(fut.iterrows(), start=1):
        if pd.notna(row[exit_ma]) and row["close"] < row[exit_ma]:
            exit_row = row
            hold = offset
            break
    sliced = fut.iloc[:hold]
    return {
        "ret": float((exit_row["close"] / entry - 1) * 100),
        "peak": float((sliced["high"].max() / entry - 1) * 100),
        "dd": float((sliced["low"].min() / entry - 1) * 100),
        "hold": float(hold),
    }


def summarize(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {"count": 0}
    return {
        "count": int(len(df)),
        "avg_ret": round(float(df["ret"].mean()), 2),
        "avg_peak": round(float(df["peak"].mean()), 2),
        "avg_dd": round(float(df["dd"].mean()), 2),
        "avg_hold": round(float(df["hold"].mean()), 2),
        "win_pct": round(float((df["ret"] > 0).mean() * 100), 1),
    }


def block(title: str, stats: dict[str, float]) -> list[str]:
    if not stats.get("count"):
        return [f"- `{title}`", "  - count `0`"]
    return [
        f"- `{title}`",
        f"  - count `{stats['count']}`",
        f"  - avg_ret `{stats['avg_ret']}`",
        f"  - avg_peak `{stats['avg_peak']}`",
        f"  - avg_dd `{stats['avg_dd']}`",
        f"  - avg_hold `{stats['avg_hold']}`",
        f"  - win_pct `{stats['win_pct']}`",
    ]


def main() -> None:
    app = load_app_module()
    notes = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    tickers = sorted({c["ticker"] for c in notes["cases"] if c.get("market") == "KR"})

    rows = []
    for ticker in tickers:
        try:
            daily = app.add_indicators(app.normalize_ohlcv(stock.get_market_ohlcv_by_date("20170101", "20260311", ticker)))
            if daily.empty or len(daily) < 700:
                continue
            weekly = app.add_indicators(app.resample_ohlcv(daily[["open", "high", "low", "close", "volume"]], "W-FRI"))
            monthly = app.add_indicators(app.resample_ohlcv(daily[["open", "high", "low", "close", "volume"]], "MS"))
            monthly["ma10"] = monthly["close"].rolling(10).mean()

            for i in range(700, len(daily) - 241):
                dt = daily.index[i]
                d = daily.iloc[i]
                w = weekly.loc[:dt].iloc[-1]
                m = monthly.loc[:dt].iloc[-1]
                scores = app.score_position(d, w, m)
                profile = app.classify_trade_horizon(d, w, m, scores)
                filters = app.evaluate_operating_filters(d, w, m, scores, profile)
                plan = app.get_trade_plan(profile)

                profile_alt = classify_trade_horizon_alt(d, w, m, scores)
                plan_alt = app.get_trade_plan(profile_alt)

                sim_base = simulate_trade(daily, i, profile["trade_horizon"])
                sim_alt = simulate_trade(daily, i, profile_alt["trade_horizon"])
                if sim_base is None or sim_alt is None:
                    continue

                rows.append(
                    {
                        "regime_base": scores["buyable_score"] >= plan["entry_threshold"],
                        "regime_prop": scores["buyable_score"] >= plan_alt["entry_threshold"],
                        "indicator_base": scores["buyable_score"] >= plan["entry_threshold"],
                        "indicator_prop": scores["buyable_score"] >= plan["entry_threshold"] and filters["rs_positive"] and filters["atr_compression"] and filters["bb_compression"],
                        "operating_base": profile["trade_horizon"] == "중기" and scores["buyable_score"] >= 65,
                        "operating_prop": profile["trade_horizon"] == "중기" and scores["buyable_score"] >= 65 and filters["atr_compression"] and filters["bb_compression"],
                        "ret_base": sim_base["ret"],
                        "peak_base": sim_base["peak"],
                        "dd_base": sim_base["dd"],
                        "hold_base": sim_base["hold"],
                        "ret_alt": sim_alt["ret"],
                        "peak_alt": sim_alt["peak"],
                        "dd_alt": sim_alt["dd"],
                        "hold_alt": sim_alt["hold"],
                    }
                )
        except Exception:
            continue

    df = pd.DataFrame(rows)

    variants = [
        ("기존 1 레짐 기준", "regime_base", "base"),
        ("제언 적용 1-1 레짐 기준", "regime_prop", "alt"),
        ("기존 2 지표 기준", "indicator_base", "base"),
        ("제언 적용 2-2 지표 기준", "indicator_prop", "base"),
        ("기존 3 운용 기준", "operating_base", "base"),
        ("제언 적용 3-3 운용 기준", "operating_prop", "base"),
    ]

    lines = [
        "# Six-Way Backtest (2026-03-11)",
        "",
        "기존 1/2/3과 제언 적용 1-1/2-2/3-3을 같은 데이터로 비교한 결과입니다.",
        "",
        "## Assumptions",
        "",
        "- `1-1 레짐 기준`은 외부 제언을 반영해 `월봉 5선` 대신 `월봉 10선`을 사용한 대안으로 가정",
        "- `2-2 지표 기준`은 외부 제언을 반영해 `RS 양수 + ATR 압축 + 밴드 압축`을 동시 적용",
        "- `3-3 운용 기준`은 중기 메인 운용에 `ATR 압축 + 밴드 압축` 동시 확인을 추가",
        "",
    ]

    for title, mask_col, source in variants:
        mask = df[mask_col]
        subset = df[mask]
        if source == "base":
            stats = summarize(subset.rename(columns={"ret_base": "ret", "peak_base": "peak", "dd_base": "dd", "hold_base": "hold"})[["ret", "peak", "dd", "hold"]])
        else:
            stats = summarize(subset.rename(columns={"ret_alt": "ret", "peak_alt": "peak", "dd_alt": "dd", "hold_alt": "hold"})[["ret", "peak", "dd", "hold"]])
        lines.extend(block(title, stats))
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_PATH)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
