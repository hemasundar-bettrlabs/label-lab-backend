"""
Simplified Print-Based Pipeline Logger for Label Validator Backend

A lightweight logging system that outputs only essential information:
- Current step/stage
- What is being processed
- Errors

Simple print-based output to terminal + optional file logging.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# Setup: Paths and Configuration
# ─────────────────────────────────────────────────────────────────────────────

LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOGS_DIR / "app.log"


# ─────────────────────────────────────────────────────────────────────────────
# Setup Function: Initialize logging
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(log_level: str = "INFO") -> None:
    """
    Initialize the simple print-based logging service.
    
    Args:
        log_level: Logging level (not used, kept for compatibility)
    """
    print(f"[{_timestamp()}] Logger initialized")


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def _timestamp() -> str:
    """Return current time as HH:MM:SS."""
    return datetime.now().strftime("%H:%M:%S")


def _write_log(message: str) -> None:
    """Write message to log file."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass  # Silently fail if can't write to file


# ─────────────────────────────────────────────────────────────────────────────
# PipelineLogger: Simple Print-Based Logger
# ─────────────────────────────────────────────────────────────────────────────

class PipelineLogger:
    """
    Simple pipeline logger using print statements.
    Shows only: current step, what's being processed, and errors.
    """
    
    def stage(self, step: int, total: int, message: str) -> None:
        """Log a stage/step marker (e.g., 'Step 1/5 - Processing')."""
        output = f"[STEP {step}/{total}] {message}"
        print(output)
        _write_log(output)
    
    def info(self, section: str, message: str) -> None:
        """Log what is currently being processed."""
        output = f"[{section}] {message}"
        print(output)
        _write_log(output)
    
    def error(self, section: str, message: str) -> None:
        """Log an error."""
        output = f"[ERROR: {section}] {message}"
        print(output)
        _write_log(output)
    
    def success(self, message: str) -> None:
        """Log a success message."""
        output = f"[SUCCESS] {message}"
        print(output)
        _write_log(output)
    
    def json_dump(self, label: str, data: dict) -> None:
        """Log a JSON structure (simplified)."""
        import json
        try:
            formatted = json.dumps(data, indent=2)
            output = f"[{label}]\n{formatted}"
            print(output)
            _write_log(f"[{label}] {formatted}")
        except Exception as e:
            output = f"[{label}] {data} (JSON error: {e})"
            print(output)
            _write_log(output)


# ─────────────────────────────────────────────────────────────────────────────
# Exports
# ─────────────────────────────────────────────────────────────────────────────

# PipelineLogger instance (for backward compatibility with existing code)
pipeline_logger = PipelineLogger()

__all__ = [
    "setup_logging",
    "pipeline_logger",
    "PipelineLogger",
]
