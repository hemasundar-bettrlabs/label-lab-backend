"""
Log Broadcasting Store

Broadcasts all backend logs to connected SSE clients over WebSocket/SSE.
Bridges the sync/async boundary: loguru sink (sync) → asyncio.Queue subscribers (async).

Architecture:
- loguru BrowserLogSink → LogBroadcaster.emit(record) [SYNC, thread-safe]
- LogBroadcaster.emit() → loop.call_soon_threadsafe(queue.put_nowait, entry) [async-safe]
- GET /api/logs/stream → subscribe() → drains queue with SSE events
- Late subscribers get replay of last 200 entries (deque buffer)
"""

import asyncio
import threading
import json
from collections import deque
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any


class LogBroadcaster:
    """
    Thread-safe log broadcaster that routes sync loguru messages to async SSE queues.
    
    Usage:
        1. loguru sink calls: broadcaster.emit(message_record)
        2. SSE endpoint calls: past_logs, queue = broadcaster.subscribe()
        3. SSE generator: event = await queue.get(); yield f"event: log\ndata: {json.dumps(event)}\n\n"
        4. On disconnect: broadcaster.unsubscribe(queue)
    """
    
    def __init__(self, buffer_size: int = 200):
        """
        Initialize broadcaster.
        
        Args:
            buffer_size: Number of log entries to buffer for late-joining clients
        """
        self._buffer: deque = deque(maxlen=buffer_size)
        self._subscribers: List[asyncio.Queue] = []
        self._lock = threading.Lock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
    
    def _get_event_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Get the running event loop (if any)."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return None
    
    def emit(self, record: Any) -> None:
        """
        Emit a log record from loguru sink (SYNC, thread-safe).
        
        Called by loguru's BrowserLogSink. Records are parsed and sent to all SSE subscribers.
        
        Args:
            record: loguru record object with .message, .level.name, .name, .time
        """
        try:
            # Parse the log record
            timestamp = record["time"].strftime("%H:%M:%S.%f")[:-3]  # HH:MM:SS.mmm
            level = record["level"].name  # "INFO", "ERROR", "WARNING", etc.
            module_name = record["name"]  # "app.services.analysis_engine", etc.
            message = record["message"]  # Full formatted message text
            
            # Build the log entry dict
            log_entry = {
                "timestamp": timestamp,
                "level": level,
                "name": module_name,
                "message": message
            }
            
            # Send to all async subscribers (thread-safe)
            self._emit_log_entry(log_entry)
        
        except Exception as e:
            # Avoid infinite recursion: don't log errors from the logger itself
            import sys
            print(f"[LogBroadcaster.emit] Error: {e}", file=sys.stderr)
    
    def emit_dict(self, log_entry: Dict[str, str]) -> None:
        """
        Emit a pre-built log entry dict (SYNC, thread-safe).
        
        Called by BrowserLogSink which has already parsed the loguru record.
        
        Args:
            log_entry: Dict with keys: timestamp, level, name, message
        """
        try:
            # Send to all async subscribers (thread-safe)
            self._emit_log_entry(log_entry)
        
        except Exception as e:
            import sys
            print(f"[LogBroadcaster.emit_dict] Error: {e}", file=sys.stderr)
    
    def _emit_log_entry(self, log_entry: Dict[str, str]) -> None:
        """
        Internal method to emit a log entry to all subscribers (thread-safe).
        
        Args:
            log_entry: Pre-formatted log entry dict
        """
        # Buffer for late-joining clients
        with self._lock:
            self._buffer.append(log_entry)
            subscribers_snapshot = list(self._subscribers)
        
        # Send to all async subscribers (thread-safe)
        loop = self._get_event_loop()
        if loop:
            for queue in subscribers_snapshot:
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, log_entry)
                except RuntimeError:
                    # Event loop may have been closed
                    pass
    
    async def subscribe(self) -> Tuple[List[Dict[str, str]], asyncio.Queue]:
        """
        Subscribe a new SSE client.
        
        Returns:
            (past_logs, queue) where past_logs is the buffer of recent entries,
            and queue is an asyncio.Queue where future log entries will be put.
        
        The caller should:
            1. Yield all items from past_logs
            2. Then await queue.get() in a loop for new entries
            3. Call unsubscribe(queue) when done
        """
        queue = asyncio.Queue()
        
        with self._lock:
            self._subscribers.append(queue)
            past_logs = list(self._buffer)
        
        return past_logs, queue
    
    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        """
        Unsubscribe an SSE client (call on disconnect).
        
        Args:
            queue: The queue returned from subscribe()
        """
        with self._lock:
            try:
                self._subscribers.remove(queue)
            except ValueError:
                # Queue may have been removed already
                pass


# Singleton broadcaster instance
log_broadcaster = LogBroadcaster()

__all__ = ["LogBroadcaster", "log_broadcaster"]
