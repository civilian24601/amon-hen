# Amon Hen — Narrative Intelligence Platform

**"The Seat of Seeing"** — One vantage point across every source.

> **Instructions for Claude:** This is a complete project specification. Build this as a proper Python package from the start using the project structure defined below. Start with Week 1 tasks. Ask clarifying questions if anything is ambiguous, but prefer making reasonable decisions and moving forward over blocking on details.

## What You're Building

**Amon Hen** is a self-hostable, open-source narrative tracking and clustering tool. It ingests news articles and social media posts from configurable sources, enriches them with LLM-extracted intelligence (entities, claims, framing, sentiment), embeds them into vector space, and clusters by *narrative* — not just topic. It tracks how narratives emerge, mutate, merge, and die over time, and surfaces anomalies like sudden coordinated amplification or narrative divergence between source types.

**The core insight:** GDELT tells you what happened. RSS tells you what was published. Bluesky tells you what people are saying. Amon Hen tells you *what story is being told — and when that story changes.*

**Positioning:** This fills a gap between enterprise narrative intelligence platforms ($50K+/year: Graphika, Recorded Future, Primer, Silobreaker) and scattered Python scripts on GitHub. No open-source tool does narrative-level clustering with modern LLM enrichment pipelines. Amon Hen is the missing middle layer.

### Naming Convention

| Context | Format |
|---------|--------|
| Project name | Amon Hen |
| GitHub repo | `amon-hen` |
| Python package | `amon_hen` |
| CLI binary | `amon` |
| Qdrant collection | `amon_hen_items` |
| Docker image | `amon-hen` |
| Domain | `amonhen.dev` |

---

## Architecture Overview

```
Sources Layer (configurable via sources.yaml)
  ├── GDELT Doc API (article discovery, 15-min updates)
  ├── RSS Bundle (50-75 curated feeds, user-extensible)
  ├── Bluesky Firehose (filtered by keywords/follows via AT Protocol)
  └── Reddit API (selected subreddits, free tier)
       │
       ▼
Ingestion Pipeline (runs on cron, every 15-30 min)
  ├── Fetch new items from all sources
  ├── Normalize to common schema (see Data Models below)
  ├── Deduplicate (URL-based + semantic similarity threshold)
  └── Queue for enrichment
       │
       ▼
Enrichment Pipeline (async workers processing queue)
  ├── LLM extraction (see Enrichment Prompt below)
  │   ├── Entities (people, orgs, places, with roles)
  │   ├── Core claims (factual assertions made)
  │   ├── Narrative framing (how the story is told)
  │   ├── Sentiment/tone
  │   └── 2-3 sentence summary
  ├── Embed (sentence-transformers or API embeddings)
  └── Store (Qdrant vectors + SQLite metadata)
       │
       ▼
Intelligence Layer (runs after each enrichment batch)
  ├── Narrative clustering (HDBSCAN over embeddings)
  ├── Cluster labeling (LLM-generated cluster names)
  ├── Drift detection (cluster centroid movement over time)
  ├── Divergence detection (same event, different framing by source type)
  ├── Anomaly alerts (volume spikes, new clusters, sudden amplification)
  └── Daily digest generation (LLM summary of emerging/fading narratives)
       │
       ▼
Interface Layer
  ├── Dashboard (narrative cluster map, timeline, search)
  ├── CLI (query, search, status, manual operations)
  └── REST API (for other tools to consume)
```

---

## Data Models

### RawItem (ingested, pre-enrichment)

```python
@dataclass
class RawItem:
    id: str                    # UUID
    source_type: str           # "rss" | "gdelt" | "bluesky" | "reddit"
    source_name: str           # e.g. "Reuters", "r/geopolitics", "@user.bsky.social"
    source_url: str            # original URL
    title: str | None          # article title (None for social posts)
    content_text: str          # full text or post body (used for enrichment, NOT stored long-term)
    author: str | None
    published_at: datetime
    ingested_at: datetime
    language: str              # ISO 639 code
    raw_metadata: dict         # source-specific fields (GDELT tone, Reddit score, etc.)
```

### EnrichedItem (post-LLM, stored in SQLite + Qdrant)

```python
@dataclass
class EnrichedItem:
    id: str                    # same UUID as RawItem
    source_type: str
    source_name: str
    source_url: str
    title: str | None
    published_at: datetime
    ingested_at: datetime
    language: str

    # LLM-extracted intelligence
    summary: str               # 2-3 sentences
    entities: list[Entity]     # see below
    claims: list[str]          # factual assertions made in the piece
    framing: str               # 1-2 sentence description of narrative angle/frame
    sentiment: float           # -1.0 to 1.0
    topic_tags: list[str]      # max 5, from controlled vocabulary + freeform

    # Embedding
    embedding_id: str          # Qdrant point ID
    embedding_model: str       # e.g. "all-MiniLM-L6-v2"

    # Cluster assignment (updated by clustering pipeline)
    cluster_id: str | None
    cluster_label: str | None

    # Metadata
    enrichment_model: str      # e.g. "claude-haiku-4-5"
    enrichment_cost_usd: float # track spend
```

### Entity

```python
@dataclass
class Entity:
    name: str                  # canonical name
    type: str                  # "person" | "org" | "place" | "event"
    role: str                  # e.g. "subject", "target", "source", "location"
    aliases: list[str]         # alternate names found
```

### NarrativeCluster

```python
@dataclass
class NarrativeCluster:
    id: str
    label: str                 # LLM-generated human-readable name
    summary: str               # LLM-generated description of the narrative
    item_count: int
    first_seen: datetime
    last_updated: datetime
    centroid: list[float]      # average embedding vector
    source_distribution: dict  # {"rss": 45, "bluesky": 120, "reddit": 30}
    sentiment_distribution: dict  # histogram of sentiment scores
    key_entities: list[str]    # most frequent entities in cluster
    key_claims: list[str]      # representative claims
    status: str                # "emerging" | "active" | "fading" | "dead"
    parent_cluster_id: str | None  # if this split from another cluster
```

---

## Source Configuration

### sources.yaml (ships with curated defaults, user-extensible)

```yaml
rss:
  # Wire services (highest authority, lowest bias)
  - name: Reuters World
    url: https://feeds.reuters.com/reuters/worldNews
    category: wire
    refresh_minutes: 15

  - name: AP Top News
    url: https://rsshub.app/apnews/topics/apf-topnews
    category: wire
    refresh_minutes: 15

  # Quality international outlets
  - name: BBC World
    url: https://feeds.bbci.co.uk/news/world/rss.xml
    category: news_intl
    refresh_minutes: 30

  - name: Al Jazeera
    url: https://www.aljazeera.com/xml/rss/all.xml
    category: news_intl
    refresh_minutes: 30

  - name: NHK World
    url: https://www3.nhk.or.jp/rss/news/cat0.xml
    category: news_intl
    refresh_minutes: 60

  - name: DW News
    url: https://rss.dw.com/rdf/rss-en-all
    category: news_intl
    refresh_minutes: 60

  - name: France24
    url: https://www.france24.com/en/rss
    category: news_intl
    refresh_minutes: 60

  # US outlets (left-center, center, right-center for balance)
  - name: NPR
    url: https://feeds.npr.org/1001/rss.xml
    category: news_us
    refresh_minutes: 30

  - name: The Hill
    url: https://thehill.com/feed/
    category: news_us
    refresh_minutes: 30

  - name: The Dispatch
    url: https://thedispatch.com/feed/
    category: news_us_right
    refresh_minutes: 60

  # Government/institutional primary sources
  - name: State Dept Briefings
    url: https://www.state.gov/rss-feed/press-releases/feed/
    category: gov_us
    refresh_minutes: 120

  - name: DoD News
    url: https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945
    category: gov_us
    refresh_minutes: 120

  - name: UN News
    url: https://news.un.org/feed/subscribe/en/news/all/rss.xml
    category: gov_intl
    refresh_minutes: 120

  # Think tanks and analysis
  - name: War on the Rocks
    url: https://warontherocks.com/feed/
    category: analysis
    refresh_minutes: 120

  - name: CSIS
    url: https://www.csis.org/rss.xml
    category: analysis
    refresh_minutes: 240

  - name: Brookings
    url: https://www.brookings.edu/feed/
    category: analysis
    refresh_minutes: 240

  - name: Carnegie Endowment
    url: https://carnegieendowment.org/rss/solr/?query=*
    category: analysis
    refresh_minutes: 240

  # Regional (for demo topics)
  - name: Times of Israel
    url: https://www.timesofisrael.com/feed/
    category: news_regional
    refresh_minutes: 30

  - name: Tehran Times
    url: https://www.tehrantimes.com/rss
    category: news_regional
    refresh_minutes: 60

  - name: South China Morning Post
    url: https://www.scmp.com/rss/91/feed
    category: news_regional
    refresh_minutes: 30

gdelt:
  enabled: true
  queries:
    - name: us_israel_iran
      keywords: ["Israel", "Iran", "Netanyahu", "Khamenei", "IRGC", "IDF"]
      refresh_minutes: 15
    - name: us_china
      keywords: ["China", "Taiwan", "Xi Jinping", "trade war", "semiconductor"]
      refresh_minutes: 15
    - name: ai_governance
      keywords: ["AI regulation", "artificial intelligence policy", "AI safety"]
      refresh_minutes: 30

bluesky:
  enabled: true
  filter_mode: keyword  # "keyword" | "list" | "both"
  keywords: ["OSINT", "Israel", "Iran", "geopolitics", "narrative", "disinformation", "infops"]
  max_posts_per_cycle: 200
  refresh_minutes: 5

reddit:
  enabled: true
  subreddits:
    - name: geopolitics
      sort: hot
      limit: 25
    - name: credibledefense
      sort: hot
      limit: 25
    - name: osint
      sort: hot
      limit: 15
  include_top_comments: 3  # include top N comments as context
  refresh_minutes: 30
```

---

## LLM Enrichment

### Provider Configuration

```yaml
enrichment:
  # Primary: Claude Haiku for hosted demo
  provider: anthropic
  model: claude-haiku-4-5-20251001
  api_key_env: ANTHROPIC_API_KEY

  # Alternative: local Ollama for self-hosted (zero cost)
  # provider: ollama
  # model: llama3.1:8b
  # base_url: http://localhost:11434

  # Cost tracking
  track_costs: true
  daily_budget_usd: 2.00  # halt enrichment if exceeded
```

### Enrichment Prompt (single call per item)

```
You are an intelligence analyst extracting structured information from a news article or social media post. Analyze the following content and return a JSON object with these fields:

1. "summary": A 2-3 sentence factual summary of the content.
2. "entities": An array of objects with {name, type, role, aliases}
   - type: "person" | "org" | "place" | "event"
   - role: "subject" | "target" | "source" | "location" | "mentioned"
   - aliases: any alternate names or abbreviations used
3. "claims": An array of the key factual assertions or claims made (max 5). State each as a declarative sentence.
4. "framing": A 1-2 sentence description of the narrative angle. How is this story being told? What perspective or interpretation does the source apply? What is emphasized vs omitted?
5. "sentiment": A float from -1.0 (very negative) to 1.0 (very positive) representing the overall tone.
6. "topic_tags": Up to 5 short tags describing the topics covered.

Respond with ONLY the JSON object, no other text.

CONTENT:
Title: {title}
Source: {source_name} ({source_type})
Date: {published_at}

{content_text}
```

### Embedding Strategy

Use `all-MiniLM-L6-v2` from sentence-transformers for v1 (384-dim, fast, free, runs locally). Embed the concatenation of: `summary + " " + framing + " " + " ".join(claims)`. This ensures the embedding captures *how* the story is told, not just *what* it's about — which is the key differentiation from topic-based clustering.

Do NOT embed the raw article text. The LLM-enriched summary+framing+claims is a higher-signal, lower-noise representation.

---

## Storage Architecture

### Qdrant (vector store — narrative search & clustering)

- Collection: `amon_hen_items`
- Vector size: 384 (matching MiniLM) or 1536 (if using OpenAI embeddings)
- Distance metric: Cosine
- Payload: `{id, source_type, source_name, published_at, cluster_id, sentiment, topic_tags}`
- **Qdrant Cloud free tier: 1GB**, more than sufficient for months of data at projected volume

### SQLite (metadata store — everything else)

Tables:
- `items` — full EnrichedItem records (everything except raw content_text and embedding vector)
- `clusters` — NarrativeCluster records
- `cluster_membership` — item_id ↔ cluster_id with assignment timestamp
- `digests` — daily digest text and metadata
- `source_status` — last fetch time, error count per source
- `cost_log` — per-item enrichment cost tracking

SQLite is the right choice for v1. No managed database, no connection strings, single file, backs up trivially, runs on any VPS. Move to Postgres only if there's a concrete reason (concurrent writers, etc.).

### Data Lifecycle

- **30-day rolling window** for v1. Items older than 30 days are deleted from Qdrant and marked `archived` in SQLite (metadata kept, vector removed).
- Full article text (`content_text`) is used during enrichment and then discarded. Store only the URL and extracted intelligence. This keeps storage small and avoids copyright issues with storing full articles.
- **Projected volume:** ~800-1500 items/day → ~12MB/day in Qdrant → ~360MB/month. Well within Qdrant Cloud free tier.

---

## Intelligence Pipeline

### Narrative Clustering

Run after each enrichment batch (or on schedule, every 1-2 hours).

1. Pull all embeddings from Qdrant for the active window (last 30 days, or configurable).
2. Run HDBSCAN with `min_cluster_size=5`, `min_samples=3`. These params should be configurable.
3. For each cluster:
   a. Compute centroid (mean of member vectors).
   b. Pull the 5 items closest to centroid.
   c. Send those 5 summaries + framings to LLM to generate a cluster label and cluster summary.
   d. Compute source_distribution (how many items from each source type).
   e. Compute sentiment distribution.
   f. Extract most frequent entities across cluster members.
4. Compare new clusters to previous clustering run:
   a. If a new cluster overlaps >70% with a previous cluster → same cluster, update metadata.
   b. If a previous cluster lost >50% of its members → mark "fading".
   c. If a new cluster has no significant overlap → mark "emerging".
   d. If a previous cluster split into two → record parent_cluster_id.

### Divergence Detection

The most valuable intelligence output. For each cluster:
- Compute sub-centroids by source_type (e.g., centroid of all RSS items vs centroid of all Bluesky posts).
- If cosine distance between source-type sub-centroids exceeds threshold (e.g., 0.3), flag as "divergent framing".
- This surfaces situations where mainstream media and social media are telling fundamentally different stories about the same event.

### Anomaly Detection

- **Volume spike:** If a cluster's item count in the last 6 hours exceeds 3x its rolling 7-day average hourly rate.
- **New entity surge:** If a previously unseen entity appears in >10 items within 6 hours.
- **Sentiment shift:** If a cluster's average sentiment shifts by >0.5 within 24 hours.

### Daily Digest

Generated once per day (configurable time). LLM prompt:

```
You are a geopolitical intelligence analyst writing a daily briefing. Based on the following narrative cluster summaries and statistics, write a concise daily digest covering:

1. TOP NARRATIVES: The 3-5 most active narrative clusters, with key developments.
2. EMERGING: Any new narratives that appeared in the last 24 hours.
3. DIVERGENT: Any narratives where news sources and social media are telling different stories.
4. FADING: Narratives losing attention.
5. NOTABLE: Any anomalies (volume spikes, sentiment shifts, new entities).

Keep it under 500 words. Be factual and analytical, not sensational.

CLUSTER DATA:
{cluster_summaries_json}
```

---

## Interface

### Dashboard (web, served from VPS or static host)

**Tech stack:** Single-page app. React + Tailwind, or even plain HTML/JS with a charting library. Keep it simple — the dashboard is a demo surface, not a product. Prioritize:

1. **Cluster Map** — 2D scatter plot (UMAP reduction of cluster centroids). Each dot is a cluster, size = item count, color = sentiment. Hoverable for cluster label and summary. This is the hero screenshot.
2. **Timeline** — Horizontal timeline showing cluster activity over time. Each cluster is a swimlane. Width = volume. Shows emergence, growth, fade.
3. **Cluster Detail View** — Click a cluster to see: label, summary, key entities, key claims, source distribution bar chart, sentiment distribution, list of member items with links to originals.
4. **Search** — Semantic search across all items. "Find items about Iranian nuclear enrichment" returns semantically similar items regardless of exact keywords.
5. **Digest View** — Latest daily digest, rendered as readable text.
6. **Source Health** — Simple status page showing last fetch time and error count per source.

### CLI

```bash
amon status                    # show source health, item counts, cluster counts
amon search "iranian drones"   # semantic search
amon clusters                  # list active clusters with labels
amon cluster <id>              # show cluster detail
amon digest                    # show latest daily digest
amon ingest --now              # trigger immediate ingestion cycle
amon enrich --now              # trigger immediate enrichment cycle
amon cluster --now             # trigger immediate clustering cycle
```

### REST API

```
GET  /api/clusters                   # list active clusters
GET  /api/clusters/:id               # cluster detail with member items
GET  /api/search?q=<query>           # semantic search
GET  /api/items?since=<datetime>     # recent items
GET  /api/digest/latest              # latest daily digest
GET  /api/health                     # source and pipeline status
```

---

## Demo Configuration (for launch day)

### Monitored Narratives (3 active threads)

1. **US/Israel/Iran** — Wire services, Times of Israel, Tehran Times, think tank analysis, Bluesky discourse. Highest immediacy, potential for real-time narrative divergence between sources.

2. **US-China Relations** — SCMP, NHK, wire services, trade/semiconductor focused RSS. Slower-moving but consistently active, good for showing narrative evolution over weeks.

3. **AI Governance & Regulation** — Tech press, government feeds, think tanks, very active Bluesky community. Relevant to the audience who will see this tool.

### Demo Instance

- Public URL (Hetzner VPS + domain)
- Pre-loaded with ~2 weeks of data before launch
- Auto-updating in real-time
- README links to live instance

---

## Hosting & Deployment

### Minimum Viable Infrastructure

| Component | Service | Cost |
|-----------|---------|------|
| Compute | Hetzner CX22 (4GB RAM, 40GB disk) | ~$4.50/mo |
| Vector DB | Qdrant Cloud free tier (1GB) | Free |
| LLM Enrichment | Anthropic Haiku API | ~$8-15/mo |
| Embeddings | sentence-transformers (local on VPS) | Free |
| Domain | Any registrar | ~$12/yr |
| Dashboard hosting | Served from same VPS (nginx) | Free |
| **Total** | | **~$15-25/mo** |

### Self-Hosted Option (documented in README)

For users who want zero cloud dependencies:
- Replace Qdrant Cloud with local Qdrant (Docker)
- Replace Anthropic Haiku with Ollama + Llama 3.1 8B or Mistral 7B
- Needs beefier VPS (8GB+ RAM) or local machine
- Total cost: VPS only (~$8/mo) or free on local hardware

### Docker Compose (for easy deployment)

```yaml
services:
  amon-hen:
    build: .
    env_file: .env
    volumes:
      - ./data:/app/data          # SQLite + config
      - ./sources.yaml:/app/sources.yaml
    ports:
      - "8080:8080"               # dashboard + API

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - ./qdrant_data:/qdrant/storage
    ports:
      - "6333:6333"
```

---

## Build Plan

### Week 1: Core Pipeline (end-to-end working)

**Goal:** Items flow from sources → enrichment → Qdrant. Basic CLI search works.

- [ ] Project scaffolding (Python, pyproject.toml, basic project structure)
- [ ] Data models (dataclasses as specified above)
- [ ] Source ingestion: RSS parser (feedparser), GDELT Doc API client (gdeltdoc), basic Bluesky keyword filter (atproto)
- [ ] Deduplication (URL-exact + optional semantic similarity check)
- [ ] LLM enrichment pipeline (async, with cost tracking, daily budget cap)
- [ ] Embedding pipeline (sentence-transformers local)
- [ ] Qdrant storage (create collection, upsert, basic search)
- [ ] SQLite schema and basic CRUD
- [ ] CLI: `status`, `search`, `ingest --now`, `enrich --now`
- [ ] Cron-based scheduling for ingestion + enrichment
- [ ] Config loading from sources.yaml and .env

### Week 2: Intelligence + Dashboard

**Goal:** Clustering works. Dashboard shows cluster map. This is the screenshot week.

- [ ] HDBSCAN clustering pipeline
- [ ] Cluster labeling (LLM)
- [ ] Cluster tracking (match new clusters to previous, detect emerging/fading)
- [ ] Divergence detection (source-type sub-centroids)
- [ ] Anomaly detection (volume spikes, sentiment shifts)
- [ ] Daily digest generation
- [ ] Dashboard: cluster map (UMAP 2D projection, interactive)
- [ ] Dashboard: timeline view
- [ ] Dashboard: cluster detail view
- [ ] Dashboard: semantic search
- [ ] Dashboard: digest view
- [ ] REST API endpoints
- [ ] CLI: `clusters`, `cluster <id>`, `digest`

### Week 3: Polish + Launch

**Goal:** Public instance running. README is killer. Demo video recorded.

- [ ] Deploy to Hetzner VPS with Docker Compose
- [ ] Pre-load 2 weeks of data for demo topics
- [ ] README: sharp, no fluff, screenshots, architecture diagram, quick-start
- [ ] 90-second demo video (screen recording of dashboard in action)
- [ ] Self-hosted documentation (Ollama + local Qdrant instructions)
- [ ] Source health monitoring and error handling
- [ ] Rate limiting and retry logic for all external APIs
- [ ] Data lifecycle (30-day rolling window cleanup)
- [ ] Launch: post on X, Bluesky, Hacker News

---

## Technical Dependencies

### Project Structure

```
amon-hen/
├── src/amon_hen/
│   ├── __init__.py
│   ├── cli.py              # Click CLI entry point → `amon` binary
│   ├── config.py            # sources.yaml + .env loading
│   ├── models.py            # dataclasses (RawItem, EnrichedItem, etc.)
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── rss.py
│   │   ├── gdelt.py
│   │   ├── bluesky.py
│   │   └── reddit.py
│   ├── enrichment/
│   │   ├── __init__.py
│   │   ├── llm.py           # enrichment prompt + provider abstraction
│   │   └── embeddings.py    # sentence-transformers
│   ├── intelligence/
│   │   ├── __init__.py
│   │   ├── clustering.py    # HDBSCAN + cluster tracking
│   │   ├── divergence.py    # source-type framing divergence
│   │   ├── anomalies.py     # volume/sentiment/entity spikes
│   │   └── digest.py        # daily digest generation
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── sqlite.py        # metadata store
│   │   └── vectors.py       # Qdrant operations
│   └── api/
│       ├── __init__.py
│       └── server.py        # FastAPI routes
├── dashboard/               # frontend (static or React)
├── sources.yaml             # default source configuration
├── docker-compose.yml
├── pyproject.toml
├── README.md
└── .env.example
```

```
# Core
python >= 3.11
feedparser            # RSS parsing
httpx                 # async HTTP client
apscheduler           # cron scheduling
pydantic              # data validation

# LLM
anthropic             # Claude API client (or openai for compatible APIs)
# OR ollama           # local LLM

# Embeddings & Vector
sentence-transformers # local embeddings
qdrant-client         # Qdrant SDK

# Clustering
hdbscan               # narrative clustering
umap-learn            # dimensionality reduction for visualization
numpy
scikit-learn

# Social
atproto               # Bluesky AT Protocol client
praw                  # Reddit API client

# GDELT
gdeltdoc              # GDELT 2.0 Doc API client

# Web / Dashboard
fastapi               # API server
uvicorn               # ASGI server
jinja2                # templates (if server-rendered)
# OR: React frontend served as static files

# Storage
sqlite3               # built-in
```

---

## Design Principles

1. **Pipeline architecture is the product.** The value isn't any single component — it's that unstructured content goes in one end and navigable narrative intelligence comes out the other. This is the same pattern as Vaire (audio → enrichment → semantic search), Local Historian (civic data → enrichment → structured intelligence), and what Vannevar/Primer/Recorded Future do commercially.

2. **Source diversity is a feature, not a bug.** Tag everything by source type. Let clustering reveal when sources diverge. Don't try to determine truth — surface framing differences. Put this philosophy in the README.

3. **Self-hostable is non-negotiable.** The OSINT community won't trust a tool that requires sending their queries to your server. Docker Compose + Ollama + local Qdrant = runs on a laptop with no external dependencies.

4. **The README is as important as the code.** Write it like a portfolio piece. Architecture diagram, clear screenshots, 30-second "what is this and why does it exist," quick-start that actually works. This is what hiring managers will read.

5. **Scope ruthlessly.** 30-day rolling window. 3 demo topics. No user accounts. No auth. No multi-tenancy. No mobile. Ship something that works and looks impressive in screenshots within 3 weeks.

---

## What Success Looks Like

- Public instance running at amonhen.dev (or similar) with live data
- GitHub repo with clean code, good README, architecture diagram
- 90-second demo video showing real narrative clusters forming around current events
- At least one moment where the tool surfaces a genuine narrative divergence that's interesting to talk about in an interview
- Portfolio page updated with Amon Hen as the lead project
- Posted on X/Bluesky/HN with demo video, tagged to OSINT community

**The interview line:** "I built Amon Hen, an open-source narrative intelligence platform that tracks how stories emerge and mutate across 75+ news sources and social media in real-time. It's the same pipeline architecture — ingest, enrich, embed, cluster — that I've applied to audio discovery, civic data, and scientific literature. The name is Tolkien — the Seat of Seeing. One vantage point across every source."
