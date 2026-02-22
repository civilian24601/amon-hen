"""CLI for Amon Hen narrative intelligence platform."""

from __future__ import annotations

import asyncio
import logging
import sys

import click

from amon_hen.config import Settings, get_settings, get_sources


def _run(coro):
    """Run an async coroutine from a sync Click command."""
    return asyncio.run(coro)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def cli(verbose: bool):
    """Amon Hen — Narrative Intelligence Platform."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


@cli.command()
def status():
    """Show platform status: item/cluster counts, cost, source health."""
    settings = get_settings()
    from amon_hen.storage import get_stores

    sqlite, vectors = get_stores(settings)

    item_count = sqlite.get_item_count()
    cluster_count = sqlite.get_cluster_count()
    total_cost = sqlite.get_total_cost()
    vector_info = vectors.get_collection_info()

    click.echo(f"Items:    {item_count}")
    click.echo(f"Clusters: {cluster_count}")
    click.echo(f"Vectors:  {vector_info['points_count']}")
    click.echo(f"Total cost: ${total_cost:.4f}")
    click.echo()

    # Source health
    statuses = sqlite.get_all_source_status()
    if statuses:
        click.echo("Source Health:")
        for s in statuses:
            status_str = "OK" if s.error_count == 0 else f"ERR({s.error_count})"
            last = s.last_fetch_at.strftime("%Y-%m-%d %H:%M") if s.last_fetch_at else "never"
            click.echo(f"  {s.source_name:<25} {status_str:<10} last={last}  items={s.items_fetched}")
    else:
        click.echo("No source status recorded yet.")


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=20, help="Number of results")
def search(query: str, limit: int):
    """Semantic search across enriched items."""
    settings = get_settings()
    from amon_hen.enrichment.embeddings import EmbeddingService
    from amon_hen.storage import get_stores

    sqlite, vectors = get_stores(settings)
    embedder = EmbeddingService()
    query_vec = embedder.embed_query(query)
    results = vectors.search(query_vec, limit=limit)

    if not results:
        click.echo("No results found.")
        return

    for i, r in enumerate(results, 1):
        title = r.payload.get("title", "Untitled")
        summary = r.payload.get("summary", "")[:100]
        source = r.payload.get("source_name", "?")
        click.echo(f"{i}. [{r.score:.3f}] {title}")
        click.echo(f"   Source: {source}")
        if summary:
            click.echo(f"   {summary}...")
        click.echo()


@cli.command()
def clusters():
    """List active narrative clusters."""
    settings = get_settings()
    from amon_hen.storage import get_stores

    sqlite, _ = get_stores(settings)
    active = sqlite.get_active_clusters()

    if not active:
        click.echo("No active clusters.")
        return

    for c in active:
        click.echo(f"[{c.status.value:>8}] {c.label}")
        click.echo(f"  ID: {c.id}  Items: {c.item_count}")
        click.echo(f"  Sources: {c.source_distribution}")
        click.echo(f"  Summary: {c.summary[:120]}")
        click.echo()


@cli.command()
@click.argument("cluster_id")
def cluster(cluster_id: str):
    """Show detail for a specific cluster."""
    settings = get_settings()
    from amon_hen.storage import get_stores

    sqlite, _ = get_stores(settings)
    c = sqlite.get_cluster(cluster_id)

    if not c:
        click.echo(f"Cluster {cluster_id} not found.")
        return

    click.echo(f"Cluster: {c.label}")
    click.echo(f"Status: {c.status.value}")
    click.echo(f"Items: {c.item_count}")
    click.echo(f"First seen: {c.first_seen}")
    click.echo(f"Summary: {c.summary}")
    click.echo(f"Key entities: {', '.join(c.key_entities)}")
    click.echo(f"Key claims: {', '.join(c.key_claims)}")
    click.echo(f"Source distribution: {c.source_distribution}")
    click.echo(f"Sentiment distribution: {c.sentiment_distribution}")
    click.echo()

    items = sqlite.get_items_by_cluster(cluster_id)
    click.echo(f"Member items ({len(items)}):")
    for item in items[:20]:
        click.echo(f"  - [{item.source_type.value}] {item.title or item.summary[:60]}")


@cli.command()
def digest():
    """Show the latest intelligence digest."""
    settings = get_settings()
    from amon_hen.storage import get_stores

    sqlite, _ = get_stores(settings)
    d = sqlite.get_latest_digest()

    if not d:
        click.echo("No digest available yet.")
        return

    click.echo(f"Digest generated: {d.generated_at}")
    click.echo(f"Clusters: {d.cluster_count}  Items: {d.item_count}")
    click.echo()
    click.echo(d.content)


@cli.command("ingest")
@click.option("--now", is_flag=True, help="Run immediately")
def ingest_cmd(now: bool):
    """Trigger source ingestion."""
    from amon_hen.sources import run_ingestion

    items = _run(run_ingestion())
    click.echo(f"Ingested {len(items)} new items.")


@cli.command("enrich")
@click.option("--now", is_flag=True, help="Run immediately")
def enrich_cmd(now: bool):
    """Trigger LLM enrichment on un-enriched items."""
    click.echo("Enrichment requires ingested but un-enriched items.")
    click.echo("Use 'amon ingest' first, then the enrichment coordinator will process them.")


@cli.command("recluster")
@click.option("--now", is_flag=True, help="Run immediately")
def recluster_cmd(now: bool):
    """Trigger re-clustering of all items."""
    from amon_hen.intelligence import run_intelligence_pipeline

    settings = get_settings()
    from amon_hen.storage import get_stores

    sqlite, vectors = get_stores(settings)
    result = _run(run_intelligence_pipeline(settings, sqlite, vectors))

    clusters = result["clusters"]
    divergences = result["divergences"]
    anomalies = result["anomalies"]
    all_anomalies = (
        anomalies.get("volume_spikes", [])
        + anomalies.get("sentiment_shifts", [])
        + anomalies.get("entity_surges", [])
    )

    click.echo(f"Clustering complete: {len(clusters)} clusters")
    click.echo(f"Divergences: {len(divergences)}")
    click.echo(f"Anomalies: {len(all_anomalies)}")


@cli.command()
@click.option("--days", default=7, help="Number of days to backfill")
def seed(days: int):
    """Seed the database with historical data via GDELT backfill."""
    async def _seed():
        settings = get_settings()
        sources_config = get_sources(settings)
        from amon_hen.sources.gdelt import fetch_gdelt_backfill
        from amon_hen.storage import get_stores

        sqlite, vectors = get_stores(settings)

        click.echo(f"Seeding {days} days of GDELT historical data...")
        gdelt_items = await fetch_gdelt_backfill(sources_config.gdelt, days=days)
        click.echo(f"GDELT backfill: {len(gdelt_items)} articles")

        # Also fetch current RSS/Bluesky/Reddit snapshots
        from amon_hen.sources import run_ingestion
        current_items = await run_ingestion(settings, sources_config, sqlite)
        click.echo(f"Current sources: {len(current_items)} items")

        total = len(gdelt_items) + len(current_items)
        click.echo(f"Total seeded: {total} items")
        click.echo("Run 'amon enrich --now' followed by 'amon recluster --now' to process.")

    _run(_seed())


@cli.command("validate-sources")
def validate_sources():
    """Validate all RSS feed URLs in sources.yaml."""
    import httpx

    settings = get_settings()
    sources = get_sources(settings)

    click.echo(f"Validating {len(sources.rss)} RSS feeds...")
    alive = 0
    dead = 0

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for feed in sources.rss:
            try:
                resp = client.get(feed.url)
                if resp.status_code < 400:
                    click.echo(f"  OK   {feed.name} ({feed.url})")
                    alive += 1
                else:
                    click.echo(f"  FAIL {feed.name} ({feed.url}) — HTTP {resp.status_code}")
                    dead += 1
            except Exception as e:
                click.echo(f"  FAIL {feed.name} ({feed.url}) — {e}")
                dead += 1

    click.echo(f"\nResults: {alive} alive, {dead} dead out of {len(sources.rss)} feeds")


@cli.command()
@click.option("--host", default="0.0.0.0", help="Bind host")
@click.option("--port", default=8080, help="Bind port")
def serve(host: str, port: int):
    """Start the API server with scheduler."""
    import uvicorn

    from amon_hen.api.server import create_app

    app = create_app()
    click.echo(f"Starting Amon Hen server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    cli()
