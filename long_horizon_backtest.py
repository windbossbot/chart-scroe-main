import importlib.util
import json
from pathlib import Path

import pandas as pd
from pykrx import stock


ROOT = Path(__file__).resolve().parent
NOTES_PATH = ROOT / "_cache" / "chart_case_notes.json"
REPORT_PATH = ROOT / "_cache" / "long_horizon_backtest_2026-03-11.md"
APP_PATH = ROOT / "chart_score_app.py"


def load_app_module():
    spec = importlib.util.spec_from_file_location("chart_score_app", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def future_stats(df: pd.DataFrame, idx: int, bars: int) -> dict[str, float] | None:
    fut = df.iloc[idx + 1 : idx + 1 + bars]
    if len(fut) < bars:
        return None
    entry = float(df.iloc[idx]["close"])
    return {
        "close_ret": float((fut.iloc[-1]["close"] / entry - 1) * 100),
        "peak_ret": float((fut["high"].max() / entry - 1) * 100),
        "dd_ret": float((fut["low"].min() / entry - 1) * 100),
    }


def exit_on_ma_break(df: pd.DataFrame, idx: int, ma_col: str, max_bars: int = 120) -> dict[str, float] | None:
    entry = float(df.iloc[idx]["close"])
    fut = df.iloc[idx + 1 : idx + 1 + max_bars]
    if fut.empty:
        return None
    exit_row = fut.iloc[-1]
    hold_days = len(fut)
    for offset, (_, row) in enumerate(fut.iterrows(), start=1):
        ma_val = row.get(ma_col)
        if pd.notna(ma_val) and row["close"] < ma_val:
            exit_row = row
            hold_days = offset
            break
    sliced = fut.iloc[:hold_days]
    return {
        "close_ret": float((exit_row["close"] / entry - 1) * 100),
        "peak_ret": float((sliced["high"].max() / entry - 1) * 100),
        "dd_ret": float((sliced["low"].min() / entry - 1) * 100),
        "hold_days": float(hold_days),
    }


def smooth_run_stats(df: pd.DataFrame, idx: int) -> dict[str, float] | None:
    entry = float(df.iloc[idx]["close"])
    fut5 = df.iloc[idx + 1 : idx + 6]
    fut10 = df.iloc[idx + 1 : idx + 11]
    fut60 = df.iloc[idx + 1 : idx + 61]
    if len(fut5) < 5 or len(fut10) < 10 or len(fut60) < 60:
        return None
    up5 = float((fut5.iloc[-1]["close"] / entry - 1) * 100)
    up10 = float((fut10.iloc[-1]["close"] / entry - 1) * 100)
    dd10 = float((fut10["low"].min() / entry - 1) * 100)
    close60 = float((fut60.iloc[-1]["close"] / entry - 1) * 100)
    peak60 = float((fut60["high"].max() / entry - 1) * 100)
    return {
        "up5": up5,
        "up10": up10,
        "dd10": dd10,
        "close60": close60,
        "peak60": peak60,
        "clean_run": float(up5 > 0 and up10 > 0 and dd10 > -5 and close60 > 0),
        "fast_run": float(up5 > 2 and up10 > 4 and dd10 > -4 and peak60 > 12),
    }


def summarize(df: pd.DataFrame, value_cols: list[str]) -> dict[str, float]:
    out: dict[str, float] = {"count": int(len(df))}
    for col in value_cols:
        out[col] = round(float(df[col].mean()), 2) if len(df) else float("nan")
    return out


def format_summary(label: str, data: dict[str, float], cols: list[str]) -> str:
    parts = [f"- `{label}`", f"  - count `{data['count']}`"]
    for col in cols:
        parts.append(f"  - {col} `{data[col]}`")
    return "\n".join(parts)


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
        for i in range(500, len(daily) - 121):
            dt = daily.index[i]
            d = daily.iloc[i]
            w = weekly.loc[:dt].iloc[-1]
            m = monthly.loc[:dt].iloc[-1]
            scores = app.score_position(d, w, m)
            row = {
                "ticker": ticker,
                "date": dt.strftime("%Y-%m-%d"),
                "buyable": float(scores["buyable_score"]),
                "turning": float(scores["turning_score"]),
                "regime": scores.get("regime_label", "-"),
            }
            ok = True
            for bars in [5, 10, 20, 60, 120]:
                stats = future_stats(daily, i, bars)
                if stats is None:
                    ok = False
                    break
                row[f"close_{bars}"] = stats["close_ret"]
                row[f"peak_{bars}"] = stats["peak_ret"]
                row[f"dd_{bars}"] = stats["dd_ret"]
            if not ok:
                continue
            for ma_col in ["ma20", "ma60", "ma120"]:
                stats = exit_on_ma_break(daily, i, ma_col)
                if stats is None:
                    ok = False
                    break
                suffix = ma_col.replace("ma", "")
                row[f"exit_{suffix}_ret"] = stats["close_ret"]
                row[f"exit_{suffix}_peak"] = stats["peak_ret"]
                row[f"exit_{suffix}_dd"] = stats["dd_ret"]
                row[f"exit_{suffix}_hold"] = stats["hold_days"]
            if not ok:
                continue
            smooth = smooth_run_stats(daily, i)
            if smooth is None:
                continue
            row.update(smooth)
            rows.append(row)

    df = pd.DataFrame(rows)

    thresholds = [0, 55, 65, 75, 85]
    horizon_cols = {
        "fixed": ["close_5", "close_10", "close_20", "close_60", "close_120", "dd_10", "dd_20", "dd_60"],
        "exit20": ["exit_20_ret", "exit_20_peak", "exit_20_dd", "exit_20_hold"],
        "exit60": ["exit_60_ret", "exit_60_peak", "exit_60_dd", "exit_60_hold"],
        "exit120": ["exit_120_ret", "exit_120_peak", "exit_120_dd", "exit_120_hold"],
        "smooth": ["up5", "up10", "dd10", "close60", "peak60", "clean_run", "fast_run"],
    }

    report_lines = [
        "# Long Horizon Backtest (2026-03-11)",
        "",
        "중장기 보유형 관점에서 현재 `buyable_score`를 다시 점검한 결과입니다.",
        "",
        "## Sample",
        "",
        f"- KR bars tested: `{len(df)}`",
        f"- Universe: `{len(tickers)}` tickers from stored KR cases",
        "",
        "## 1. Fixed Holding Windows",
        "",
    ]

    for th in thresholds:
        hit = df if th == 0 else df[df["buyable"] >= th]
        s = summarize(hit, horizon_cols["fixed"])
        report_lines.append(format_summary(f"buyable>={th}", s, horizon_cols["fixed"]))
        if len(hit):
            report_lines.append(f"  - win_60 `{round((hit['close_60'] > 0).mean() * 100, 1)}`")
            report_lines.append(f"  - win_120 `{round((hit['close_120'] > 0).mean() * 100, 1)}`")
        report_lines.append("")

    report_lines += [
        "## 2. MA Exit Rules",
        "",
        "매수 후 `20/60/120`일선을 종가 기준으로 이탈하면 청산, 아니면 최대 120거래일까지 보유합니다.",
        "",
    ]

    for section, cols in [("exit20", horizon_cols["exit20"]), ("exit60", horizon_cols["exit60"]), ("exit120", horizon_cols["exit120"])]:
        report_lines.append(f"### {section}")
        report_lines.append("")
        for th in thresholds:
            hit = df if th == 0 else df[df["buyable"] >= th]
            s = summarize(hit, cols)
            report_lines.append(format_summary(f"buyable>={th}", s, cols))
            report_lines.append("")

    report_lines += [
        "## 3. Fast And Smooth Follow-Through",
        "",
        "좋은 자리를 샀을 때 `바로 오르고 꾸준히 오르는가`를 보기 위한 지표입니다.",
        "",
    ]

    for th in thresholds:
        hit = df if th == 0 else df[df["buyable"] >= th]
        s = summarize(hit, horizon_cols["smooth"])
        report_lines.append(format_summary(f"buyable>={th}", s, horizon_cols["smooth"]))
        if len(hit):
            report_lines.append(f"  - clean_run_pct `{round(hit['clean_run'].mean() * 100, 1)}`")
            report_lines.append(f"  - fast_run_pct `{round(hit['fast_run'].mean() * 100, 1)}`")
        report_lines.append("")

    regime = (
        df.groupby("regime")[["close_60", "close_120", "dd_60", "clean_run", "fast_run"]]
        .mean()
        .round(2)
        .sort_values("close_120", ascending=False)
    )
    report_lines += [
        "## Regime Summary",
        "",
        "```text",
        regime.to_string(),
        "```",
        "",
    ]

    REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
    print(REPORT_PATH)
    print("\n".join(report_lines[:40]))


if __name__ == "__main__":
    main()
