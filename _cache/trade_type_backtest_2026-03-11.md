# Trade Type Backtest (2026-03-11)

단기 / 중기 / 장기 자리 분류 후, 타입별 매수-매도 시뮬레이션 결과입니다.

## Type Summary

- `단기`
  - count `2785`
  - avg_ret `2.53`
  - avg_peak `27.78`
  - avg_dd `-13.48`
  - avg_hold `11.51`
  - win_pct `38.0`
  - big_win_pct `60.0`

- `중기`
  - count `13372`
  - avg_ret `13.59`
  - avg_peak `42.44`
  - avg_dd `-11.45`
  - avg_hold `63.78`
  - win_pct `42.1`
  - big_win_pct `61.4`

- `장기`
  - count `29524`
  - avg_ret `5.62`
  - avg_peak `20.91`
  - avg_dd `-5.9`
  - avg_hold `34.55`
  - win_pct `32.8`
  - big_win_pct `21.2`

## Threshold By Type

### 단기

- `buyable>=0`
  - count `2785`
  - avg_ret `2.53`
  - avg_peak `27.78`
  - avg_dd `-13.48`
  - avg_hold `11.51`
  - win_pct `38.0`
  - big_win_pct `60.0`

- `buyable>=55`
  - count `895`
  - avg_ret `2.38`
  - avg_peak `28.64`
  - avg_dd `-13.03`
  - avg_hold `10.23`
  - win_pct `39.2`
  - big_win_pct `63.5`

- `buyable>=65`
  - count `360`
  - avg_ret `2.18`
  - avg_peak `30.14`
  - avg_dd `-13.69`
  - avg_hold `9.84`
  - win_pct `39.4`
  - big_win_pct `68.3`

- `buyable>=75`
  - count `42`
  - avg_ret `2.63`
  - avg_peak `31.67`
  - avg_dd `-10.8`
  - avg_hold `5.33`
  - win_pct `23.8`
  - big_win_pct `69.0`

### 중기

- `buyable>=0`
  - count `13372`
  - avg_ret `13.59`
  - avg_peak `42.44`
  - avg_dd `-11.45`
  - avg_hold `63.78`
  - win_pct `42.1`
  - big_win_pct `61.4`

- `buyable>=55`
  - count `1985`
  - avg_ret `9.8`
  - avg_peak `32.03`
  - avg_dd `-9.36`
  - avg_hold `56.27`
  - win_pct `38.8`
  - big_win_pct `55.1`

- `buyable>=65`
  - count `787`
  - avg_ret `11.04`
  - avg_peak `31.96`
  - avg_dd `-8.23`
  - avg_hold `56.21`
  - win_pct `40.3`
  - big_win_pct `57.9`

- `buyable>=75`
  - count `319`
  - avg_ret `11.37`
  - avg_peak `30.51`
  - avg_dd `-6.76`
  - avg_hold `52.18`
  - win_pct `40.1`
  - big_win_pct `54.2`

### 장기

- `buyable>=0`
  - count `29524`
  - avg_ret `5.62`
  - avg_peak `20.91`
  - avg_dd `-5.9`
  - avg_hold `34.55`
  - win_pct `32.8`
  - big_win_pct `21.2`

- `buyable>=55`
  - count `669`
  - avg_ret `8.68`
  - avg_peak `34.69`
  - avg_dd `-5.35`
  - avg_hold `76.04`
  - win_pct `30.8`
  - big_win_pct `46.0`

- `buyable>=65`
  - count `281`
  - avg_ret `8.02`
  - avg_peak `35.44`
  - avg_dd `-5.52`
  - avg_hold `65.45`
  - win_pct `22.4`
  - big_win_pct `43.4`

- `buyable>=75`
  - count `94`
  - avg_ret `3.59`
  - avg_peak `23.57`
  - avg_dd `-5.89`
  - avg_hold `80.15`
  - win_pct `33.0`
  - big_win_pct `56.4`

## Mixed Summary

```text
           count  avg_ret  avg_peak  avg_dd  avg_hold  win_pct  big_win_pct
threshold                                                                  
0          45681     7.76     27.63   -7.98     41.70     35.8         35.3
55          3549     7.72     31.68   -9.53     48.38     37.4         55.5
65          1428     8.22     32.19   -9.07     46.34     36.6         57.7
75           455     8.95     29.19   -6.95     53.63     37.1         56.0
```
