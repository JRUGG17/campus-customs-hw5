# The Desk: Campus Customs dashboard

React + Vite + TypeScript. It calls the FastAPI backend at http://localhost:8000.

```bash
# 1. backend (from hw5/backend/)
uvicorn main:app --reload --port 8000

# 2. dashboard (from hw5/frontend/)
npm install      # first time only
npm run dev      # http://localhost:5173
```

The backend allows the page's origin (http://localhost:5173) through CORS. To point the page somewhere else, set `VITE_API_URL`. Design notes are in `../output/design.md`.
