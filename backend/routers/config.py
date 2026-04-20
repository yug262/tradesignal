"""Config API router."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
import db_models
from models import SystemConfig

router = APIRouter(prefix="/api/config", tags=["config"])


def _get_store():
    from main import app_state
    return app_state


def _default_config() -> SystemConfig:
    return SystemConfig()


def _get_or_create_config(db: Session) -> db_models.DBSystemConfig:
    cfg = db.query(db_models.DBSystemConfig).first()
    if not cfg:
        defaults = _default_config()
        cfg = db_models.DBSystemConfig(
            capital=defaults.capital,
            risk_per_trade_pct=defaults.risk_per_trade_pct,
            max_open_positions=defaults.max_open_positions,
            max_daily_loss_pct=defaults.max_daily_loss_pct,
            min_rr=defaults.min_rr,
            news_endpoint_url=defaults.news_endpoint_url,
            polling_interval_mins=defaults.polling_interval_mins,
            processing_mode=defaults.processing_mode
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


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
def get_config(db: Session = Depends(get_db)):
    cfg = _get_or_create_config(db)
    # Sync in-memory state for other parts of the app that might still use it
    state = _get_store()
    state.config = SystemConfig(
        capital=cfg.capital,
        risk_per_trade_pct=cfg.risk_per_trade_pct,
        max_open_positions=cfg.max_open_positions,
        max_daily_loss_pct=cfg.max_daily_loss_pct,
        min_rr=cfg.min_rr,
        news_endpoint_url=cfg.news_endpoint_url,
        polling_interval_mins=cfg.polling_interval_mins,
        processing_mode=cfg.processing_mode
    )
    return state.config.model_dump()


@router.put("")
def update_config(new_cfg: SystemConfig, db: Session = Depends(get_db)):
    if _validate_config(new_cfg):
        cfg = _get_or_create_config(db)
        cfg.capital = new_cfg.capital
        cfg.risk_per_trade_pct = new_cfg.risk_per_trade_pct
        cfg.max_open_positions = new_cfg.max_open_positions
        cfg.max_daily_loss_pct = new_cfg.max_daily_loss_pct
        cfg.min_rr = new_cfg.min_rr
        cfg.news_endpoint_url = new_cfg.news_endpoint_url
        cfg.polling_interval_mins = new_cfg.polling_interval_mins
        cfg.processing_mode = new_cfg.processing_mode
        
        db.commit()
        
        # Sync in-memory
        state = _get_store()
        state.config = new_cfg
        return {"success": True}
    return {"success": False}


@router.post("/reset")
def reset_config(db: Session = Depends(get_db)):
    cfg = _get_or_create_config(db)
    defaults = _default_config()
    
    cfg.capital = defaults.capital
    cfg.risk_per_trade_pct = defaults.risk_per_trade_pct
    cfg.max_open_positions = defaults.max_open_positions
    cfg.max_daily_loss_pct = defaults.max_daily_loss_pct
    cfg.min_rr = defaults.min_rr
    cfg.news_endpoint_url = defaults.news_endpoint_url
    cfg.polling_interval_mins = defaults.polling_interval_mins
    cfg.processing_mode = defaults.processing_mode
    
    db.commit()
    
    # Sync in-memory
    state = _get_store()
    state.config = defaults
    return defaults.model_dump()
