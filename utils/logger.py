"""Logging utilities for mac-cleaner."""
import logging
from pathlib import Path

def setup_logger():
    """Setup file logger for cleaning history."""
    log_dir = Path.home() / ".mac-cleaner"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "history.log"
    
    logger = logging.getLogger("mac-cleaner-history")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

history_logger = setup_logger()

def log_cleaning_action(action: str, target: str, dry_run: bool = False):
    """Log a cleaning action."""
    prefix = "[DRY-RUN] " if dry_run else ""
    history_logger.info(f"{prefix}{action}: {target}")
