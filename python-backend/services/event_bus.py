"""Event bus for publishing events to SSE subscribers.

Provides a central pub/sub mechanism for real-time events.
Services publish events, SSE endpoint subscribes and streams to clients.

Usage:
    from services.event_bus import event_bus
    
    # Publisher (e.g., CruiseService)
    event_bus.publish_sync({"event": "cruiseUpdate", "data": {...}})
    
    # Subscriber (SSE endpoint)
    async for event in event_bus.subscribe():
        yield format_sse(event)
"""

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

logger = logging.getLogger(__name__)


class EventBus:
    """
    Central event bus that distributes events to all SSE subscribers.
    
    Thread-safe and supports multiple concurrent subscribers.
    Each subscriber gets its own queue to prevent slow consumers
    from blocking fast ones.
    """
    
    def __init__(self, max_queue_size: int = 100):
        """Initialize the event bus.
        
        Args:
            max_queue_size: Maximum events to queue per subscriber.
                           Older events are dropped if queue is full.
        """
        self._subscribers: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store a reference to the main asyncio event loop.

        Must be called from the running event loop (e.g., in run_http)
        so that publish_sync can safely schedule tasks from worker threads.

        Args:
            loop: The main asyncio event loop
        """
        self._loop = loop
        logger.debug("Event bus bound to event loop")

    async def subscribe(self) -> AsyncGenerator[dict, None]:
        """Subscribe to events. Yields events as they arrive.
        
        Usage:
            async for event in event_bus.subscribe():
                # Process event
                pass
        
        Yields:
            Event dictionaries with 'event' and 'data' keys
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._max_queue_size)
        
        async with self._lock:
            self._subscribers.add(queue)
        
        subscriber_count = len(self._subscribers)
        logger.info(f"SSE client connected (total subscribers: {subscriber_count})")
        
        try:
            while True:
                event = await queue.get()
                yield event
        except asyncio.CancelledError:
            logger.debug("SSE subscriber cancelled")
            raise
        finally:
            async with self._lock:
                self._subscribers.discard(queue)
            subscriber_count = len(self._subscribers)
            logger.info(f"SSE client disconnected (total subscribers: {subscriber_count})")
    
    async def publish(self, event: dict) -> int:
        """Publish an event to all subscribers.
        
        Args:
            event: Event dictionary to publish
            
        Returns:
            Number of subscribers that received the event
        """
        delivered = 0
        
        async with self._lock:
            for queue in self._subscribers:
                try:
                    # Use put_nowait to avoid blocking
                    queue.put_nowait(event)
                    delivered += 1
                except asyncio.QueueFull:
                    # Drop event for slow subscriber
                    logger.warning("Subscriber queue full, dropping event")
        
        return delivered
    
    def publish_sync(self, event: dict) -> None:
        """Synchronous publish - schedules async publish on the event loop.

        Thread-safe: can be called from any thread. Uses call_soon_threadsafe
        to schedule the coroutine on the main event loop.

        Args:
            event: Event dictionary to publish
        """
        if self._loop is None or self._loop.is_closed():
            logger.debug("Cannot publish event: no event loop bound (call set_loop first)")
            return
        self._loop.call_soon_threadsafe(self._loop.create_task, self.publish(event))
    
    @property
    def subscriber_count(self) -> int:
        """Get current number of subscribers."""
        return len(self._subscribers)
    
    async def close(self) -> None:
        """Close the event bus and disconnect all subscribers."""
        async with self._lock:
            # Clear all subscriber queues
            for queue in self._subscribers:
                # Put None to signal shutdown (optional)
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            self._subscribers.clear()
        logger.info("Event bus closed")


# Global singleton instance
event_bus = EventBus()
