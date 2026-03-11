# Research Weight Notes (2026-03-11)

## Purpose

- 최근 백테스트 결과와 기존 공개 연구를 함께 참고해 점수 비중을 정리한다.
- 차트 우선 원칙을 유지하되, 어떤 축을 강하게 보고 어떤 축을 약하게 둘지 기록한다.

## Reflected Sources

- Brock, Lakonishok, LeBaron (1992)
  - Moving average / trading range rule에 예측력이 있다는 고전 연구
  - Link: [American Finance Association PDF](https://support-and-resistance.technicalanalysis.org.uk/BrockLakonishokLeBaron1992.pdf)

- George, Hwang (2004)
  - 52주 신고가 근처가 모멘텀 설명력에 중요하다는 연구
  - Link: [Journal of Finance PDF](https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf)

- Lee, Swaminathan (2000)
  - 거래량이 모멘텀 해석에 중요하다는 연구
  - Link: [Kellogg summary](https://www.kellogg.northwestern.edu/faculty/research/detail/2000/price-momentum-and-trading-volume/)

- Moskowitz, Ooi, Pedersen (2012)
  - 추세 자체를 독립된 요인으로 보는 시간추세 모멘텀 연구
  - Link: [SSRN PDF](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2089463_code753937.pdf?abstractid=2089463&mirid=1)

## Practical Reflection

- `월봉 5선`
  - 방향 필터 최상위
  - 현재 프로젝트 백테스트와 공개 연구 모두 추세 지속 쪽을 지지

- `주봉 60선`
  - 월봉 다음의 중간 방향 필터
  - 일봉 타점보다 먼저 종목 상태를 걸러주는 용도

- `52주 신고가 근처`
  - 강한 가점
  - 신고가 갈 가능성이 높다는 사용자 규칙과 George-Hwang 방향이 일치

- `52주 신저가 근처`
  - 강한 감점
  - 신저가가 또 신저가를 부를 가능성 반영

- `20/60/120/240/480`
  - 이평은 매매 뼈대
  - 단, 종목 상태(강세/중간/약세)에 따라 핵심선이 달라진다

- `거래량 감소`
  - 눌림 정리 / 박스 정리 확인용
  - 단독 시그널보다는 지지 확인 보조

- `박스권`, `고점 대비 눌림`
  - 빗각을 직접 못 보는 대신 대체 흔적으로 반영

## Current Interpretation

- 메인:
  - 월봉
  - 주봉
  - 일봉

- 보조:
  - 4시간봉
  - 1시간봉

- 약한 참고:
  - 펀더멘털
  - 시장/지수

## Why Fundamentals Stay Weak

- KR 과거 펀더 이력은 현재 환경에서 안정적으로 조회되지 않음
- US/CRYPTO 과거 펀더 이력도 현재 저장소 소스로는 장기 백테스트가 어려움
- 따라서 펀더멘털은 차트를 덮는 메인 점수가 아니라 참고용 보조 점수로만 유지
