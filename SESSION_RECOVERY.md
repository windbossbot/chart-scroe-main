# Session Recovery

- workspace: `C:\Users\KGWPC\workspace\dividend-chart-score`
- render url: `https://dividend-chart-score.onrender.com/`
- local chart app: `C:\Users\KGWPC\workspace\dividend-chart-score\chart_score_app.py`
- render entry: `C:\Users\KGWPC\workspace\dividend-chart-score\render.yaml`
- keep cache: `_cache/*`
- venv python: `C:\Users\KGWPC\workspace\dividend-chart-score\.venv\Scripts\python.exe`

## Context

- `v1`은 로컬 전용으로 별개다. 이 저장소의 목적은 `v3 차트 점수화`다.
- `v3`는 경량 앱으로 정리했다.
- 기능은 `티커 1개 입력 -> 현재 자리 평가 -> 저장된 과거 사례 비교`가 핵심이다.
- KR 주식은 `pykrx`, 코인은 `Bithumb public candlestick API`를 사용한다.
- 미국 주식은 `yfinance`를 사용한다.
- 기존 스크리너 구조를 다시 섞지 않는다.

## Chart Scoring

- 목적:
  - KR/CRYPTO 티커 입력
  - 현재 자리 점수 확인
  - 저장된 과거 사례와 비교
- 현재 점수 축:
  - `buyable_score`
  - `turning_score`
  - `extension_risk_score`
  - `fear_score`
- 점수는 1차 usable 버전이며, 빗각은 직접 못 보고 수치 흔적으로 근사한다.
- 현재 가중치 원칙:
  - `일봉` 중심
  - `주봉`, `월봉`은 약한 보정 점수
  - `4시간`, `1시간`은 아직 미구현

## Current App Architecture

- 메인 파일:
  - `chart_score_app.py`
- Render 설정:
  - `render.yaml`
- 의존성:
  - `requirements.txt`
- 데이터:
  - KR: `pykrx`
  - US: `yfinance`
  - CRYPTO: `requests` + `Bithumb public API`
- 참고 사례:
  - `_cache/chart_case_notes.json`
  - `_cache/chart_case_scores.json`
- 트레이딩뷰 지표:
  - `kgw_trend_template_v1.pine`
  - 현재 기준 `Pine Script v6`

## Non-Negotiable Architecture

- `v1`을 다시 섞지 않는다.
- 기존 스크리너 UI/조건검색 UI를 `v3`에 다시 붙이지 않는다.
- `v3`는 `단일 종목 평가기`로 유지한다.
- 필요한 공유는 로직/아이디어 수준만 허용하고, UI/구조는 별개다.

## Chart Calibration Notes

- 사람 해석의 핵심 축:
  - `구조적으로 좋은 자리`
  - `실제로 사기 편한 자리`
  - `무서운 자리`
  - `늦은 자리`
- 강한 감점 요소:
  - 신저가 진행
  - 하락 추세 지속
  - 횡보 중인데 상승 후 눌림으로 착각한 경우
  - 빗각 미돌파
- 추가로 계속 수치화할 대상:
  - 최근 20일 고점 대비 위치
  - 최근 30일 상승폭
  - 박스권/횡보 길이
  - 20/60/120 이평 간격
  - 빗각 아래 반복 도전 흔적

## Render Deploy

- GitHub repo:
  - `https://github.com/windbossbot/dividend-screener-v3`
- visibility:
  - `PRIVATE`
- 현재 `render.yaml` 기준:
  - rootDir: `.`
  - build: `pip install -r requirements.txt`
  - start: `streamlit run chart_score_app.py --server.port $PORT --server.address 0.0.0.0`

## Local Run

```powershell
cd C:\Users\KGWPC\workspace\dividend-chart-score
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run chart_score_app.py --server.port 8501
```

## After Deploy

- 앱 들어가서 먼저 확인할 것:
  - 자산 `KR`
  - 예시 티커: `005930`, `000660`, `035720`, `086520`
  - 자산 `US`
  - 예시 티커: `NVDA`, `TSLA`, `AAPL`
  - 자산 `CRYPTO`
  - 예시 티커: `BTC`, `ETH`, `XRP`
- 점수가 이상한 종목이 나오면, 그 케이스를 다시 사용자 기준으로 보정한다.

## Current Status

- 누적 사례: `127`
- 종목/자산: `46`
- 상태:
  - `후보군 압축 + 사람 최종판단` 용도로 usable
  - 완전자동 판정기는 아님
  - 다음 단계는 Render 실사용 후 보정

## Real Goal

- 최종 목표:
  - `내가 먼저 고른 자리`와 `사용자가 실제로 고를 자리`가 `95% 이상` 일치하도록 보정
- 이 프로젝트의 핵심은:
  - 자동매매 완성이 아니라
  - `과거 차트에서 사용자가 선호하는 매수자리 패턴`을 최대한 복원하는 것

## Non-Negotiables

- 시장보다 `차트 자리`가 우선이다.
- 사용자는 `빗각`, `지지저항`, `20/60/120/240`, `주봉`, `월봉`을 함께 본다.
- `추격매수`는 메인 시스템에 넣지 않는다.
- `조건검색`은 어디까지나 후보군 압축이다.
- 점수는 바로 매수 신호가 아니라 `후보 우선순위`다.
- `좋은 자리`와 `사고 싶은 자리`는 다르다.
- `결과가 좋았던 자리`와 `실전에서 누를 수 있는 자리`도 다르다.

## Current Scoring Gap

- 지금 잘 잡는 것:
  - 이평 기반 눌림
  - 20/60/120 근접
  - 공포형 눌림
  - 과열 확장 구간
- 아직 약한 것:
  - `상승 후 눌림` vs `그냥 횡보 중`
  - `빗각 미돌파 감점`
  - `신저가 진행형` 강한 배제
  - `실제로 사기 편한 자리`
  - `결과 좋음/나쁨` 차이를 수치로 분리

## Next Session Workflow

다음 세션에서는 아래 순서를 그대로 반복한다.

1. 종목 하나 선택
2. 모델이 과거 좋은 자리 후보 날짜를 먼저 제시
3. 사용자가 아래 라벨로 보정
   - `정답`
   - `근접`
   - `제외`
   - `결과 좋음`
   - `결과 나쁨`
4. 아래 축을 중심으로 규칙 보정
   - `빗각 미돌파 감점`
   - `상승 후 눌림` 여부
   - `240일선`, `주봉`, `월봉`
   - `실제 사기 편한 자리`
   - `무서운 자리`
5. 10종목 단위로 중간 점검
   - 무작위 테스트
   - 점수 과대/과소 보정

## How To Continue Immediately

- 다음 세션 시작 시 해야 할 첫 문장:
  - `SESSION_RECOVERY.md`, `chart_pattern_summary.md`, `chart_case_notes.json`, `chart_case_scores.json`을 먼저 읽고 현재 목표와 작업 방식을 복기한다.
- 그 다음:
  - 새로운 종목 1개를 정해서 과거 후보 날짜를 먼저 제시한다.
- 절대 하면 안 되는 것:
  - 현재 자리 평가만 길게 늘어놓고 과거 자리 보정을 건너뛰기
  - 조건검색식만 만지기
  - 빗각을 직접 알 수 있다고 가정하기

## Next Session Prompt

```text
우리는 차트분석 기반 매수자리 규칙화를 계속한다.
목표는 네가 먼저 고른 자리와 내가 실제로 인정하는 자리가 95% 이상 일치하도록 만드는 것이다.

기준:
- 시장보다 차트 자리가 우선이다.
- 빗각, 지지저항, 20/60/120/240 이평, 주봉, 월봉, 거래량, RSI, 이격도, 박스권을 함께 본다.
- 빗각은 직접 수치화가 어려우니 다른 지표 흔적으로 근사한다.
- 좋은 자리 / 사고 싶은 자리 / 무서운 자리 / 늦은 자리를 구분한다.
- 추격매수는 메인 시스템에 넣지 않는다.
- 조건검색은 후보군 압축용이다.
- 점수는 일봉 중심이고, 주봉/월봉은 약한 보정 점수다.

작업 방식:
- 네가 종목 하나를 정해서 과거 좋은 자리 후보 날짜를 먼저 제시한다.
- 내가 정답/근접/제외와 결과 좋음/나쁨을 보정한다.
- 특히 상승 후 눌림 vs 횡보 중, 빗각 미돌파 감점, 240일선/주봉/월봉 반영을 강화한다.

참고 파일:
- C:\Users\KGWPC\workspace\dividend-chart-score\SESSION_RECOVERY.md
- C:\Users\KGWPC\workspace\dividend-chart-score\_cache\chart_pattern_summary.md
- C:\Users\KGWPC\workspace\dividend-chart-score\_cache\chart_case_notes.json
- C:\Users\KGWPC\workspace\dividend-chart-score\_cache\chart_case_scores.json

이제 다음 종목부터 계속 진행하자.
```

## Known Maintenance Notes

- `requirements.txt`에 코인 지원용 `requests`가 반드시 포함돼 있어야 한다.
- `__pycache__`와 `*.pyc`는 git 추적 대상이 아니어야 한다.
- 다음 세션 시작 시 `git status`로 문서/캐시 오염부터 확인한다.
- `kgw_trend_template_v1.pine`는 Pine v6 기준으로 유지한다.
