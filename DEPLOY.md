# Deploy to Render

## Prerequisites

1. Push this project to a **GitHub** repository
2. Create a [Render](https://render.com) account (free)

## Deploy Steps

### Option A: One-Click (Blueprint)

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New** → **Blueprint**
3. Connect your GitHub repo and select this project
4. Render will detect `render.yaml` and create the web service
5. Add your **FINVIZ_API_KEY** in the service **Environment** tab
6. Deploy

### Option B: Manual Setup

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New** → **Web Service**
3. Connect your GitHub repo
4. Configure:
   - **Root Directory**: `Market Metrics Dashboard` (if repo root is parent) or leave blank
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:server --bind 0.0.0.0:$PORT`
5. Add environment variable:
   - **Key**: `FINVIZ_API_KEY`
   - **Value**: your FinViz Elite API key
6. Click **Create Web Service**

## Environment Variables

| Variable        | Required | Description                    |
|----------------|----------|--------------------------------|
| FINVIZ_API_KEY | Yes      | Your FinViz Elite API key      |

## Notes

- **Free tier**: Service spins down after ~15 min of inactivity. First visit after that may take 30–60 seconds to wake up.
- **Cache**: In-memory cache resets on each deploy. Disk cache (`.cache/`) is ephemeral on Render.
- **Root directory**: If your repo root is `PradlyPortal` and this app is in `Market Metrics Dashboard/`, set **Root Directory** to `Market Metrics Dashboard` in Render.
