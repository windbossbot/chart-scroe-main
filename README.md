# Dividend Chart Score

이 폴더는 차트 점수화 전용입니다.

- 메인 앱: `chart_score_app.py`
- 배포 설정: `render.yaml`
- 의존성: `requirements.txt`
- 점수 재생성: `score_cases.py`
- 패턴 점검 CLI: `chart_pattern_score.py`
- 참고 자료: `_cache/*`, `SESSION_RECOVERY.md`, `kgw_trend_template_v1.pine`

실행:

```powershell
cd C:\Users\KGWPC\workspace\dividend-chart-score
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run chart_score_app.py --server.port 8501
```

점수 캐시를 다시 만들 때:

```powershell
cd C:\Users\KGWPC\workspace\dividend-chart-score
.\.venv\Scripts\python.exe score_cases.py
```
