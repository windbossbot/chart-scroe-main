# Deploy Guide

## GitHub
1. Open `C:\Users\KGWPC\workspace\dividend-chart-score`.
2. Commit and push to `https://github.com/windbossbot/dividend-screener-v3`.
3. Keep this folder as the only source for the chart-score app.

## Render
1. Connect the GitHub repo in Render.
2. Use the repo root and the included `render.yaml`.
3. Render will install from `requirements.txt`.
4. Start command:
   `streamlit run chart_score_app.py --server.port $PORT --server.address 0.0.0.0`

## Local
```powershell
cd C:\Users\KGWPC\workspace\dividend-chart-score
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run chart_score_app.py --server.port 8501
```
