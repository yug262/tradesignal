"""Dashboard API router."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _get_store():
    from main import app_state
    return app_state


@router.get("/summary")
def get_dashboard_summary():
    state = _get_store()
    total = len(state.news_store)

    # 24 hours in milliseconds
    h24_ms = 86_400_000
    now_approx = 1_713_225_600_000

    processed_today = 0
    pending_count = 0

    for art in state.news_store.values():
        if art.analyzed_at >= now_approx - h24_ms:
            processed_today += 1
        if art.processing_status == "pending":
            pending_count += 1

    endpoint_status = "mock" if state.config.use_mock_data else "live"

    return {
        "total_articles_consumed": total,
        "articles_processed_today": processed_today,
        "pending_candidates": pending_count,
        "active_opportunities": 0,
        "no_trade_count": 0,
        "system_mode": state.config.processing_mode,
        "last_refresh": state.proc_state.last_poll_timestamp,
        "endpoint_status": endpoint_status,
    }


@router.get("/processing-state")
def get_processing_state():
    state = _get_store()
    return state.proc_state.model_dump()
