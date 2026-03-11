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
SUPPORT_SCORE_MAX = 10.0


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
    out["hh20"] = out["high"].rolling(20).max().shift(1)
    out["from_hh20"] = (out["close"] / out["hh20"] - 1) * 100
    out["hh252"] = out["high"].rolling(252).max()
    out["from_52h"] = (out["close"] / out["hh252"] - 1) * 100
    box_high = out["high"].rolling(20).max().shift(1)
    box_low = out["low"].rolling(20).min().shift(1)
    out["box_range_pct"] = (box_high - box_low) / out["close"] * 100
    return out


def score_position(daily: pd.Series, weekly: pd.Series, monthly: pd.Series) -> dict:
    regime = "중간"
    if monthly["close"] > monthly["ma5"] and weekly["close"] > weekly["ma60"] and daily["ma20"] > daily["ma60"]:
        regime = "강세"
    elif monthly["close"] < monthly["ma5"] or daily["close"] < daily["ma120"]:
        regime = "약세"

    daily_buyable = 0.0
    if regime == "강세":
        daily_buyable += 22 if -4.5 <= daily["dist20"] <= 1.5 else 0
        daily_buyable += 20 if -2.5 <= daily["dist60"] <= 3.5 else 0
        daily_buyable += 6 if -2.5 <= daily["dist120"] <= 5.5 else 0
        daily_buyable += 10 if -9 <= daily["dist20"] <= -2 and daily["close"] > daily["ma60"] else 0
    elif regime == "중간":
        daily_buyable += 12 if -4.5 <= daily["dist20"] <= 1.5 else 0
        daily_buyable += 22 if -2.5 <= daily["dist60"] <= 3.5 else 0
        daily_buyable += 16 if -2.5 <= daily["dist120"] <= 5.5 else 0
        daily_buyable += 10 if -8 <= daily["dist20"] <= -2 and daily["close"] > daily["ma60"] else 0
    else:
        daily_buyable += 6 if -2.5 <= daily["dist120"] <= 5.5 else 0
        daily_buyable += 10 if -3 <= daily["dist240"] <= 6 else 0
        daily_buyable += 16 if -3 <= daily["dist480"] <= 8 else 0

    daily_buyable += 8 if 34 <= daily["rsi14"] <= 56 else 0
    daily_buyable += 8 if daily["vr20"] <= 1.0 else 0
    daily_buyable += 4 if 1.0 < daily["vr20"] <= 1.2 else 0
    daily_buyable += 8 if 10 <= daily["box_range_pct"] <= 32 else 0
    daily_buyable += 8 if -14 <= daily["from_hh20"] <= -4 else 0
    daily_buyable += 4 if -12 <= daily["from_52h"] <= -2 else 0
    daily_buyable -= 18 if daily["close"] < daily["ma60"] and daily["close"] < daily["ma120"] else 0
    daily_buyable -= 10 if daily["close"] < daily["ma20"] and daily["ma20_slope5"] < 0 else 0
    daily_buyable -= 18 if daily["dist20"] > 6 else 0
    daily_buyable -= 12 if daily["ret14"] > 18 else 0
    daily_buyable -= 12 if daily["dist240"] < -8 else 0
    daily_buyable -= 20 if daily["dist480"] < -6 else 0
    daily_buyable -= 6 if daily["close"] < daily["ma20"] and 0 <= daily["dist120"] <= 8 else 0
    daily_buyable -= 6 if daily["close"] < daily["ma20"] and 0 <= daily["dist240"] <= 10 else 0

    weekly_buyable = 0.0
    weekly_buyable += 6 if weekly["close"] > weekly["ma60"] else 0
    weekly_buyable += 4 if weekly["close"] > weekly["ma20"] else 0
    weekly_buyable += 3 if weekly["ma20_slope5"] > 0 else 0

    monthly_buyable = 0.0
    monthly_buyable += 8 if monthly["close"] > monthly["ma5"] else 0
    monthly_buyable += 3 if monthly["close"] > monthly["ma20"] else 0
    monthly_buyable += 3 if monthly["ma20_slope5"] > 0 else 0
    monthly_buyable -= 16 if monthly["close"] < monthly["ma5"] and monthly["ma5_slope5"] < 0 else 0

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
    monthly_turning += 8 if monthly["close"] > monthly["ma5"] else 0
    monthly_turning += 5 if monthly["close"] > monthly["ma20"] else 0
    monthly_turning += 3 if monthly["ma20_slope5"] > 0 else 0
    monthly_turning -= 10 if monthly["close"] < monthly["ma5"] and monthly["ma5_slope5"] < 0 else 0

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

    breakout_setup = 0.0
    breakout_notes: list[str] = []
    if daily["runup30"] > 0:
        breakout_setup += 12
        breakout_notes.append("최근 30일 상승 추세 유지")
    if 0 <= daily["dist120"] <= 8:
        breakout_setup += 20
        breakout_notes.append("120일선 근처 지지")
    elif 0 <= daily["dist240"] <= 10:
        breakout_setup += 16
        breakout_notes.append("240일선 근처 지지")
    if -10 <= daily["dist60"] <= 10:
        breakout_setup += 14
        breakout_notes.append("60일선 근처 매매 근거")
    if -18 <= daily["from_hh20"] <= -6:
        breakout_setup += 16
        breakout_notes.append("고점 대비 눌림 후 재시도")
    if 45 <= daily["rsi14"] <= 60:
        breakout_setup += 10
        breakout_notes.append("RSI 재가속 가능 구간")
    if 0.6 <= daily["vr20"] <= 1.6:
        breakout_setup += 10
        breakout_notes.append("거래량 과열 전 정리")
    if 8 <= daily["box_range_pct"] <= 32:
        breakout_setup += 8
        breakout_notes.append("박스 압축 범위 유지")
    if weekly["ma20_slope5"] > 0:
        breakout_setup += 6
        breakout_notes.append("주봉 기울기 양호")
    if monthly["ma20_slope5"] > 0:
        breakout_setup += 4
        breakout_notes.append("월봉 기울기 양호")
    if daily["close"] < daily["ma60"]:
        breakout_setup -= 12
        breakout_notes.append("60일선 하회")
    if daily["ret14"] < -15:
        breakout_setup -= 10
        breakout_notes.append("최근 낙폭 과다")
    if daily["vr20"] > 2.5 and daily["from_hh20"] > 0:
        breakout_setup -= 12
        breakout_notes.append("이미 거래량 터진 돌파")
    if daily["dist20"] > 12:
        breakout_setup -= 10
        breakout_notes.append("20일선 과열 이격")

    return {
        "regime_label": regime,
        "buyable_score": round(clamp(buyable), 1),
        "turning_score": round(clamp(turning), 1),
        "extension_risk_score": round(clamp(extension), 1),
        "fear_score": round(clamp(fear), 1),
        "breakout_setup_score": round(clamp(breakout_setup), 1),
        "breakout_setup_notes": breakout_notes,
        "daily_core_buyable": round(clamp(daily_buyable), 1),
        "weekly_bonus_buyable": round(clamp(weekly_buyable), 1),
        "monthly_bonus_buyable": round(clamp(monthly_buyable), 1),
        "daily_core_turning": round(clamp(daily_turning), 1),
        "weekly_bonus_turning": round(clamp(weekly_turning), 1),
        "monthly_bonus_turning": round(clamp(monthly_turning), 1),
    }


def build_comment(scores: dict, daily: pd.Series) -> str:
    tone = []

    if daily["close"] >= daily["ma20"] and daily["close"] >= daily["ma60"]:
        tone.append("단기와 중기 이평이 아래에서 받쳐주는 구조라 매매 근거는 비교적 선명합니다.")
    elif daily["close"] >= daily["ma20"] and daily["close"] < daily["ma60"]:
        tone.append("20일선은 회복했지만 60일선이 위에 있어, 반등보다는 아직 저항 확인 구간에 가깝습니다.")
    elif daily["close"] < daily["ma20"] and daily["close"] >= daily["ma60"]:
        tone.append("60일선은 지키고 있지만 20일선 아래라, 눌림으로 볼지 약세 전환으로 볼지 애매한 자리입니다.")
    else:
        tone.append("20일선과 60일선이 모두 위에 있어 이평이 지지보다 저항처럼 느껴질 수 있습니다.")

    if scores["extension_risk_score"] >= 70:
        tone.append("이미 많이 터진 자리라 추격 부담이 크고, 메인 매수 시스템보다는 단기 대응 영역에 가깝습니다.")
    elif scores["extension_risk_score"] >= 45:
        tone.append("강한 종목일 수는 있지만 이격이 벌어져 있어 편하게 버티는 자리는 아닐 가능성이 큽니다.")
    elif scores["fear_score"] >= 60:
        tone.append("공포형 눌림 성격이 강해 자리 자체는 볼 만하지만 손절 기준을 분명히 잡아야 합니다.")
    elif scores["buyable_score"] >= 75 and scores["turning_score"] >= 60:
        tone.append("정석 눌림 후보에 가깝고, 지지 유지가 확인되면 실전 매수까지 이어질 수 있는 구조입니다.")
    elif scores["buyable_score"] >= 55:
        tone.append("사고 싶은 자리 후보로는 볼 수 있지만, 한 단계 더 눌리거나 지지 확인이 붙으면 더 편해질 수 있습니다.")
    else:
        tone.append("가능성은 있어도 지금 바로 누르기엔 근거가 조금 부족한 편입니다.")

    if scores.get("breakout_setup_score", 0) >= 75:
        tone.append("최근 패턴은 공포 뒤 급등 전조 후보에 가까워, 눌림 후 재가속을 노리는 관점에선 의미가 있습니다.")
    elif scores.get("breakout_setup_score", 0) >= 55:
        tone.append("급등 전조 흔적은 일부 보이지만, 아직은 확률 높은 자리로 단정하기엔 확인이 더 필요합니다.")

    if daily["dist120"] > 0 and daily["dist120"] <= 6:
        tone.append("120일선 근처라 중기 추세 확인선이 가까운 점은 심리적으로 도움이 됩니다.")
    elif daily["dist120"] < 0 and abs(daily["dist120"]) <= 6:
        tone.append("120일선 아래에서 움직여 중기선이 머리 위 저항처럼 느껴질 수 있습니다.")
    elif daily["dist240"] > 0 and daily["dist240"] <= 10:
        tone.append("240일선 근처라 장기선 반응을 같이 보는 쪽이 좋겠습니다.")

    return " ".join(tone[:3])


def safe_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def parse_number_text(value: str | None) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "").replace("%", "").replace("배", "").replace("원", "")
    if text in {"", "-", "N/A"}:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


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
    base_date = end_date or get_latest_kr_trading_date()
    base_dt = pd.to_datetime(base_date, format="%Y%m%d", errors="coerce")
    if pd.isna(base_dt):
        base_dt = pd.Timestamp.now()

    for offset in range(0, 15):
        dt = (base_dt - pd.Timedelta(days=offset)).strftime("%Y%m%d")
        try:
            df = stock.get_market_fundamental_by_date(dt, dt, ticker)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        row = df.iloc[-1]
        return {
            "source": "pykrx",
            "date": dt,
            "BPS": safe_float(row.get("BPS")),
            "PER": safe_float(row.get("PER")),
            "PBR": safe_float(row.get("PBR")),
            "EPS": safe_float(row.get("EPS")),
            "DIV": safe_float(row.get("DIV")),
            "DPS": safe_float(row.get("DPS")),
        }

    try:
        url = f"https://finance.naver.com/item/main.naver?code={ticker}"
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15).text
        import re

        def extract(metric_id: str) -> float:
            match = re.search(rf'id="{metric_id}">(.*?)</em>', html)
            return parse_number_text(match.group(1) if match else None)

        per = extract("_per")
        eps = extract("_eps")
        pbr = extract("_pbr")
        div = extract("_dvr")
        if any(v > 0 for v in [per, eps, pbr, div]):
            return {
                "source": "naver",
                "date": "-",
                "BPS": 0.0,
                "PER": per,
                "PBR": pbr,
                "EPS": eps,
                "DIV": div,
                "DPS": 0.0,
            }
    except Exception:
        pass

    return {"source": "-", "date": "-"}


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
            market_score = min(market_score, 6.0)
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
        f_date = str(fundamentals.get("date", "-"))
        f_source = str(fundamentals.get("source", "-"))
        per = safe_float(fundamentals.get("PER"), default=-1)
        pbr = safe_float(fundamentals.get("PBR"), default=-1)
        eps = safe_float(fundamentals.get("EPS"))
        div = safe_float(fundamentals.get("DIV"))

        if 0 < per <= 25:
            fundamental_score += 1.0
            details.append("펀더멘털: PER 과열 아님")
        if 0 < pbr <= 3.5:
            fundamental_score += 0.7
            details.append("펀더멘털: PBR 부담 낮음")
        if eps > 0:
            fundamental_score += 0.8
            details.append("펀더멘털: EPS 양수")
        if div >= 1.0:
            dividend_score += 1.0
            details.append("배당: DIV 1% 이상")

        fundamental_rows = [
            {"항목": "시장구분", "값": segment},
            {"항목": "펀더 출처", "값": f_source},
            {"항목": "펀더 기준일", "값": f_date},
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
            fundamental_score += 1.0
            details.append("펀더멘털: PER 과열 아님")
        if eps > 0:
            fundamental_score += 0.8
            details.append("펀더멘털: EPS 양수")
        if roe >= 8:
            fundamental_score += 0.8
            details.append("펀더멘털: ROE 양호")
        if div_yield >= 1.0:
            dividend_score += 1.0
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
        market_score = min(market_score, 8.0)
        details.append("코인: 펀더멘털 이력 백테스트가 어려워 점수 반영 제외")
        fundamental_rows = [
            {"항목": "환경 해석", "값": "BTC/ETH 강도 기반 약한 보정"},
            {"항목": "펀더멘털 처리", "값": "코인은 점수 제외"},
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
    today_date = datetime.now().strftime("%Y%m%d")

    with st.form("score_form"):
        col0, col1, col2 = st.columns([0.8, 1.2, 1])
        with col0:
            asset_type = st.selectbox("자산", ["KR", "US", "CRYPTO"], index=0)
        with col1:
            default_ticker = "005930" if asset_type == "KR" else ("NVDA" if asset_type == "US" else "BTC")
            ticker = st.text_input("티커", value=default_ticker, max_chars=20)
        with col2:
            end_date = st.text_input("기준일(YYYYMMDD)", value=today_date, disabled=asset_type == "CRYPTO")
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

    total_score = round(
        clamp(
            scores["buyable_score"] * 0.5
            + scores["turning_score"] * 0.2
            + (100 - scores["extension_risk_score"]) * 0.15
            + (100 - scores["fear_score"]) * 0.05
            + support["support_score"] * 0.1
        ),
        1,
    )

    m0, m1, m2, m3, m4, m5, m6 = st.columns(7)
    m0.metric("총점", f"{total_score:.1f}")
    m1.metric("사고 싶은 자리", f"{scores['buyable_score']:.1f}")
    m2.metric("전환 가능성", f"{scores['turning_score']:.1f}")
    m3.metric("과열 부담", f"{scores['extension_risk_score']:.1f}")
    m4.metric("공포 강도", f"{scores['fear_score']:.1f}")
    m5.metric("보조 보정", f"{support['support_score']:.1f}", f"합산 {support['adjusted_buyable_score']:.1f}")
    m6.metric("급등 전조", f"{scores['breakout_setup_score']:.1f}")

    with st.expander("점수 분해"):
        st.caption(f"현재 상태 분류: {scores.get('regime_label', '-')}")
        d1, d2, d3 = st.columns(3)
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
        with d3:
            notes = scores.get("breakout_setup_notes", [])
            bullet_text = "\n".join([f"- {note}" for note in notes[:8]]) if notes else "- 아직 뚜렷한 전조가 없습니다."
            st.markdown(
                f"""
                **급등 전조 분해**
                - 점수: `{scores['breakout_setup_score']:.1f}`
                {bullet_text}
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

    st.markdown("#### 보조 지표 / 환경 점수")
    s1, s2, s3 = st.columns(3)
    s1.metric("시장/지수 보정", f"{support['market_score']:.1f} / 6")
    s2.metric("펀더멘털 보정", f"{support['fundamental_score']:.1f} / 3")
    s3.metric("배당/메이저 보정", f"{support['dividend_score']:.1f} / 1")

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

    if asset_type == "KR":
        st.caption("국장 펀더멘털은 현재 기본 소스 응답이 불안정해 참고용으로만 표시합니다. 필요하면 다른 소스로 교체할 수 있습니다.")

    case_scores = load_case_scores()
    if not case_scores.empty:
        same = case_scores[case_scores["ticker"].astype(str) == payload["ticker"]].copy()
        if not same.empty:
            same = same.sort_values(["buyable_score", "result_score"], ascending=[False, False])
            st.markdown("#### 저장된 과거 사례")
            st.dataframe(
                same[["date", "classification", "buyable_score", "result_score", "extension_risk_score", "result_label"]],
                use_container_width=True,
                hide_index=True,
            )


if __name__ == "__main__":
    main()
