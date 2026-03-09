from datetime import datetime
from pathlib import Path
import json

import pandas as pd
import requests
import streamlit as st
import yfinance as yf
from pykrx import stock


CACHE_DIR = Path(__file__).resolve().parent / "_cache"
CASE_SCORES_PATH = CACHE_DIR / "chart_case_scores.json"
SUPPORT_SCORE_MAX = 15.0


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


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
    out = df.rename(columns=mapping).copy()
    out.index = pd.to_datetime(out.index)
    return out


def normalize_bithumb_candles(data: list) -> pd.DataFrame:
    rows = []
    for item in data:
        try:
            ts = pd.to_datetime(int(item[0]), unit="ms")
            rows.append(
                {
                    "date": ts,
                    "open": float(item[1]),
                    "close": float(item[2]),
                    "high": float(item[3]),
                    "low": float(item[4]),
                    "volume": float(item[5]),
                }
            )
        except Exception:
            continue
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    out = pd.DataFrame(rows).set_index("date").sort_index()
    return out[["open", "high", "low", "close", "volume"]]


def normalize_yfinance_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    if isinstance(df.columns, pd.MultiIndex):
        try:
            df = df.xs(df.columns.levels[-1][0], axis=1, level=-1)
        except Exception:
            df = df.droplevel(-1, axis=1)
    out = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    ).copy()
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out = out[["open", "high", "low", "close", "volume"]].dropna(subset=["open", "high", "low", "close"])
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
    for n in [5, 20, 60, 120, 240]:
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
    out["hh20"] = out["high"].rolling(20).max().shift(1)
    out["from_hh20"] = (out["close"] / out["hh20"] - 1) * 100
    box_high = out["high"].rolling(20).max().shift(1)
    box_low = out["low"].rolling(20).min().shift(1)
    out["box_range_pct"] = (box_high - box_low) / out["close"] * 100
    return out


def score_position(daily: pd.Series, weekly: pd.Series, monthly: pd.Series) -> dict:
    daily_buyable = 0.0
    daily_buyable += 25 if daily["close"] > daily["ma60"] else 0
    daily_buyable += 20 if -8 <= daily["dist20"] <= -2 else 0
    daily_buyable += 12 if 0 <= daily["dist60"] <= 6 else 0
    daily_buyable += 10 if 35 <= daily["rsi14"] <= 52 else 0
    daily_buyable += 8 if daily["vr20"] <= 1.3 else 0
    daily_buyable += 8 if 8 <= daily["box_range_pct"] <= 35 else 0
    daily_buyable -= 20 if daily["close"] < daily["ma60"] else 0
    daily_buyable -= 12 if daily["dist120"] > 20 else 0
    daily_buyable -= 10 if daily["runup30"] < 0 else 0

    weekly_buyable = 0.0
    weekly_buyable += 10 if weekly["close"] > weekly["ma20"] else 0
    weekly_buyable += 5 if weekly["ma20_slope5"] > 0 else 0

    monthly_buyable = 0.0
    monthly_buyable += 7 if monthly["close"] > monthly["ma20"] else 0
    monthly_buyable += 3 if monthly["ma20_slope5"] > 0 else 0

    buyable = daily_buyable + weekly_buyable + monthly_buyable

    daily_turning = 0.0
    daily_turning += 25 if daily["close"] > daily["ma60"] else 0
    daily_turning += 18 if -12 <= daily["from_hh20"] <= -3 else 0
    daily_turning += 12 if daily["rsi14"] >= 38 else 0
    daily_turning += 10 if daily["ma60_slope5"] > 0 else 0
    daily_turning += 10 if daily["ma120_slope5"] > 0 else 0
    daily_turning -= 20 if daily["close"] < daily["ma120"] else 0
    daily_turning -= 15 if daily["ret14"] < -12 else 0

    weekly_turning = 0.0
    weekly_turning += 10 if weekly["close"] > weekly["ma20"] else 0
    weekly_turning += 5 if weekly["ma20_slope5"] > 0 else 0

    monthly_turning = 0.0
    monthly_turning += 7 if monthly["close"] > monthly["ma20"] else 0
    monthly_turning += 3 if monthly["ma20_slope5"] > 0 else 0

    turning = daily_turning + weekly_turning + monthly_turning

    extension = 0.0
    extension += clamp((daily["dist20"] - 5) * 3, 0, 30)
    extension += clamp((daily["dist60"] - 10) * 1.5, 0, 25)
    extension += clamp((daily["dist120"] - 15) * 1.2, 0, 20)
    extension += clamp((daily["rsi14"] - 60) * 1.8, 0, 15)
    extension += clamp((daily["ret14"] - 15) * 1.2, 0, 10)

    fear = 0.0
    fear += 30 if daily["dist20"] <= -5 else 0
    fear += 20 if abs(daily["dist60"]) <= 4 else 0
    fear += 15 if abs(daily["dist120"]) <= 5 else 0
    fear += 15 if daily["rsi14"] <= 40 else 0
    fear += 10 if daily["from_hh20"] <= -10 else 0
    fear += 10 if daily["ret14"] <= -8 else 0

    return {
        "buyable_score": round(clamp(buyable), 1),
        "turning_score": round(clamp(turning), 1),
        "extension_risk_score": round(clamp(extension), 1),
        "fear_score": round(clamp(fear), 1),
        "daily_core_buyable": round(clamp(daily_buyable), 1),
        "weekly_bonus_buyable": round(clamp(weekly_buyable), 1),
        "monthly_bonus_buyable": round(clamp(monthly_buyable), 1),
        "daily_core_turning": round(clamp(daily_turning), 1),
        "weekly_bonus_turning": round(clamp(weekly_turning), 1),
        "monthly_bonus_turning": round(clamp(monthly_turning), 1),
    }


def build_comment(scores: dict, daily: pd.Series) -> str:
    if daily["close"] < daily["ma60"]:
        return "하락/조정 지속 쪽에 가깝습니다. 60일선 재회복 전에는 보수적으로 보는 편이 낫습니다."
    if scores["extension_risk_score"] >= 55:
        return "과열 확장 구간 쪽입니다. 강한 종목일 수는 있지만 정석 눌림 매수와는 거리가 있습니다."
    if scores["buyable_score"] >= 70 and scores["turning_score"] >= 60:
        return "정석 눌림 후보에 가깝습니다. 다만 실제 진입은 지지 유지 여부를 확인하는 쪽이 안전합니다."
    if scores["fear_score"] >= 60:
        return "공포형 눌림 후보입니다. 구조는 맞아도 심리적으로 어려울 수 있어 손절 기준이 중요합니다."
    return "구조는 일부 맞지만 애매한 자리입니다. 더 눌리거나 다시 정리되는지 확인하는 편이 낫습니다."


def safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_reference_ohlcv(symbol: str, end_date: str | None = None) -> pd.DataFrame:
    start = "2020-01-01"
    end = None
    if end_date:
        end_dt = pd.to_datetime(end_date, format="%Y%m%d", errors="coerce")
        if not pd.isna(end_dt):
            end = (end_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    raw = yf.download(symbol, start=start, end=end, auto_adjust=False, progress=False, interval="1d")
    df = normalize_yfinance_ohlcv(raw)
    return add_indicators(df)


def score_reference_strength(row: pd.Series) -> tuple[float, list[str]]:
    score = 0.0
    notes = []
    close = safe_float(row.get("close"))
    ma20 = safe_float(row.get("ma20"))
    ma60 = safe_float(row.get("ma60"))
    rsi14 = safe_float(row.get("rsi14"))
    ret14 = safe_float(row.get("ret14"))

    if close > ma20:
        score += 2.0
        notes.append("종가가 20선 위")
    if close > ma60:
        score += 2.0
        notes.append("종가가 60선 위")
    if ma20 > ma60:
        score += 2.0
        notes.append("20선이 60선 위")
    if 45 <= rsi14 <= 70:
        score += 1.0
        notes.append("RSI가 중강세권")
    if ret14 > 0:
        score += 1.0
        notes.append("최근 14일 수익률 양호")

    return min(score, 8.0), notes


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_kr_latest_fundamentals(ticker: str, end_date: str | None) -> dict:
    date = end_date or get_latest_kr_trading_date()
    df = stock.get_market_fundamental_by_date(date, date, ticker)
    if df is None or df.empty:
        return {}
    row = df.iloc[-1]
    return {
        "BPS": safe_float(row.get("BPS")),
        "PER": safe_float(row.get("PER")),
        "PBR": safe_float(row.get("PBR")),
        "EPS": safe_float(row.get("EPS")),
        "DIV": safe_float(row.get("DIV")),
        "DPS": safe_float(row.get("DPS")),
    }


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_us_fast_info(ticker: str) -> dict:
    info = {}
    tk = yf.Ticker(ticker)
    try:
        fi = getattr(tk, "fast_info", {}) or {}
        info.update(fi)
    except Exception:
        pass
    try:
        base = tk.info or {}
    except Exception:
        base = {}
    info.update(
        {
            "trailingPE": base.get("trailingPE"),
            "forwardPE": base.get("forwardPE"),
            "dividendYield": base.get("dividendYield"),
            "trailingEps": base.get("trailingEps"),
            "returnOnEquity": base.get("returnOnEquity"),
        }
    )
    return info


def build_support_context(asset_type: str, ticker: str, payload: dict, end_date: str | None) -> dict:
    details = []
    market_score = 0.0
    fundamental_score = 0.0
    dividend_score = 0.0
    benchmark_rows: list[dict] = []

    if asset_type == "KR":
        segment = get_kr_market_segment(ticker, end_date)
        index_code = "1001" if segment == "KOSPI" else "2001"
        ref_df = fetch_kr_index_ohlcv(index_code, end_date)
        if not ref_df.empty:
            row = ref_df.iloc[-1]
            market_score, notes = score_reference_strength(row)
            benchmark_rows.append(
                {
                    "항목": segment,
                    "종가": f"{safe_float(row.get('close')):,.2f}",
                    "20선 대비": f"{safe_float(row.get('dist20')):+.2f}%",
                    "60선 대비": f"{safe_float(row.get('dist60')):+.2f}%",
                    "RSI": f"{safe_float(row.get('rsi14')):.2f}",
                }
            )
            details.extend([f"시장: {note}" for note in notes])

        fundamentals = fetch_kr_latest_fundamentals(ticker, end_date)
        per = safe_float(fundamentals.get("PER"), default=-1)
        pbr = safe_float(fundamentals.get("PBR"), default=-1)
        eps = safe_float(fundamentals.get("EPS"))
        div = safe_float(fundamentals.get("DIV"))

        if 0 < per <= 25:
            fundamental_score += 2.0
            details.append("펀더멘털: PER 과열 아님")
        if 0 < pbr <= 3.5:
            fundamental_score += 1.5
            details.append("펀더멘털: PBR 부담 낮음")
        if eps > 0:
            fundamental_score += 1.5
            details.append("펀더멘털: EPS 양수")
        if div >= 1.0:
            dividend_score += 2.0
            details.append("배당: DIV 1% 이상")

        fundamental_rows = [
            {"항목": "시장구분", "값": segment},
            {"항목": "PER", "값": "-" if per <= 0 else f"{per:.2f}"},
            {"항목": "PBR", "값": "-" if pbr <= 0 else f"{pbr:.2f}"},
            {"항목": "EPS", "값": "-" if eps == 0 else f"{eps:,.0f}"},
            {"항목": "DIV", "값": "-" if div <= 0 else f"{div:.2f}%"},
        ]

    elif asset_type == "US":
        benchmarks = [("^GSPC", "S&P500"), ("^IXIC", "NASDAQ")]
        for symbol, label in benchmarks:
            ref_df = fetch_reference_ohlcv(symbol, end_date)
            if ref_df.empty:
                continue
            row = ref_df.iloc[-1]
            score, notes = score_reference_strength(row)
            market_score += score / 2
            benchmark_rows.append(
                {
                    "항목": label,
                    "종가": f"{safe_float(row.get('close')):,.2f}",
                    "20선 대비": f"{safe_float(row.get('dist20')):+.2f}%",
                    "60선 대비": f"{safe_float(row.get('dist60')):+.2f}%",
                    "RSI": f"{safe_float(row.get('rsi14')):.2f}",
                }
            )
            details.extend([f"시장: {label} {note}" for note in notes[:2]])

        info = fetch_us_fast_info(ticker)
        trailing_pe = safe_float(info.get("trailingPE"), default=-1)
        forward_pe = safe_float(info.get("forwardPE"), default=-1)
        eps = safe_float(info.get("trailingEps"))
        div_yield = safe_float(info.get("dividendYield")) * 100
        roe = safe_float(info.get("returnOnEquity")) * 100

        if 0 < trailing_pe <= 35 or 0 < forward_pe <= 30:
            fundamental_score += 2.0
            details.append("펀더멘털: PER 과열 아님")
        if eps > 0:
            fundamental_score += 1.5
            details.append("펀더멘털: EPS 양수")
        if roe >= 8:
            fundamental_score += 1.5
            details.append("펀더멘털: ROE 양호")
        if div_yield >= 1.0:
            dividend_score += 2.0
            details.append("배당: dividend yield 1% 이상")

        fundamental_rows = [
            {"항목": "Trailing PE", "값": "-" if trailing_pe <= 0 else f"{trailing_pe:.2f}"},
            {"항목": "Forward PE", "값": "-" if forward_pe <= 0 else f"{forward_pe:.2f}"},
            {"항목": "EPS", "값": "-" if eps == 0 else f"{eps:.2f}"},
            {"항목": "Dividend Yield", "값": "-" if div_yield <= 0 else f"{div_yield:.2f}%"},
            {"항목": "ROE", "값": "-" if roe <= 0 else f"{roe:.2f}%"},
        ]

    else:
        benchmarks = [("BTC-USD", "BTC"), ("ETH-USD", "ETH")]
        for symbol, label in benchmarks:
            ref_df = fetch_reference_ohlcv(symbol, end_date)
            if ref_df.empty:
                continue
            row = ref_df.iloc[-1]
            score, notes = score_reference_strength(row)
            market_score += min(score, 6.0)
            benchmark_rows.append(
                {
                    "항목": label,
                    "종가": f"{safe_float(row.get('close')):,.2f}",
                    "20선 대비": f"{safe_float(row.get('dist20')):+.2f}%",
                    "60선 대비": f"{safe_float(row.get('dist60')):+.2f}%",
                    "RSI": f"{safe_float(row.get('rsi14')):.2f}",
                }
            )
            details.extend([f"코인 환경: {label} {note}" for note in notes[:2]])
        market_score = min(market_score, 12.0)
        symbol = str(payload.get("ticker", "")).upper()
        if symbol in {"BTC", "ETH"}:
            fundamental_score += 2.0
            details.append("코인 특성: 메이저 자산")
        fundamental_rows = [
            {"항목": "환경 해석", "값": "BTC/ETH 강도 기반 약한 보정"},
        ]

    total = clamp(market_score + fundamental_score + dividend_score, 0.0, SUPPORT_SCORE_MAX)
    return {
        "support_score": round(total, 1),
        "market_score": round(market_score, 1),
        "fundamental_score": round(fundamental_score, 1),
        "dividend_score": round(dividend_score, 1),
        "adjusted_buyable_score": round(clamp(payload["scores"]["buyable_score"] + total), 1),
        "details": details,
        "benchmark_rows": benchmark_rows,
        "fundamental_rows": fundamental_rows,
    }


@st.cache_data(show_spinner=False, ttl=3600)
def load_case_scores() -> pd.DataFrame:
    if not CASE_SCORES_PATH.exists():
        return pd.DataFrame()
    try:
        raw = json.loads(CASE_SCORES_PATH.read_text(encoding="utf-8"))
        return pd.DataFrame(raw.get("cases", []))
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=3600)
def get_kr_market_segment(ticker: str, date: str | None = None) -> str:
    base_date = date or get_latest_kr_trading_date()
    try:
        if ticker in stock.get_market_ticker_list(date=base_date, market="KOSPI"):
            return "KOSPI"
        if ticker in stock.get_market_ticker_list(date=base_date, market="KOSDAQ"):
            return "KOSDAQ"
    except Exception:
        pass
    return "KOSPI"


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_kr_index_ohlcv(index_code: str, end_date: str | None = None) -> pd.DataFrame:
    end = end_date or get_latest_kr_trading_date()
    try:
        raw = stock.get_index_ohlcv_by_date("20200101", end, index_code)
        return add_indicators(normalize_ohlcv(raw))
    except Exception:
        fallback_symbol = "^KS11" if index_code == "1001" else "^KQ11"
        return fetch_reference_ohlcv(fallback_symbol, end)


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_kr_payload(ticker: str, end_date: str | None) -> dict:
    end = end_date or datetime.now().strftime("%Y%m%d")
    daily_df = normalize_ohlcv(stock.get_market_ohlcv_by_date("20200101", end, ticker))
    daily_df = add_indicators(daily_df)
    if daily_df.empty:
        raise ValueError("데이터가 없습니다.")
    weekly_df = add_indicators(resample_ohlcv(daily_df, "W-FRI"))
    monthly_df = add_indicators(resample_ohlcv(daily_df, "MS"))
    latest_dt = daily_df.index[-1]
    daily = daily_df.iloc[-1]
    weekly = weekly_df.loc[:latest_dt].iloc[-1]
    monthly = monthly_df.loc[:latest_dt].iloc[-1]
    return {
        "name": stock.get_market_ticker_name(ticker),
        "ticker": ticker,
        "date": latest_dt.strftime("%Y-%m-%d"),
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "scores": score_position(daily, weekly, monthly),
    }


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_bithumb_payload(symbol: str) -> dict:
    ticker = str(symbol).strip().upper().replace("/KRW", "").replace("-KRW", "")
    if not ticker:
        raise ValueError("심볼이 비어 있습니다.")
    url = f"https://api.bithumb.com/public/candlestick/{ticker}_KRW/24h"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    raw = resp.json()
    if str(raw.get("status")) != "0000":
        raise ValueError("빗썸 API 조회 실패")

    daily_df = normalize_bithumb_candles(raw.get("data", []))
    daily_df = add_indicators(daily_df)
    if daily_df.empty:
        raise ValueError("빗썸 캔들 데이터가 없습니다.")
    weekly_df = add_indicators(resample_ohlcv(daily_df, "W-FRI"))
    monthly_df = add_indicators(resample_ohlcv(daily_df, "MS"))
    latest_dt = daily_df.index[-1]
    daily = daily_df.iloc[-1]
    weekly = weekly_df.loc[:latest_dt].iloc[-1]
    monthly = monthly_df.loc[:latest_dt].iloc[-1]
    return {
        "name": f"{ticker}/KRW",
        "ticker": ticker,
        "date": latest_dt.strftime("%Y-%m-%d"),
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "scores": score_position(daily, weekly, monthly),
    }


@st.cache_data(show_spinner=False, ttl=3600)
def fetch_us_payload(symbol: str, end_date: str | None) -> dict:
    ticker = str(symbol).strip().upper()
    if not ticker:
        raise ValueError("티커가 비어 있습니다.")

    start = "2020-01-01"
    if end_date:
        end_dt = pd.to_datetime(end_date, format="%Y%m%d", errors="coerce")
        if pd.isna(end_dt):
            raise ValueError("기준일 형식이 잘못되었습니다.")
        end = (end_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        end = None

    raw = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=False,
        progress=False,
        interval="1d",
    )
    daily_df = normalize_yfinance_ohlcv(raw)
    daily_df = add_indicators(daily_df)
    if daily_df.empty:
        raise ValueError("미국 주식 데이터가 없습니다.")

    weekly_df = add_indicators(resample_ohlcv(daily_df, "W-FRI"))
    monthly_df = add_indicators(resample_ohlcv(daily_df, "MS"))
    latest_dt = daily_df.index[-1]
    daily = daily_df.iloc[-1]
    weekly = weekly_df.loc[:latest_dt].iloc[-1]
    monthly = monthly_df.loc[:latest_dt].iloc[-1]

    try:
        info = yf.Ticker(ticker).fast_info
        name = info.get("shortName") or info.get("longName") or ticker
    except Exception:
        name = ticker

    return {
        "name": name,
        "ticker": ticker,
        "date": latest_dt.strftime("%Y-%m-%d"),
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "scores": score_position(daily, weekly, monthly),
    }


@st.cache_data(show_spinner=False, ttl=3600)
def get_latest_kr_trading_date() -> str:
    base = datetime.now()
    for d in range(0, 15):
        dt = (base - pd.Timedelta(days=d)).strftime("%Y%m%d")
        try:
            out = stock.get_market_ticker_list(date=dt, market="KOSPI")
            if out:
                return dt
        except Exception:
            continue
    return datetime.now().strftime("%Y%m%d")


def main() -> None:
    st.set_page_config(page_title="Dividend Chart Score", layout="wide")
    st.title("Dividend Chart Score")
    st.caption("티커 1개 입력 -> 현재 자리 점수 평가")
    latest_trading_date = get_latest_kr_trading_date()

    with st.form("score_form"):
        col0, col1, col2 = st.columns([0.8, 1.2, 1])
        with col0:
            asset_type = st.selectbox("자산", ["KR", "US", "CRYPTO"], index=0)
        with col1:
            default_ticker = "005930" if asset_type == "KR" else ("NVDA" if asset_type == "US" else "BTC")
            ticker = st.text_input("티커", value=default_ticker, max_chars=20)
        with col2:
            end_date = st.text_input("기준일(YYYYMMDD)", value=latest_trading_date, disabled=asset_type == "CRYPTO")
        submitted = st.form_submit_button("평가", type="primary")

    if not submitted:
        st.info("예시 KR: 005930, 000660 / US: NVDA, TSLA, AAPL / CRYPTO: BTC, ETH, XRP, THE, ES")
        return

    try:
        if asset_type == "KR":
            payload = fetch_kr_payload(str(ticker).strip().zfill(6), str(end_date).strip() or None)
        elif asset_type == "US":
            payload = fetch_us_payload(str(ticker).strip(), str(end_date).strip() or None)
        else:
            payload = fetch_bithumb_payload(str(ticker).strip())
    except Exception as e:
        st.error(f"조회 실패: {e}")
        return

    scores = payload["scores"]
    daily = payload["daily"]
    weekly = payload["weekly"]
    monthly = payload["monthly"]
    support = build_support_context(asset_type, payload["ticker"], payload, str(end_date).strip() or None)

    st.subheader(f"{payload['name']} ({payload['ticker']})")
    st.caption(f"기준일: {payload['date']}")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("사고 싶은 자리", f"{scores['buyable_score']:.1f}")
    m2.metric("전환 가능성", f"{scores['turning_score']:.1f}")
    m3.metric("과열 부담", f"{scores['extension_risk_score']:.1f}")
    m4.metric("공포 강도", f"{scores['fear_score']:.1f}")
    m5.metric("보조 보정", f"{support['support_score']:.1f}", f"합산 {support['adjusted_buyable_score']:.1f}")

    with st.expander("점수 분해"):
        d1, d2 = st.columns(2)
        with d1:
            st.markdown(
                f"""
                **사고 싶은 자리 분해**
                - 일봉 코어: `{scores['daily_core_buyable']:.1f}`
                - 주봉 보정: `{scores['weekly_bonus_buyable']:.1f}`
                - 월봉 보정: `{scores['monthly_bonus_buyable']:.1f}`
                """
            )
        with d2:
            st.markdown(
                f"""
                **전환 가능성 분해**
                - 일봉 코어: `{scores['daily_core_turning']:.1f}`
                - 주봉 보정: `{scores['weekly_bonus_turning']:.1f}`
                - 월봉 보정: `{scores['monthly_bonus_turning']:.1f}`
                """
            )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            f"""
            **일봉**
            - 종가: `{daily['close']:,.0f}`
            - 20일선: `{daily['ma20']:,.0f}` ({daily['dist20']:+.2f}%)
            - 60일선: `{daily['ma60']:,.0f}` ({daily['dist60']:+.2f}%)
            - 120일선: `{daily['ma120']:,.0f}` ({daily['dist120']:+.2f}%)
            - RSI14: `{daily['rsi14']:.2f}`
            """
        )
    with c2:
        st.markdown(
            f"""
            **주봉**
            - 종가: `{weekly['close']:,.0f}`
            - 20주선: `{weekly['ma20']:,.0f}`
            - 60주선: `{weekly['ma60']:,.0f}`
            - RSI14: `{weekly['rsi14']:.2f}`
            """
        )
    with c3:
        st.markdown(
            f"""
            **월봉**
            - 종가: `{monthly['close']:,.0f}`
            - 20월선: `{monthly['ma20']:,.0f}`
            - 60월선: `{monthly['ma60']:,.0f}`
            - RSI14: `{monthly['rsi14']:.2f}`
            """
        )

    st.info(build_comment(scores, daily))

    case_scores = load_case_scores()
    if case_scores.empty:
        return
    same = case_scores[case_scores["ticker"].astype(str) == payload["ticker"]].copy()
    if not same.empty:
        same = same.sort_values(["buyable_score", "result_score"], ascending=[False, False])
        st.markdown("#### 저장된 과거 사례")
        st.dataframe(
            same[["date", "classification", "buyable_score", "result_score", "extension_risk_score", "result_label"]],
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### 보조 지표 / 환경 점수")
    s1, s2, s3 = st.columns(3)
    s1.metric("시장/지수 보정", f"{support['market_score']:.1f} / 8")
    s2.metric("펀더멘털 보정", f"{support['fundamental_score']:.1f} / 5")
    s3.metric("배당/메이저 보정", f"{support['dividend_score']:.1f} / 2")

    if support["details"]:
        st.caption(" | ".join(support["details"][:6]))

    b1, b2 = st.columns(2)
    with b1:
        if support["benchmark_rows"]:
            st.markdown("**시장/지수 강도**")
            st.dataframe(pd.DataFrame(support["benchmark_rows"]), use_container_width=True, hide_index=True)
    with b2:
        if support["fundamental_rows"]:
            st.markdown("**펀더멘털/배당 지표**")
            st.dataframe(pd.DataFrame(support["fundamental_rows"]), use_container_width=True, hide_index=True)

    with st.expander("직접 입력 참고 지표"):
        st.caption("자동점수와 별개로, 실적/배당 같은 참고값을 직접 적어두는 칸입니다.")
        i1, i2, i3, i4 = st.columns(4)
        with i1:
            manual_eps = st.number_input("EPS", value=0.0, step=1.0, format="%.2f")
        with i2:
            manual_per = st.number_input("PER", value=0.0, step=0.1, format="%.2f")
        with i3:
            manual_pbr = st.number_input("PBR", value=0.0, step=0.1, format="%.2f")
        with i4:
            manual_div = st.number_input("배당수익률(%)", value=0.0, step=0.1, format="%.2f")
        manual_note = st.text_input("메모", value="")
        st.dataframe(
            pd.DataFrame(
                [
                    {"항목": "EPS 직접입력", "값": "-" if manual_eps == 0 else f"{manual_eps:,.2f}"},
                    {"항목": "PER 직접입력", "값": "-" if manual_per == 0 else f"{manual_per:.2f}"},
                    {"항목": "PBR 직접입력", "값": "-" if manual_pbr == 0 else f"{manual_pbr:.2f}"},
                    {"항목": "배당수익률 직접입력", "값": "-" if manual_div == 0 else f"{manual_div:.2f}%"},
                    {"항목": "메모", "값": manual_note or "-"},
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
