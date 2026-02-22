# Amon Hen

**Narrative Intelligence Platform** — *The Seat of Seeing*

One vantage point across every source. Amon Hen ingests news and social media from RSS feeds, GDELT, Bluesky, and Reddit, enriches each item with LLM-extracted intelligence (entities, claims, framing, sentiment), embeds into vector space, clusters by *narrative* (not topic), and surfaces divergence, anomalies, and daily intelligence digests.

## Architecture

```
Sources (RSS/GDELT/Bluesky/Reddit)
    │
    ▼
Ingestion → Raw Items
    │
    ▼
LLM Enrichment (Claude Haiku / Ollama)
    │  → entities, claims, framing, sentiment, summary
    ▼
Embedding (all-MiniLM-L6-v2, 384-dim)
    │  → embed summary + framing + claims (NOT raw text)
    ▼
┌──────────┬──────────┐
│  SQLite   │  Qdrant   │
│ (metadata)│ (vectors) │
└──────────┴──────────┘
    │
    ▼
Intelligence Layer
    ├── HDBSCAN clustering → Narrative Clusters
    ├── Divergence detection (source sub-centroids)
    ├── Anomaly detection (volume/sentiment/entity)
    └── Daily digest generation
    │
    ▼
┌──────────┬──────────┬──────────┐
│   CLI     │ REST API  │Dashboard │
└──────────┴──────────┴──────────┘
```

## Quick Start

### From Source

```bash
# Clone
git clone https://github.com/civilian24601/amon-hen.git
cd amon-hen

# Install (Python 3.11+)
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your API keys

# Validate feeds
amon validate-sources

# Seed with historical data
amon seed --days 7

# Start the server
amon serve
```

### With Docker

```bash
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
```

Dashboard at `http://localhost:8080`.

## Configuration

### `.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes (or Ollama) | Claude API key for enrichment |
| `REDDIT_CLIENT_ID` | For Reddit | Reddit app client ID |
| `REDDIT_CLIENT_SECRET` | For Reddit | Reddit app client secret |
| `BLUESKY_HANDLE` | For Bluesky | Bluesky handle |
| `BLUESKY_APP_PASSWORD` | For Bluesky | Bluesky app password |
| `QDRANT_MODE` | No | `local` (default), `cloud`, or `memory` |
| `ENRICHMENT_DAILY_BUDGET_USD` | No | Daily LLM budget (default: $2.00) |

### `sources.yaml`

Define RSS feeds, GDELT queries, Bluesky keywords, and Reddit subreddits. See the included `sources.yaml` for examples.

## CLI Reference

| Command | Description |
|---------|-------------|
| `amon status` | Item/cluster counts, cost, source health |
| `amon search "query"` | Semantic search across enriched items |
| `amon clusters` | List active narrative clusters |
| `amon cluster <id>` | Detail view for a specific cluster |
| `amon digest` | Latest intelligence digest |
| `amon ingest --now` | Trigger immediate ingestion |
| `amon recluster --now` | Trigger re-clustering |
| `amon seed --days N` | Backfill via GDELT historical queries |
| `amon validate-sources` | Check which RSS feeds are alive |
| `amon serve` | Start API server + scheduler |

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/clusters` | List active clusters |
| `GET /api/clusters/:id` | Cluster detail + member items |
| `GET /api/search?q=<query>` | Semantic search |
| `GET /api/items` | Recent enriched items |
| `GET /api/digest/latest` | Latest digest |
| `GET /api/health` | System health |

## Self-Hosted (Ollama)

Set `enrichment.provider: ollama` in config and run Ollama locally:

```bash
ollama pull llama3
# Set ENRICHMENT_PROVIDER=ollama in .env
```

Combined with local Qdrant (`QDRANT_MODE=local`), the entire system runs without any external API calls.

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## Design Principles

- **Narrative, not topic**: Clusters capture how stories are framed, not just what they're about
- **Embed intelligence, not text**: Vectors are generated from LLM-extracted summaries, framing, and claims
- **Source-aware**: Every cluster tracks which sources contribute and where they diverge
- **Budget-conscious**: Daily cost tracking with configurable budget limits
- **Self-hostable**: Works entirely offline with Ollama + local Qdrant

## License

MIT
