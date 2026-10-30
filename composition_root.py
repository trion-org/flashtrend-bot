"""The ONLY place adapters are wired into use cases."""
from __future__ import annotations

from application.check_bilibili import CheckBilibili
from application.check_media import CheckMedia
from application.digest import RunDigest
from application.observer import Observer
from domain.clock import now_vn
from infrastructure.analysis_charts import AnalysisCharts
from infrastructure.bilibili_api import BilibiliSource
from infrastructure.chart import MatplotlibChart
from infrastructure.dry_run import DryRunStore
from infrastructure.embedder import SentenceTransformerEmbedder
from infrastructure.gemini import GeminiWriter
from infrastructure.image_host import HttpImageHost, url_is_alive
from infrastructure.multi_source import MultiSource
from infrastructure.settings import Settings
from infrastructure.supabase_store import SupabaseStore
from infrastructure.youtube_api import YouTubeSource


def build_digest(settings: Settings, observer: Observer, dry_run: bool = False) -> RunDigest:
    store = SupabaseStore.connect(settings.supabase_url, settings.supabase_service_role_key)
    return RunDigest(
        store=DryRunStore(store) if dry_run else store,
        source=MultiSource(YouTubeSource.from_api_key(settings.youtube_api_key), BilibiliSource(), observer),
        embedder=SentenceTransformerEmbedder(),
        # a dry run reads real data but spends no Gemini quota and uploads nothing
        writer=None if dry_run else GeminiWriter(
            settings.gemini_api_key, settings.gemini_model, settings.lang
        ),
        image_host=HttpImageHost(settings.s3_url) if settings.s3_url and not dry_run else None,
        chart=None if dry_run else MatplotlibChart(),
        analysis=None if dry_run else AnalysisCharts(),
        observer=observer,
        max_ideas=settings.max_ideas,
        git_sha=settings.git_sha,
        trigger=settings.trigger,
    )


def build_bilibili_check(observer: Observer) -> CheckBilibili:
    """Needs no secret: Bilibili is read anonymously."""
    return CheckBilibili(BilibiliSource(), observer, now_vn)


def build_media_check(settings: Settings, observer: Observer) -> CheckMedia:
    store = SupabaseStore.connect(settings.supabase_url, settings.supabase_service_role_key)
    return CheckMedia(store, url_is_alive, observer)
