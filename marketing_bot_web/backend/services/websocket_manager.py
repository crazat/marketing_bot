"""WebSocket connection manager for real-time UI updates."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)

EVENT_TYPES = {
    "hud_update",
    "scan_progress",
    "scan_complete",
    "rank_update",
    "ranking_update",
    "rank_alert",
    "new_lead",
    "review_detected",
    "review_response_draft",
    "viral_target_update",
    "scheduler_status",
    "competitor_change",
    "alert",
    "pathfinder_progress",
    "pathfinder_complete",
    "pathfinder_log",
    "pathfinder_status",
}


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._last_activity: Dict[WebSocket, float] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._send_timeout = 5.0
        self._zombie_timeout = 300
        self._subscriptions: Dict[WebSocket, Set[str]] = {}
        self._send_locks: Dict[WebSocket, asyncio.Lock] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        if websocket not in self.active_connections:
            self.active_connections.append(websocket)
        self._last_activity[websocket] = time.time()
        self._subscriptions[websocket] = set(EVENT_TYPES)
        self._send_locks[websocket] = asyncio.Lock()
        logger.info("WebSocket connected (%s active)", len(self.active_connections))

        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self._last_activity.pop(websocket, None)
        self._subscriptions.pop(websocket, None)
        self._send_locks.pop(websocket, None)

        if not self.active_connections and self._cleanup_task and not self._cleanup_task.done():
            try:
                current_task = asyncio.current_task()
            except RuntimeError:
                current_task = None
            if current_task is not self._cleanup_task:
                self._cleanup_task.cancel()
            self._cleanup_task = None

        logger.info("WebSocket disconnected (%s active)", len(self.active_connections))

    async def _send_json(self, websocket: WebSocket, message: Dict[str, Any]):
        lock = self._send_locks.get(websocket)
        if lock is None:
            lock = asyncio.Lock()
            self._send_locks[websocket] = lock

        async with lock:
            await asyncio.wait_for(websocket.send_json(message), timeout=self._send_timeout)

    @staticmethod
    def _normalize_event_types(event_types: Any) -> Set[str]:
        if not isinstance(event_types, list):
            return set()
        return {event_type for event_type in event_types if isinstance(event_type, str) and event_type in EVENT_TYPES}

    def subscribe(self, websocket: WebSocket, event_types: List[str]):
        valid_types = self._normalize_event_types(event_types)
        if websocket in self._subscriptions:
            self._subscriptions[websocket] = valid_types

    def unsubscribe(self, websocket: WebSocket, event_types: List[str]):
        if websocket in self._subscriptions:
            self._subscriptions[websocket] -= self._normalize_event_types(event_types)

    async def send_message(self, websocket: WebSocket, message: Dict[str, Any]):
        try:
            await self._send_json(websocket, message)
        except Exception as exc:
            logger.debug("WebSocket send failed: %s", exc)
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        disconnected = []
        event_type = message.get("type", "")

        for connection in list(self.active_connections):
            if event_type and connection in self._subscriptions:
                if event_type not in self._subscriptions[connection]:
                    continue

            try:
                await self._send_json(connection, message)
                self._last_activity[connection] = time.time()
            except Exception as exc:
                logger.debug("WebSocket broadcast failed: %s", exc)
                disconnected.append(connection)

        for connection in disconnected:
            self.disconnect(connection)

    def update_activity(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self._last_activity[websocket] = time.time()

    async def _periodic_cleanup(self):
        try:
            while self.active_connections:
                await asyncio.sleep(60)
                current_time = time.time()
                zombies = []

                for connection in list(self.active_connections):
                    last_seen = self._last_activity.get(connection, current_time)
                    if current_time - last_seen > self._zombie_timeout:
                        zombies.append(connection)

                for zombie in zombies:
                    try:
                        await zombie.close()
                    except Exception:
                        pass
                    self.disconnect(zombie)

                if zombies:
                    logger.info("Cleaned %s stale WebSocket connections", len(zombies))
        except asyncio.CancelledError:
            return

    async def send_hud_update(self, data: Dict[str, Any]):
        await self.broadcast({"type": "hud_update", "data": data})

    async def send_pathfinder_progress(self, progress: int, message: str):
        await self.broadcast(
            {
                "type": "pathfinder_progress",
                "data": {"progress": progress, "message": message},
            }
        )

    async def send_pathfinder_complete(self, stats: Dict[str, Any]):
        await self.broadcast({"type": "pathfinder_complete", "data": stats})

    async def send_ranking_update(self, keyword: str, rank: int):
        await self.broadcast(
            {
                "type": "ranking_update",
                "data": {"keyword": keyword, "rank": rank},
            }
        )

    async def send_new_lead(self, lead: Dict[str, Any]):
        await self.broadcast({"type": "new_lead", "data": lead})

    async def send_viral_target_update(self, target: Dict[str, Any]):
        await self.broadcast({"type": "viral_target_update", "data": target})

    async def send_scheduler_status(self, status: str, task: str):
        await self.broadcast(
            {
                "type": "scheduler_status",
                "data": {"status": status, "task": task},
            }
        )

    async def send_pathfinder_log(self, line: str):
        await self.broadcast(
            {
                "type": "pathfinder_log",
                "data": {"line": line, "timestamp": None},
            }
        )

    async def send_pathfinder_status(self, status_data: Dict[str, Any]):
        await self.broadcast({"type": "pathfinder_status", "data": status_data})

    async def send_scan_progress(
        self,
        module: str,
        progress: int,
        message: str,
        current: int = 0,
        total: int = 0,
    ):
        await self.broadcast(
            {
                "type": "scan_progress",
                "data": {
                    "module": module,
                    "progress": progress,
                    "message": message,
                    "current": current,
                    "total": total,
                    "timestamp": datetime.now().isoformat(),
                },
            }
        )

    async def send_scan_complete(self, module: str, result: Dict[str, Any]):
        await self.broadcast(
            {
                "type": "scan_complete",
                "data": {
                    "module": module,
                    "result": result,
                    "timestamp": datetime.now().isoformat(),
                },
            }
        )

    async def send_rank_alert(
        self,
        keyword: str,
        old_rank: int,
        new_rank: int,
        device_type: str = "mobile",
    ):
        change = old_rank - new_rank
        await self.broadcast(
            {
                "type": "rank_alert",
                "data": {
                    "keyword": keyword,
                    "old_rank": old_rank,
                    "new_rank": new_rank,
                    "change": change,
                    "direction": "up" if change > 0 else "down",
                    "device_type": device_type,
                    "timestamp": datetime.now().isoformat(),
                },
            }
        )

    async def send_review_detected(
        self,
        competitor_name: str,
        content_preview: str,
        sentiment: str = "neutral",
        star_rating: Optional[float] = None,
    ):
        await self.broadcast(
            {
                "type": "review_detected",
                "data": {
                    "competitor_name": competitor_name,
                    "content_preview": content_preview[:100],
                    "sentiment": sentiment,
                    "star_rating": star_rating,
                    "timestamp": datetime.now().isoformat(),
                },
            }
        )

    async def send_review_response_draft(self, review_id: int, draft_preview: str):
        await self.broadcast(
            {
                "type": "review_response_draft",
                "data": {
                    "review_id": review_id,
                    "draft_preview": draft_preview[:200],
                    "timestamp": datetime.now().isoformat(),
                },
            }
        )

    async def send_competitor_change(self, competitor_name: str, change_type: str, details: str):
        await self.broadcast(
            {
                "type": "competitor_change",
                "data": {
                    "competitor_name": competitor_name,
                    "change_type": change_type,
                    "details": details,
                    "timestamp": datetime.now().isoformat(),
                },
            }
        )

    async def send_alert(
        self,
        level: str,
        title: str,
        message: str,
        action_url: Optional[str] = None,
    ):
        await self.broadcast(
            {
                "type": "alert",
                "data": {
                    "level": level,
                    "title": title,
                    "message": message,
                    "action_url": action_url,
                    "timestamp": datetime.now().isoformat(),
                },
            }
        )

    async def handle_client_message(self, websocket: WebSocket, data: Dict[str, Any]):
        action = data.get("action", "")

        if action == "subscribe":
            events = data.get("events", [])
            if isinstance(events, list):
                self.subscribe(websocket, events)
        elif action == "unsubscribe":
            events = data.get("events", [])
            if isinstance(events, list):
                self.unsubscribe(websocket, events)
        elif action == "ping":
            self.update_activity(websocket)
            try:
                await self._send_json(websocket, {"type": "pong", "data": {}})
            except Exception:
                self.disconnect(websocket)


ws_manager = WebSocketManager()
