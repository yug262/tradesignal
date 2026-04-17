"""Config API router."""

from fastapi import APIRouter
from models import SystemConfig

router = APIRouter(prefix="/api/config", tags=["config"])


def _get_store():
    from main import app_state
    return app_state


def _default_config() -> SystemConfig:
    return SystemConfig()


def _validate_config(config: SystemConfig) -> bool:
    if config.capital <= 0:
        return False
    if config.risk_per_trade_pct < 0.5 or config.risk_per_trade_pct > 5.0:
        return False
    if config.min_rr < 1.0:
        return False
    if config.max_open_positions < 1 or config.max_open_positions > 20:
        return False
    if config.polling_interval_mins < 1:
        return False
    return True


@router.get("")
def get_config():
    state = _get_store()
    return state.config.model_dump()


@router.put("")
def update_config(cfg: SystemConfig):
    state = _get_store()
    if _validate_config(cfg):
        state.config = cfg
        return {"success": True}
    return {"success": False}


@router.post("/reset")
def reset_config():
    state = _get_store()
    defaults = _default_config()
    state.config = defaults
    return defaults.model_dump()
