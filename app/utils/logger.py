"""
Logger re-export for backward compatibility.

The actual logging implementation is in app.utils.logging_service,
which provides a simple print-based pipeline logger.

This module re-exports pipeline_logger so all existing call sites
(e.g., pipeline_logger.info(...)) continue to work without any changes.
"""

from app.utils.logging_service import pipeline_logger, PipelineLogger

__all__ = ["pipeline_logger", "PipelineLogger"]
