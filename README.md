# DevPulse — Developer Productivity MVP

A full-stack developer productivity tool built with **FastAPI** (Python backend) + **React** (frontend).

## Project Structure

```
dev-productivity/
├── backend/
│   ├── main.py            ← FastAPI app (API routes)
│   ├── data_loader.py     ← Reads Excel, calculates metrics + interpretations
│   ├── requirements.txt   ← Python dependencies
│   └── data/
│       └── intern_assignment_support_pack_dev_only_v3.xlsx  ← PUT FILE HERE
│
└── frontend/
    ├── public/
    │   └── index.html
    ├── src/
    │   ├── App.js / App.css           ← Main app shell
    │   ├── index.js / index.css       ← Entry point + global styles
    │   ├── hooks/useApi.js            ← API call functions
    │   └── components/
    │       ├── MetricCard.js/.css     ← Individual metric tile with hover tooltip
    │       ├── PatternBadge.js/.css   ← Healthy/Watch/Review status pill
    │       ├── InterpretationPanel.js/.css  ← Interpretation button + next steps
    │       └── ManagerView.js/.css    ← Team overview table
    └── package.json
```

---

## Setup Instructions

### Step 1 — Place the Excel file

Copy your Excel workbook into:
```
backend/data/intern_assignment_support_pack_dev_only_v3.xlsx
```
(Create the `data/` folder if it doesn't exist.)

---

### Step 2 — Set up the Python backend

```bash
cd backend

# Create a virtual environment (recommended)
python -m venv venv

# Activate it
# On Mac/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn main:app --reload --port 8000
```

Backend will run at: **http://localhost:8000**  
You can test it at: **http://localhost:8000/docs** (auto-generated API docs)

---

### Step 3 — Set up the React frontend

```bash
cd frontend

# Install packages
npm install

# Start the dev server
npm start
```

Frontend will open at: **http://localhost:3000**

The `"proxy": "http://localhost:8000"` in package.json means React automatically forwards API calls to FastAPI — no CORS issues.

---

## API Endpoints

| Endpoint | What it returns |
|---|---|
| `GET /developers` | List of all developers with name, team, level |
| `GET /months` | Available months in the dataset |
| `GET /metrics/{developer_id}/{month}` | Full metrics + tooltips + interpretation + next steps |
| `GET /manager-summary/{month}` | All developers' metrics for a given month |

---

## Features

- **Metric cards** — 5 metrics displayed with colour-coded status (green/amber/red)
- **Hover tooltips** — hover any metric card to see: what the metric means + whether this dev's value is high/low
- **Pattern badge** — Healthy Flow / Quality Watch / Needs Review status pill
- **Interpret button** — click to reveal a plain-English interpretation of the month + 2–4 personalised next steps
- **Team Overview tab** — manager view showing all developers side-by-side
- **Month selector** — switch between March and April 2026 data
