from models import SystemConfig, ProcessingState

class AppState:
    """Global mutable state container."""
    def __init__(self):
        self.config = SystemConfig()
        self.proc_state = ProcessingState()

# Singleton instance
_store = AppState()

def _get_store() -> AppState:
    return _store
