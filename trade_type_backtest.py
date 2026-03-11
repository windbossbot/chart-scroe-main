import importlib.util
import json
from pathlib import Path

import pandas as pd
from pykrx import stock


ROOT = Path(__file__).resolve().parent
NOTES_PATH = ROOT / "_cache" / "chart_case_notes.json"
REPORT_PATH = ROOT / "_cache" / "trade_type_backtest_2026-03-11.md"
APP_PATH = ROOT / "chart_score_app.py"


def load_app_module():
    spec = importlib.util.spec_from_file_location("chart_score_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def blended_short_exit(df: pd.DataFrame, idx: int, max_bars: int = 60) -> dict[str, float] | None:
    fut = df.iloc[idx + 1 : idx + 1 + max_bars]
    if fut.empty:
        return None
    entry = float(df.iloc[idx]["close"])
    weights = [("ma5", 0.4), ("ma20", 0.3), ("ma60", 0.3)]
    exit_returns = []
    exit_days = []
    for ma_col, weight in weights:
        exit_row = fut.iloc[-1]
        exit_day = len(fut)
        for offset, (_, row) in enumerate(fut.iterrows(), start=1):
            ma_val = row.get(ma_col)
            if pd.notna(ma_val) and row["close"] < ma_val:
                exit_row = row
                exit_day = offset
                break
        exit_returns.append(weight * float((exit_row["close"] / entry - 1) * 100))
        exit_days.append(weight * exit_day)
    return {
        "ret": float(sum(exit_returns)),
        "peak": float((fut["high"].max() / entry - 1) * 100),
        "dd": float((fut["low"].min() / entry - 1) * 100),
        "hold": float(sum(exit_days)),
    }


def single_exit(df: pd.DataFrame, idx: int, ma_col: str, max_bars: int) -> dict[str, float] | None:
    fut = df.iloc[idx + 1 : idx + 1 + max_bars]
    if fut.empty:
        return None
    entry = float(df.iloc[idx]["close"])
    exit_row = fut.iloc[-1]
    hold = len(fut)
    for offset, (_, row) in enumerate(fut.iterrows(), start=1):
        ma_val = row.get(ma_col)
        if pd.notna(ma_val) and row["close"] < ma_val:
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


def simulate_trade(df: pd.DataFrame, idx: int, trade_type: str) -> dict[str, float] | None:
    if trade_type == "단기":
        return blended_short_exit(df, idx, 60)
    if trade_type == "중기":
        return single_exit(df, idx, "ma120", 120)
    entry = df.iloc[idx]
    ma_col = "ma240" if entry["close"] >= entry["ma240"] else "ma480"
    return single_exit(df, idx, ma_col, 240)


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
        "big_win_pct": round(float((df["peak"] >= 12).mean() * 100), 1),
    }


def format_block(title: str, summary: dict[str, float]) -> list[str]:
    if not summary.get("count"):
        return [f"- `{title}`", "  - count `0`"]
    return [
        f"- `{title}`",
        f"  - count `{summary['count']}`",
        f"  - avg_ret `{summary['avg_ret']}`",
        f"  - avg_peak `{summary['avg_peak']}`",
        f"  - avg_dd `{summary['avg_dd']}`",
        f"  - avg_hold `{summary['avg_hold']}`",
        f"  - win_pct `{summary['win_pct']}`",
        f"  - big_win_pct `{summary['big_win_pct']}`",
    ]


def main() -> None:
    app = load_app_module()
    notes = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    tickers = sorted({c["ticker"] for c in notes["cases"] if c.get("market") == "KR"})

    rows = []
    for ticker in tickers:
        daily = app.add_indicators(app.normalize_ohlcv(stock.get_market_ohlcv_by_date("20180101", "20260311", ticker)))
        if daily.empty:
            continue
        weekly = app.add_indicators(app.resample_ohlcv(daily[["open", "high", "low", "close", "volume"]], "W-FRI"))
        monthly = app.add_indicators(app.resample_ohlcv(daily[["open", "high", "low", "close", "volume"]], "MS"))
        for i in range(500, len(daily) - 241):
            dt = daily.index[i]
            d = daily.iloc[i]
            w = weekly.loc[:dt].iloc[-1]
            m = monthly.loc[:dt].iloc[-1]
            scores = app.score_position(d, w, m)
            profile = app.classify_trade_horizon(d, w, m, scores)
            sim = simulate_trade(daily, i, profile["trade_horizon"])
            if sim is None:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "date": dt.strftime("%Y-%m-%d"),
                    "buyable": float(scores["buyable_score"]),
                    "turning": float(scores["turning_score"]),
                    "trade_type": profile["trade_horizon"],
                    **sim,
                }
            )

    df = pd.DataFrame(rows)
    thresholds = [0, 55, 65, 75]
    report_lines = [
        "# Trade Type Backtest (2026-03-11)",
        "",
        "단기 / 중기 / 장기 자리 분류 후, 타입별 매수-매도 시뮬레이션 결과입니다.",
        "",
        "## Type Summary",
        "",
    ]

    for trade_type in ["단기", "중기", "장기"]:
        trade_df = df[df["trade_type"] == trade_type]
        report_lines.extend(format_block(trade_type, summarize(trade_df)))
        report_lines.append("")

    report_lines += [
        "## Threshold By Type",
        "",
    ]
    for trade_type in ["단기", "중기", "장기"]:
        report_lines.append(f"### {trade_type}")
        report_lines.append("")
        trade_df = df[df["trade_type"] == trade_type]
        for th in thresholds:
            hit = trade_df if th == 0 else trade_df[trade_df["buyable"] >= th]
            report_lines.extend(format_block(f"buyable>={th}", summarize(hit)))
            report_lines.append("")

    mix_rows = []
    for th in thresholds:
        hit = df if th == 0 else df[df["buyable"] >= th]
        summary = summarize(hit)
        summary["threshold"] = th
        mix_rows.append(summary)
    mix_df = pd.DataFrame(mix_rows).set_index("threshold")
    report_lines += [
        "## Mixed Summary",
        "",
        "```text",
        mix_df.to_string(),
        "```",
        "",
    ]

    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    print(REPORT_PATH)
    print("\n".join(report_lines[:60]))


if __name__ == "__main__":
    main()
