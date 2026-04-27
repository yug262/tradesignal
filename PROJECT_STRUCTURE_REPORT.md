# ATS Backend Structure Report

This report provides a comprehensive overview of every file in the **ATS Backend** and its specific role within the automated trading system.

---

## 📁 Root Backend Directory (`/backend`)
Core application setup and infrastructure.

- **main.py**: The central entry point for the FastAPI application. It handles app initialization, middleware, and route registration.
- **database.py**: Manages the database connection pool and provides session factories using SQLAlchemy.
- **db_models.py**: Contains the primary SQL database schema definitions (e.g., `Signal`, `Trade`, `NewsArticle`, `SystemConfiguration`).
- **models.py**: Defines Pydantic schemas used for API data validation, serialization, and internal data structures.
- **requirements.txt**: The master list of Python dependencies required for the backend.
- **setup_db.py**: A script to initialize the database, create tables, and seed initial configuration data.
- **store.py**: A utility for managing global, in-memory system states and flags.
- **check_db_status.py**: A diagnostic tool to verify the health of the database and its current records.
- **reset_signals.py**: A cleanup utility to wipe signals and trades from the database for fresh testing cycles.
- **.env**: Stores sensitive environment variables (API keys, database URLs, secret tokens).
- **test_*.py**: A suite of integration tests (e.g., `test_e2e_pipeline.py`, `test_orchestrator.py`) to ensure system stability.

---

## 📁 Agents Directory (`/backend/agent`)
The intelligence and execution layer of the system.

- **scheduler.py**: The system's heartbeat; orchestrates when each agent runs based on market hours and intervals.
- **signal_generator.py (Agent 1)**: Scans for market opportunities and generates initial "Discovery" signals.
- **confirmation_agent.py (Agent 2)**: Validates signals against live market data and quantitative thresholds.
- **technical_analysis_agent.py (Agent 2.5)**: Performs multi-timeframe TA and processes visual chart data.
- **execution_agent.py (Agent 3)**: Formulates precise trade plans, including entry levels, sizing, and exit targets.
- **risk_monitor.py (Agent 4)**: Actively manages open positions, monitoring for stop-loss hits or profit targets.
- **paper_trading_engine.py**: A high-fidelity simulation engine that mimics real trade execution and tracks P&L.
- **live_news_agent.py**: Monitors live news feeds (e.g., MoneyControl) to feed the Discovery phase.
- **data_collector.py**: The bridge to external market data APIs, fetching OHLCV, depth, and snapshots.
- **market_calendar.py**: Manages the NSE market schedule, handling holidays and pre-market/post-market logic.
- **scoring_engine.py**: Ranks signals based on a multi-factor confidence model.
- **risk_rules.py**: Defines the logical constraints for trade validation (e.g., max drawdown, sector exposure).
- **risk_agent_validator.py**: Enforces risk rules before any trade plan is moved to execution.
- **risk_features.py**: Extracts and engineers data points specifically for risk assessment.
- **gemini_*.py**: A family of modules that interface with the Gemini LLM for specific reasoning tasks:
    - `gemini_analyzer.py`: News sentiment and materiality analysis.
    - `gemini_confirmer.py`: Validation reasoning for market signals.
    - `gemini_executor.py`: Strategic planning for trade execution.
    - `gemini_technical_analyzer.py`: Visual and quantitative chart analysis.
    - `gemini_risk_monitor.py`: Reasoning for dynamic position adjustments and exits.
    - `gemini_live_analyzer.py`: Real-time impact assessment of breaking news.

---

## 📁 API Routers (`/backend/routers`)
Endpoints that expose backend functionality to the frontend.

- **agent.py**: Control endpoints for triggering, pausing, or auditing AI agents.
- **news.py**: Endpoints for retrieving news feed data and associated AI analysis.
- **paper_trading.py**: Provides portfolio data, trade history, and real-time P&L metrics.
- **stocks.py**: Stock-specific data endpoints, including search and price snapshots.
- **config.py**: Handles retrieval and updates for system-wide configuration settings.
- **dashboard.py**: Aggregates high-level system health and performance metrics for the main UI.

---

## 📁 Services (`/backend/services`)
Reusable business logic and utility services.

- **indicator_service.py**: Centralized service for calculating technical indicators (RSI, EMAs, Bollinger Bands) using TA-Lib.
- **chart_generator.py**: Generates visual chart representations (JSON/PNG) for the AI's visual analysis phase.

---

## 📁 Scratch / Utilities (`/backend/scratch`)
Development tools and experimental scripts.

- **add_dummy_reliance.py**: Injects a high-quality test signal for Reliance Industries.
- **demo_rejection.py**: Tests the system's ability to correctly reject poor-quality signals.
- **test_automation.py**: Validates the end-to-end automated handoff between agents.
- **test_gaps.py**: Specifically tests the system's handling of market gap-up/gap-down scenarios.
- **test_partial_close.py**: Validates the logic for scaling out of positions partially.
- **inject_*.py**: Various scripts to force-feed specific market scenarios into the pipeline for validation.
- **check_db.py**: A quick-and-dirty script for inspecting database contents via console.
