# Logistics Assistant — AI-Powered Shipment Tracker

An async REST API that takes a shipment ID, fetches tracking data, and returns an AI-generated customer summary with delay detection — built with FastAPI, Gemini, and Redis.

## Tech Stack
- **FastAPI** (async) — REST API framework
- **Google Gemini 2.5 Flash** — AI summary generation with JSON-mode output
- **Redis** — Response caching (10-minute TTL per shipment)
- **Pydantic v2** — Request/response validation and settings management
- **Docker + Docker Compose** — Containerised local development
- **GitHub Actions** — CI pipeline with automated tests
- **slowapi** — Rate limiting (10 req/min per IP)

## Project Structure
```
logistics-assistant/
├── app/
│   ├── main.py                  # FastAPI app, routes, exception handlers
│   ├── models/schemas.py        # Pydantic request/response models
│   ├── services/
│   │   ├── tracking_shipment.py # Shipment lookup + context pre-processing
│   │   └── ai_summary.py        # Gemini integration, prompt versioning
│   ├── core/
│   │   ├── config.py            # Settings via pydantic-settings
│   │   ├── cache.py             # Async Redis get/set with graceful fallback
│   │   └── exceptions.py        # Custom exception classes
│   └── utils/data_loader.py     # JSON loader with in-memory LRU cache
├── tests/
│   └── test_tracking_service.py
├── data/synthetic_data.json
├── Dockerfile
├── docker-compose.yml           # App + Redis
├── .github/workflows/ci.yml
└── requirements.txt
```

## Quick Start

### 1. Local (without Docker)
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

# Start Redis (requires Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Run the app
uvicorn app.main:app --reload
```

### 2. Docker Compose (recommended)
```bash
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY

docker-compose up --build
```

Visit `http://localhost:8000/docs` for the interactive API docs.

## API Endpoints

### `POST /summarize`
Returns an AI-generated summary for a shipment.

**Request:**
```json
{ "shipment_id": "TRK86742LOG" }
```

**Response:**
```json
{
  "shipment_id": "TRK86742LOG",
  "summary": "Your shipment is currently in Memphis, TN and is on track for delivery to New York by April 28th.",
  "estimated_delivery": "2026-04-28T00:00:00",
  "is_exception": false,
  "suggested_actions": null,
  "cached": false
}
```

**Sample IDs with delays (WTH/HLD):**
- `TRK35874LOG` — Weather delay at Incheon
- `TRK96831LOG` — Hold + Weather delay
- `TRK48683LOG` — Active hold (Alert: Delay status)

## Running Tests
```bash
pytest tests/ -v
```

## Design Decisions (for interviews)

**Why pre-process before the AI call?**
The `extract_shipment_context()` function extracts only the relevant fields (last location, exception events) before sending to Gemini. This reduces token usage, makes the prompt deterministic, and means the LLM focuses on communication — not data parsing.

**Why Redis caching?**
Shipment status doesn't change every second. Caching AI responses for 10 minutes eliminates redundant LLM API calls for the same order, reducing latency and cost. Cache failure is non-fatal — the app falls through to a fresh Gemini call.

**Why custom exceptions?**
`ShipmentNotFoundException` and `AIServiceException` map to specific HTTP status codes (404, 503) via FastAPI exception handlers. This keeps route handlers clean and error responses consistent.

**Why `lru_cache` on `load_logistics_data`?**
The JSON file is read once per process and held in memory — simulating a DB connection pool pattern. In production this would be replaced with an async DB call.
