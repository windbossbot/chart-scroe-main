# Six-Way Backtest (2026-03-11)

기존 1/2/3과 제언 적용 1-1/2-2/3-3을 같은 데이터로 비교한 결과입니다.

## Assumptions

- `1-1 레짐 기준`은 외부 제언을 반영해 `월봉 5선` 대신 `월봉 10선`을 사용한 대안으로 가정
- `2-2 지표 기준`은 외부 제언을 반영해 `RS 양수 + ATR 압축 + 밴드 압축`을 동시 적용
- `3-3 운용 기준`은 중기 메인 운용에 `ATR 압축 + 밴드 압축` 동시 확인을 추가

- `기존 1 레짐 기준`
  - count `1488`
  - avg_ret `9.8`
  - avg_peak `33.1`
  - avg_dd `-7.02`
  - avg_hold `64.21`
  - win_pct `35.4`

- `제언 적용 1-1 레짐 기준`
  - count `1510`
  - avg_ret `9.49`
  - avg_peak `32.65`
  - avg_dd `-7.07`
  - avg_hold `63.78`
  - win_pct `34.8`

- `기존 2 지표 기준`
  - count `1488`
  - avg_ret `9.8`
  - avg_peak `33.1`
  - avg_dd `-7.02`
  - avg_hold `64.21`
  - win_pct `35.4`

- `제언 적용 2-2 지표 기준`
  - count `858`
  - avg_ret `12.69`
  - avg_peak `38.27`
  - avg_dd `-7.49`
  - avg_hold `70.77`
  - win_pct `40.3`

- `기존 3 운용 기준`
  - count `769`
  - avg_ret `10.86`
  - avg_peak `31.17`
  - avg_dd `-8.22`
  - avg_hold `55.37`
  - win_pct `39.8`

- `제언 적용 3-3 운용 기준`
  - count `502`
  - avg_ret `13.47`
  - avg_peak `35.23`
  - avg_dd `-8.49`
  - avg_hold `59.39`
  - win_pct `43.6`
