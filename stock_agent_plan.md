# Autonomous AI Stock Trading Agent — Implementation Plan

## Architecture Overview

The agent runs as a scheduled Cloud Run Job triggered once per trading day after market close. Each run follows this pipeline:

```
Cloud Scheduler (daily cron)
        |
  Cloud Run Job (Python container)
        |
  main.py (orchestrator)
   /              \
yfinance data    Portfolio state
(60d OHLCV)     (Firestore / JSON)
        |
  Signal Engine
  (RSI + SMA tools)
        |
  Gemini 2.5 Flash
  (tool-calling loop)
        |
  Decision Executor
  (buy/sell/hold + trade log)
```

---

## Tech Stack

| Concern | Choice |
|---|---|
| LLM | `google-genai` SDK → `gemini-2.5-flash` |
| Stock data | `yfinance` (free, no API key) |
| Indicators | `pandas-ta` (vectorized RSI/SMA) |
| Portfolio state | Cloud Firestore (Spark free tier) + local JSON fallback |
| Scheduling | Cloud Scheduler + Cloud Run Jobs |
| Secrets | GCP Secret Manager |

---

## File Structure

```
stock_plan/
├── Dockerfile
├── requirements.txt
├── .env.example
├── config/
│   └── settings.py          # env var config: watchlist, thresholds, flags
├── src/
│   ├── main.py              # orchestrator entrypoint
│   ├── data/
│   │   └── fetcher.py       # yfinance wrapper, caches DataFrames
│   ├── signals/
│   │   ├── rsi.py           # RSI(14) → oversold/overbought/neutral
│   │   └── sma.py           # SMA(20/50) → cross signals
│   ├── agent/
│   │   ├── tools.py         # Gemini function declarations
│   │   └── gemini_agent.py  # tool-calling loop → final decisions JSON
│   ├── portfolio/
│   │   ├── state.py         # Firestore/JSON read-write
│   │   └── executor.py      # applies decisions, clamps to feasible qty
│   └── utils/
│       └── logger.py
├── data/
│   └── portfolio.json       # local fallback (gitignored)
└── tests/
```

---

## Key Component Details

### Configuration (`config/settings.py`)

All settings driven by environment variables with sane defaults:

| Variable | Default | Description |
|---|---|---|
| `WATCHLIST` | `"NVDA,AMZN,GOOGL"` | Comma-separated ticker list |
| `INITIAL_CAPITAL` | `20000.0` | Starting portfolio value |
| `MIN_CASH_RESERVE` | `2000.0` | Minimum cash to keep on hand |
| `MAX_POSITION_PCT` | `0.20` | Max 20% of portfolio per ticker |
| `USE_FIRESTORE` | `true` | Set `false` for local dev |
| `GEMINI_MODEL` | `"gemini-2.5-flash"` | Model ID |
| `RSI_OVERSOLD` | `30` | RSI threshold for oversold signal |
| `RSI_OVERBOUGHT` | `70` | RSI threshold for overbought signal |
| `SMA_FAST` | `20` | Fast SMA period |
| `SMA_SLOW` | `50` | Slow SMA period |
| `LOG_LEVEL` | `"INFO"` | Logging verbosity |

---

### Stock Data Fetching (`src/data/fetcher.py`)

- Use `yfinance.Ticker(symbol).history(period="60d", interval="1d")` for daily OHLCV
- 60 days of history ensures enough data for RSI(14) and SMA(50) without edge cases
- Fetch all watchlist tickers once at startup and cache in a dict — signal tools reuse the same DataFrames without additional network calls
- Validate each DataFrame has at least 50 rows and no NaN close prices before passing to signal functions
- Wrap fetches in a retry decorator (3 attempts, exponential backoff) — yfinance can return empty DataFrames during rate limiting

---

### Signal Tools

#### RSI (`src/signals/rsi.py`)
- Calculate 14-period RSI using `pandas_ta.rsi(close, length=14)`
- Return last 3 days of RSI values to expose momentum direction (rising vs falling)
- Signal labels: `oversold` (RSI < 30), `overbought` (RSI > 70), `neutral` otherwise

#### SMA (`src/signals/sma.py`)
- Calculate SMA(20) and SMA(50) using `pandas_ta.sma()`
- Detect crossovers by comparing today vs yesterday's relative positions
- Signal labels: `bullish_cross`, `bearish_cross`, `bullish_trend`, `bearish_trend`, `neutral`

#### Tool Declarations (`src/agent/tools.py`)

Exposed to Gemini as function declarations:

| Tool | Returns |
|---|---|
| `get_rsi_signal(ticker)` | RSI value, 3-day trend, signal label |
| `get_sma_signal(ticker)` | SMA20/50 values, crossover signal label |
| `get_portfolio_state()` | Cash, positions, total portfolio value |
| `get_current_price(ticker)` | Latest close from cached DataFrame |

All tools pull from DataFrames fetched once at startup — no repeated network calls during the agent loop.

---

### Gemini Agent Loop (`src/agent/gemini_agent.py`)

1. Build initial prompt with portfolio state, watchlist, today's date, and risk rules
2. Register the 4 tool declarations with the Gemini client
3. **Tool-calling loop** (max 20 iterations):
   - If response contains tool calls → dispatch to Python functions → append results → re-submit
   - Repeat until model produces a text-only response
4. Parse final JSON block from the model's text: `[{ticker, action, quantity, rationale}, ...]`
5. Fall back to "hold all" if JSON parsing fails

**System prompt key elements:**
- Role: "disciplined quantitative trading assistant managing a simulated paper-trading portfolio"
- Instruction to call tools for every ticker before deciding
- Risk rules: position limits, cash floor, no shorting, no leverage
- Output format specification for the final decisions JSON

**Model settings:** `temperature=0` for deterministic decisions.

---

### Portfolio State (`src/portfolio/state.py`)

#### Firestore Schema

```json
{
  "cash": 18500.00,
  "positions": {
    "NVDA": {"shares": 10, "avg_cost": 875.50, "last_updated": "2026-04-10"},
    "AMZN": {"shares": 5, "avg_cost": 195.20, "last_updated": "2026-04-09"}
  },
  "last_run": "2026-04-10",
  "initial_capital": 20000.00
}
```

**Storage:** Dual-layer approach
- **Primary:** Firestore document `portfolios/main`, trade log as subcollection `portfolios/main/trades/{timestamp}`
- **Fallback:** `data/portfolio.json` for local development (`USE_FIRESTORE=false`)

**Interface:**
- `load_portfolio() -> dict`
- `save_portfolio(state: dict) -> None`
- `append_trade(trade: dict) -> None`

Write the full portfolio state atomically as a single document to avoid partial-write corruption.

#### Decision Executor (`src/portfolio/executor.py`)

- **Buy:** verify sufficient cash → compute max whole shares at current price → deduct cash → add/update position
- **Sell:** verify position exists → compute proceeds → add cash → reduce or remove position
- Clamp quantities to feasible amounts and log a warning if the agent requested more than available
- Record each executed trade: timestamp, action, ticker, shares, price, agent rationale

**Duplicate-run guard:** Check `last_run == today` at startup and skip execution if already run today.

---

## GCP Free Tier Usage

| Service | Free Limit | Estimated Usage |
|---|---|---|
| Cloud Run Jobs | 180,000 vCPU-sec/month | ~1,320 sec/month (22 days × 60s) |
| Cloud Scheduler | 3 free jobs | 1 needed |
| Firestore | 50k reads, 20k writes/day | <10 per run |
| Artifact Registry | 0.5 GB | ~200 MB image |
| Secret Manager | 6 secret versions free | 1 key stored |
| Cloud Build | 120 build-min/day | Optional CI |

**Schedule:** `0 21 * * 1-5` UTC (4:00 PM Eastern, after NYSE close)

Running after market close uses end-of-day prices and decides for the next trading day, avoiding intraday noise.

---

## Deployment Architecture

1. **Artifact Registry** — store image as `us-central1-docker.pkg.dev/{PROJECT}/stock-agent/trader:latest`
2. **Cloud Run Job** (not a Service — no HTTP endpoint needed)
   - 1 vCPU, 512 MiB RAM
   - `--max-retries 1` to avoid duplicate trade execution
   - Secrets injected from Secret Manager via `--set-secrets`
   - Service account roles: `roles/datastore.user`, `roles/secretmanager.secretAccessor`, `roles/aiplatform.user`
3. **Cloud Scheduler** — triggers Cloud Run Job via OIDC-authenticated Jobs API call

### Required GCP APIs to Enable
- Cloud Run
- Cloud Scheduler
- Firestore
- Secret Manager
- Artifact Registry

---

## Build Sequence

1. `src/data/fetcher.py` — validate yfinance works with the watchlist tickers
2. `src/signals/rsi.py` + `src/signals/sma.py` — unit test against known price data
3. `src/portfolio/state.py` with JSON backend only
4. `src/agent/tools.py` + `src/agent/gemini_agent.py` — test with a mock portfolio
5. `src/main.py` — wire everything together, test full local run end-to-end
6. Add Firestore backend to `state.py`, test with `USE_FIRESTORE=true`
7. Write `Dockerfile`, test with `docker run` locally
8. Deploy to GCP: Firestore → Secret Manager → Artifact Registry → Cloud Run Job → Cloud Scheduler
9. Run a manual trigger, inspect Cloud Logging and Firestore state
10. Write tests in `tests/` for signals and portfolio logic

---

## Key Risks and Limitations

### Paper Trading vs Real Trading
This is strictly a **simulated paper trading system** — no real orders are executed. Live trading would require a brokerage API (e.g., Alpaca, Interactive Brokers). Paper results will be optimistic due to the absence of slippage, bid-ask spreads, and market impact.

### Data Quality
- yfinance is an unofficial Yahoo Finance scraper — can break silently on API changes
- End-of-day data only; the agent cannot react to intraday news or price movements
- yfinance adjusts for splits and dividends by default (`auto_adjust=True`) — correct behavior, but document it
- Always validate DataFrame row count and NaN values before passing to signal functions

### Gemini API Limits
- Gemini 2.5 Flash free tier (AI Studio): verify current RPM and token/day limits
- Tool-calling loops can consume 10,000–50,000 tokens per run depending on reasoning depth
- Running the agent multiple times per day during testing can exhaust free tier limits quickly

### LLM Decision Quality
- The model is not fine-tuned for trading; decisions are based on signal summaries and pretraining knowledge
- RSI and SMA are lagging indicators — they reflect past price action, not future performance
- Use `temperature=0` for reproducibility; even so, decisions may vary across SDK versions

### Reliability
- JSON parsing of the final decision block is fragile — always fall back to "hold all" on parse failure
- Firestore writes are not transactional in the simple implementation; write atomically as a single document
- Duplicate-run guard (`last_run == today`) protects against Cloud Scheduler retries double-executing trades

### Security
- Never commit `.env` or API keys to version control
- Use GCP Secret Manager and Application Default Credentials exclusively in production
- Cloud Run service account should be least-privilege — only the three roles listed above
