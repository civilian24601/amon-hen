"""Configuration loading for Amon Hen."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# --- Source config sub-models ---


class RSSSourceConfig(BaseModel):
    name: str
    url: str
    category: str = "uncategorized"
    refresh_minutes: int = 30


class GDELTQueryConfig(BaseModel):
    name: str
    keywords: list[str]
    refresh_minutes: int = 15


class GDELTConfig(BaseModel):
    enabled: bool = True
    queries: list[GDELTQueryConfig] = Field(default_factory=list)


class BlueskyConfig(BaseModel):
    enabled: bool = True
    filter_mode: str = "keyword"
    keywords: list[str] = Field(default_factory=list)
    max_posts_per_cycle: int = 200
    refresh_minutes: int = 5


class RedditSubredditConfig(BaseModel):
    name: str
    sort: str = "hot"
    limit: int = 25


class RedditConfig(BaseModel):
    enabled: bool = True
    subreddits: list[RedditSubredditConfig] = Field(default_factory=list)
    include_top_comments: int = 3
    refresh_minutes: int = 30


class SourcesConfig(BaseModel):
    rss: list[RSSSourceConfig] = Field(default_factory=list)
    gdelt: GDELTConfig = Field(default_factory=GDELTConfig)
    bluesky: BlueskyConfig = Field(default_factory=BlueskyConfig)
    reddit: RedditConfig = Field(default_factory=RedditConfig)


# --- Enrichment / clustering config ---


class EnrichmentConfig(BaseModel):
    provider: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"
    track_costs: bool = True
    daily_budget_usd: float = 2.00


class ClusteringConfig(BaseModel):
    min_cluster_size: int = 5
    min_samples: int = 4  # sklearn convention: includes the point itself
    rolling_window_days: int = 30
    divergence_threshold: float = 0.3


# --- Main settings ---


class Settings(BaseSettings):
    # Secrets
    anthropic_api_key: str = ""
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "amon-hen/0.1"
    bluesky_handle: str = ""
    bluesky_app_password: str = ""

    # Budget
    enrichment_daily_budget_usd: float = 2.00

    # Paths
    data_dir: Path = Path("data")
    sources_yaml_path: Path = Path("sources.yaml")
    sqlite_path: Path = Path("data/amon_hen.db")
    qdrant_local_path: Path = Path("data/qdrant")

    # Mode
    qdrant_mode: str = "local"  # "local" | "cloud" | "memory"

    # Enrichment
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)

    # Clustering
    clustering: ClusteringConfig = Field(default_factory=ClusteringConfig)

    model_config = {"env_file": ".env", "env_prefix": "", "extra": "ignore"}


def load_sources_config(path: Path) -> SourcesConfig:
    """Load and validate sources.yaml."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    return SourcesConfig(**raw)


@lru_cache
def get_settings() -> Settings:
    """Get application settings (cached singleton)."""
    return Settings()


def get_sources(settings: Settings | None = None) -> SourcesConfig:
    """Get sources configuration."""
    if settings is None:
        settings = get_settings()
    return load_sources_config(settings.sources_yaml_path)
