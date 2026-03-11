# Long Horizon Backtest (2026-03-11)

중장기 보유형 관점에서 현재 `buyable_score`를 다시 점검한 결과입니다.

## Sample

- KR bars tested: `50241`
- Universe: `38` tickers from stored KR cases

## 1. Fixed Holding Windows

- `buyable>=0`
  - count `50241`
  - close_5 `0.68`
  - close_10 `1.39`
  - close_20 `2.84`
  - close_60 `9.92`
  - close_120 `22.68`
  - dd_10 `-6.09`
  - dd_20 `-8.51`
  - dd_60 `-13.63`
  - win_60 `56.7`
  - win_120 `61.8`

- `buyable>=55`
  - count `3908`
  - close_5 `1.42`
  - close_10 `2.85`
  - close_20 `4.81`
  - close_60 `11.64`
  - close_120 `23.62`
  - dd_10 `-4.94`
  - dd_20 `-6.91`
  - dd_60 `-11.91`
  - win_60 `59.4`
  - win_120 `64.3`

- `buyable>=65`
  - count `1596`
  - close_5 `1.71`
  - close_10 `3.15`
  - close_20 `4.96`
  - close_60 `11.44`
  - close_120 `24.48`
  - dd_10 `-4.63`
  - dd_20 `-6.5`
  - dd_60 `-11.64`
  - win_60 `61.5`
  - win_120 `66.6`

- `buyable>=75`
  - count `494`
  - close_5 `1.18`
  - close_10 `2.53`
  - close_20 `4.24`
  - close_60 `9.25`
  - close_120 `18.45`
  - dd_10 `-4.22`
  - dd_20 `-5.86`
  - dd_60 `-10.57`
  - win_60 `60.5`
  - win_120 `60.3`

- `buyable>=85`
  - count `102`
  - close_5 `1.63`
  - close_10 `3.22`
  - close_20 `7.09`
  - close_60 `10.32`
  - close_120 `20.31`
  - dd_10 `-4.01`
  - dd_20 `-5.21`
  - dd_60 `-9.28`
  - win_60 `70.6`
  - win_120 `66.7`

## 2. MA Exit Rules

매수 후 `20/60/120`일선을 종가 기준으로 이탈하면 청산, 아니면 최대 120거래일까지 보유합니다.

### exit20

- `buyable>=0`
  - count `50241`
  - exit_20_ret `1.85`
  - exit_20_peak `8.68`
  - exit_20_dd `-3.2`
  - exit_20_hold `7.3`

- `buyable>=55`
  - count `3908`
  - exit_20_ret `1.5`
  - exit_20_peak `6.43`
  - exit_20_dd `-2.21`
  - exit_20_hold `5.27`

- `buyable>=65`
  - count `1596`
  - exit_20_ret `1.17`
  - exit_20_peak `5.66`
  - exit_20_dd `-1.92`
  - exit_20_hold `4.55`

- `buyable>=75`
  - count `494`
  - exit_20_ret `0.67`
  - exit_20_peak `4.57`
  - exit_20_dd `-1.65`
  - exit_20_hold `3.9`

- `buyable>=85`
  - count `102`
  - exit_20_ret `0.02`
  - exit_20_peak `2.63`
  - exit_20_dd `-1.71`
  - exit_20_hold `2.35`

### exit60

- `buyable>=0`
  - count `50241`
  - exit_60_ret `4.27`
  - exit_60_peak `15.78`
  - exit_60_dd `-4.56`
  - exit_60_hold `17.57`

- `buyable>=55`
  - count `3908`
  - exit_60_ret `5.67`
  - exit_60_peak `20.29`
  - exit_60_dd `-5.22`
  - exit_60_hold `22.96`

- `buyable>=65`
  - count `1596`
  - exit_60_ret `4.83`
  - exit_60_peak `18.81`
  - exit_60_dd `-4.86`
  - exit_60_hold `20.24`

- `buyable>=75`
  - count `494`
  - exit_60_ret `1.47`
  - exit_60_peak `10.41`
  - exit_60_dd `-3.25`
  - exit_60_hold `11.45`

- `buyable>=85`
  - count `102`
  - exit_60_ret `1.87`
  - exit_60_peak `11.64`
  - exit_60_dd `-2.9`
  - exit_60_hold `12.85`

### exit120

- `buyable>=0`
  - count `50241`
  - exit_120_ret `7.67`
  - exit_120_peak `21.6`
  - exit_120_dd `-5.99`
  - exit_120_hold `31.43`

- `buyable>=55`
  - count `3908`
  - exit_120_ret `12.99`
  - exit_120_peak `34.91`
  - exit_120_dd `-8.53`
  - exit_120_hold `56.85`

- `buyable>=65`
  - count `1596`
  - exit_120_ret `13.14`
  - exit_120_peak `34.97`
  - exit_120_dd `-8.27`
  - exit_120_hold `56.28`

- `buyable>=75`
  - count `494`
  - exit_120_ret `11.63`
  - exit_120_peak `29.54`
  - exit_120_dd `-6.08`
  - exit_120_hold `48.84`

- `buyable>=85`
  - count `102`
  - exit_120_ret `13.24`
  - exit_120_peak `32.33`
  - exit_120_dd `-5.82`
  - exit_120_hold `58.78`

## 3. Fast And Smooth Follow-Through

좋은 자리를 샀을 때 `바로 오르고 꾸준히 오르는가`를 보기 위한 지표입니다.

- `buyable>=0`
  - count `50241`
  - up5 `0.68`
  - up10 `1.39`
  - dd10 `-6.09`
  - close60 `9.92`
  - peak60 `27.81`
  - clean_run `0.25`
  - fast_run `0.18`
  - clean_run_pct `25.3`
  - fast_run_pct `17.9`

- `buyable>=55`
  - count `3908`
  - up5 `1.42`
  - up10 `2.85`
  - dd10 `-4.94`
  - close60 `11.64`
  - peak60 `29.56`
  - clean_run `0.27`
  - fast_run `0.19`
  - clean_run_pct `27.2`
  - fast_run_pct `19.3`

- `buyable>=65`
  - count `1596`
  - up5 `1.71`
  - up10 `3.15`
  - dd10 `-4.63`
  - close60 `11.44`
  - peak60 `29.25`
  - clean_run `0.28`
  - fast_run `0.2`
  - clean_run_pct `28.4`
  - fast_run_pct `20.0`

- `buyable>=75`
  - count `494`
  - up5 `1.18`
  - up10 `2.53`
  - dd10 `-4.22`
  - close60 `9.25`
  - peak60 `26.73`
  - clean_run `0.26`
  - fast_run `0.18`
  - clean_run_pct `26.1`
  - fast_run_pct `17.8`

- `buyable>=85`
  - count `102`
  - up5 `1.63`
  - up10 `3.22`
  - dd10 `-4.01`
  - close60 `10.32`
  - peak60 `26.17`
  - clean_run `0.34`
  - fast_run `0.21`
  - clean_run_pct `34.3`
  - fast_run_pct `20.6`

## Regime Summary

```text
        close_60  close_120  dd_60  clean_run  fast_run
regime                                                 
중간         15.68      32.83  -9.62       0.35      0.23
강세         12.99      26.50 -13.32       0.27      0.21
약세          6.62      17.90 -14.71       0.22      0.15
```
