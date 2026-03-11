# Recalibration Snapshot (2026-03-11)

## What Changed

- `RSI`, `박스권`, `고점 대비 눌림` 보조 가중 축소
- 강세/중간 핵심 이평선 가점에 `기울기 양수` 조건 추가
- 약세 구간은 `240`보다 `480` 비중을 더 크게 조정
- `52주 신저가권` 감점 추가
- `100점 포화`를 줄이기 위해 전반 가점을 보수적으로 축소

## Why

- 분리 백테스트에서 강한 축은 `월봉 5선`, `주봉 60선`, `52주 신고가 근처`
- 약했던 축은 `touch240`, `touch60`, `touch20`, `rsi_band`
- 사용자 기준상 메인은 여전히 `이평선`, 보조 축은 과하게 점수화하지 않는 편이 맞음

## Daily Backtest After Trim

- `buyable >= 55`
  - `count 4471`
  - `avg_close20 5.77%`
  - `avg_peak20 15.04%`
  - `avg_dd20 -6.65%`
  - `close>0 60.2%`

- `buyable >= 65`
  - `count 1861`
  - `avg_close20 5.78%`
  - `avg_peak20 14.65%`
  - `avg_dd20 -6.14%`
  - `close>0 61.7%`

- `buyable >= 75`
  - `count 584`
  - `avg_close20 5.35%`
  - `avg_peak20 13.47%`
  - `avg_dd20 -5.48%`
  - `close>0 62.7%`

- `buyable >= 85`
  - `count 118`
  - `avg_close20 7.87%`
  - `avg_peak20 15.65%`
  - `avg_dd20 -5.26%`
  - `close>0 66.1%`

## Interpretation

- 고득점이 훨씬 희소해졌고 `100점 남발`은 사라짐
- `75+`는 예전보다 적게 찍히지만 손실 방어가 더 나아짐
- `85+`는 매우 드물지만 질은 좋아짐
