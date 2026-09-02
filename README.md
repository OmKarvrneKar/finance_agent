# AI Finance Agent

A full-stack AI-powered personal finance assistant that allows you to upload bank statements, automatically categorize transactions using Gemini AI, and query your financial data using natural language.

## Features

- **Automated Categorization**: Upload bank CSV statements and have them automatically parsed and categorized by AI.
- **Receipt OCR & Cash Capture**: Photograph or upload receipts to automatically extract merchant, date, and amount. Uses local Tesseract OCR by default (or Gemini Vision via config) and prompts you to confirm/edit the extracted data before saving it as a cash expense.
- **Natural Language Agent**: Ask questions about your spending ("How much did I spend on food this month?") and the AI will query the database to provide answers and insights.
- **Subscriptions Detection**: Automatically identifies recurring expenses, determines their frequency, and estimates monthly/annual costs.
- **Anomaly Detection**: Proactively warns you about suspicious transactions. It uses simple rule-based and statistical heuristics (like mean, standard deviation, and percent-change thresholds) to detect recurring bill price jumps, short-window duplicate charges, and unusually large expenses from new merchants.
- **Predictive Cash-Flow & Alerts**: Forecasts your end-of-month spending using a simple linear run-rate extrapolation based on your current month's transactions. It compares this projection against your 3-month historical average to proactively warn you of potential overspending. *(Note: This uses straightforward mathematical extrapolation, not heavy machine learning. It assumes consistent spending patterns and does not account for known upcoming one-off expenses).*
- **Budget Goals & What-If Simulator**: Set monthly spending caps per category and receive proactive nudges as you approach them. Run hypothetical scenarios to see how changing your habits (e.g. cutting dining out by 20%) would impact your long-term savings, calculating exactly how many months it would take to reach a specific financial goal.
- **Dashboard & Analytics**: Visualize your spending with bar and pie charts.
- **Full-Stack Architecture**: Built with Vite + React on the frontend and FastAPI + SQLite on the backend.

## Tech Stack

**Frontend:**
- React (Vite)
- React Router DOM
- Recharts (for data visualization)
- Lucide React (for icons)
- Axios

**Backend:**
- Python 3.11+
- FastAPI
- SQLAlchemy (SQLite)
- Pandas (for robust CSV parsing)
- OpenAI API Client (configured for OpenRouter / Gemini)

## Setup and Installation

### 1. Clone the repository

```bash
git clone https://github.com/OmKarvrneKar/Finance-Agent.git
cd Finance-Agent
```

### 2. Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
pip install -r requirements.txt
```

Set up your environment variables (e.g., inside `.env` or just exporting them):
```bash
GEMINI_API_KEY=your_gemini_key
OPENROUTER_API_KEY=your_openrouter_key
```

Run the FastAPI server:
```bash
uvicorn app.main:app --reload --port 8001
```

### 3. Frontend Setup

In a new terminal:
```bash
cd frontend
npm install
npm run dev
```

The frontend will start on `http://localhost:5173/` 

## Deployment


### Backend (Render)
1. Create a new Web Service using Docker.
2. Set root directory to `backend`
3. Add environment variables `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, and `FRONTEND_URL`

### Frontend (Vercel)
1. Create a new project and select the Vite framework.
2. Set root directory to `frontend`.
3. Add environment variable `VITE_API_URL` pointing to your deployed backend (e.g., `https://your-render-url.onrender.com/api`)
