import importlib.util
import json
from pathlib import Path

import pandas as pd
from pykrx import stock


ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "chart_score_app.py"
NOTES_PATH = ROOT / "_cache" / "chart_case_notes.json"
REPORT_PATH = ROOT / "_cache" / "operating_compare_2026-03-11.md"


def load_app_module():
    spec = importlib.util.spec_from_file_location("chart_score_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def simulate_midterm_exit(df: pd.DataFrame, idx: int) -> dict[str, float] | None:
    fut = df.iloc[idx + 1 : idx + 121]
    if fut.empty:
        return None
    entry = float(df.iloc[idx]["close"])
    exit_row = fut.iloc[-1]
    hold = len(fut)
    for offset, (_, row) in enumerate(fut.iterrows(), start=1):
        if pd.notna(row["ma120"]) and row["close"] < row["ma120"]:
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
            for i in range(700, len(daily) - 121):
                dt = daily.index[i]
                d = daily.iloc[i]
                w = weekly.loc[:dt].iloc[-1]
                m = monthly.loc[:dt].iloc[-1]
                scores = app.score_position(d, w, m)
                profile = app.classify_trade_horizon(d, w, m, scores)
                if profile["trade_horizon"] != "중기":
                    continue
                sim = simulate_midterm_exit(daily, i)
                if sim is None:
                    continue
                filters = app.evaluate_operating_filters(d, w, m, scores, profile)
                rows.append(
                    {
                        "buyable": float(scores["buyable_score"]),
                        "base": bool(scores["buyable_score"] >= 65),
                        "proposed": bool(scores["buyable_score"] >= 65 and filters["atr_compression"] and filters["bb_compression"]),
                        **sim,
                    }
                )
        except Exception:
            continue

    df = pd.DataFrame(rows)
    base_df = df[df["base"]]
    proposed_df = df[df["proposed"]]

    lines = [
        "# Operating Compare (2026-03-11)",
        "",
        "기존 중기 운용 기준과 신규 운용 기준(ATR + 밴드 압축 동시 확인)을 비교한 결과입니다.",
        "",
    ]
    lines.extend(block("기존 중기 기준", summarize(base_df)))
    lines.append("")
    lines.extend(block("신규 중기 기준", summarize(proposed_df)))
    lines.append("")
    if len(base_df) and len(proposed_df):
        delta_ret = round(float(proposed_df["ret"].mean() - base_df["ret"].mean()), 2)
        delta_win = round(float((proposed_df["ret"] > 0).mean() * 100 - (base_df["ret"] > 0).mean() * 100), 1)
        delta_dd = round(float(proposed_df["dd"].mean() - base_df["dd"].mean()), 2)
        lines += [
            "## Delta",
            "",
            f"- avg_ret delta `{delta_ret}`",
            f"- win_pct delta `{delta_win}`",
            f"- avg_dd delta `{delta_dd}`",
            "",
        ]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(REPORT_PATH)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
