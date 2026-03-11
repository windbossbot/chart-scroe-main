# Daily Score Backup (2026-03-11)

## Purpose

- 일봉 점수 교정 전/후를 따로 보관한다.
- 교정 결과가 오히려 안 좋아질 경우 바로 비교/복구할 수 있게 한다.
- 기준 파일: `chart_score_app.py`
- 백업 범위: `score_position()`의 `buyable_score`, `turning_score` 관련 핵심 규칙

## Before

`git HEAD` 기준 수정 전 `score_position()` 핵심:

```python
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
```

수정 전 특징:

- `20/60` 중심
- `월봉 5선` 없음
- `480일선` 없음
- `52주 신고가/신저가` 없음
- `지지 터치`보다 `대충 좋은 구조`를 넓게 잡는 편

## After

2026-03-11 교정 후 `score_position()` 핵심:

```python
daily_buyable = 0.0
daily_buyable += 18 if -4.5 <= daily["dist20"] <= 1.5 else 0
daily_buyable += 22 if -2.5 <= daily["dist60"] <= 3.5 else 0
daily_buyable += 10 if -2.5 <= daily["dist120"] <= 5.5 else 0
daily_buyable += 6 if -3 <= daily["dist240"] <= 6 else 0
daily_buyable += 10 if -3 <= daily["dist480"] <= 8 else 0
daily_buyable += 12 if -9 <= daily["dist20"] <= -2 and daily["close"] > daily["ma60"] else 0
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
```

수정 후 특징:

- `지지 이평선 접촉` 우선
- `480일선` 반영
- `월봉 5선` 반영
- `52주 신고가 근처` 약한 가점
- `머리 위 장기이평 부담` 감점 강화

## Backtest Memo

- 수정 전 broad daily backtest:
  - `buyable >= 75`: `avg_close20 2.56`, `avg_dd20 -6.83`, `close>0 52.5%`
- 수정 후 broad daily backtest:
  - `buyable >= 75`: `avg_close20 4.21`, `avg_dd20 -6.59`, `close>0 57.1%`

## Rollback Hint

- 완전 롤백이 필요하면 `git show HEAD:chart_score_app.py` 기준의 `score_position()`로 되돌린다.
- 부분 롤백이 필요하면 이 문서의 `Before` 블록만 기준으로 `buyable_score` 로직을 복구한다.
