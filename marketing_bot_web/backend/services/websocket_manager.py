"""
WebSocket Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

실시간 업데이트를 위한 WebSocket 관리
"""

from typing import List, Dict, Any
from fastapi import WebSocket
import json
import asyncio
import time


class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # [성능 최적화] 마지막 활동 시간 추적 (좀비 연결 감지용)
        self._last_activity: Dict[WebSocket, float] = {}
        self._cleanup_task: asyncio.Task = None
        self._zombie_timeout = 300  # 5분 무응답 시 좀비 연결로 간주

    async def connect(self, websocket: WebSocket):
        """클라이언트 연결"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self._last_activity[websocket] = time.time()
        print(f"✅ WebSocket 클라이언트 연결 (총 {len(self.active_connections)}개)")

        # 첫 연결 시 cleanup 태스크 시작
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    def disconnect(self, websocket: WebSocket):
        """클라이언트 연결 해제"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        # [성능 최적화] 활동 시간 추적 정리
        self._last_activity.pop(websocket, None)
        print(f"❌ WebSocket 클라이언트 연결 해제 (총 {len(self.active_connections)}개)")

    async def send_message(self, websocket: WebSocket, message: Dict[str, Any]):
        """특정 클라이언트에게 메시지 전송"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"메시지 전송 실패: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        """모든 연결된 클라이언트에게 브로드캐스트"""
        disconnected = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
                # [성능 최적화] 성공 시 활동 시간 업데이트
                self._last_activity[connection] = time.time()
            except Exception as e:
                print(f"브로드캐스트 실패: {e}")
                disconnected.append(connection)

        # 연결 끊긴 클라이언트 제거
        for conn in disconnected:
            self.disconnect(conn)

    def update_activity(self, websocket: WebSocket):
        """[성능 최적화] 클라이언트 활동 시간 업데이트 (ping 수신 시)"""
        if websocket in self.active_connections:
            self._last_activity[websocket] = time.time()

    async def _periodic_cleanup(self):
        """
        [성능 최적화] 좀비 연결 정리 태스크
        - 5분 동안 무응답인 연결 감지 및 제거
        - 60초마다 체크
        """
        while self.active_connections:
            await asyncio.sleep(60)

            current_time = time.time()
            zombies = []

            for connection in self.active_connections:
                last_seen = self._last_activity.get(connection, current_time)
                if current_time - last_seen > self._zombie_timeout:
                    zombies.append(connection)
                    print(f"🧟 좀비 연결 감지 ({current_time - last_seen:.0f}초 무응답)")

            # 좀비 연결 정리
            for zombie in zombies:
                try:
                    await zombie.close()
                except Exception:
                    pass
                self.disconnect(zombie)

            if zombies:
                print(f"🧹 좀비 연결 {len(zombies)}개 정리됨")

    async def send_hud_update(self, data: Dict[str, Any]):
        """HUD 메트릭 업데이트 전송"""
        await self.broadcast({
            'type': 'hud_update',
            'data': data
        })

    async def send_pathfinder_progress(self, progress: int, message: str):
        """Pathfinder 진행 상황 전송"""
        await self.broadcast({
            'type': 'pathfinder_progress',
            'data': {
                'progress': progress,
                'message': message
            }
        })

    async def send_pathfinder_complete(self, stats: Dict[str, Any]):
        """Pathfinder 완료 전송"""
        await self.broadcast({
            'type': 'pathfinder_complete',
            'data': stats
        })

    async def send_ranking_update(self, keyword: str, rank: int):
        """순위 업데이트 전송"""
        await self.broadcast({
            'type': 'ranking_update',
            'data': {
                'keyword': keyword,
                'rank': rank
            }
        })

    async def send_new_lead(self, lead: Dict[str, Any]):
        """새 리드 발견 전송"""
        await self.broadcast({
            'type': 'new_lead',
            'data': lead
        })

    async def send_viral_target_update(self, target: Dict[str, Any]):
        """바이럴 타겟 업데이트 전송"""
        await self.broadcast({
            'type': 'viral_target_update',
            'data': target
        })

    async def send_scheduler_status(self, status: str, task: str):
        """스케줄러 상태 전송"""
        await self.broadcast({
            'type': 'scheduler_status',
            'data': {
                'status': status,
                'task': task
            }
        })

    async def send_pathfinder_log(self, line: str):
        """Pathfinder 실시간 로그 전송"""
        await self.broadcast({
            'type': 'pathfinder_log',
            'data': {
                'line': line,
                'timestamp': None  # 프론트엔드에서 현재 시간 사용
            }
        })

    async def send_pathfinder_status(self, status_data: dict):
        """Pathfinder 상태 전송 (running/completed/idle)"""
        await self.broadcast({
            'type': 'pathfinder_status',
            'data': status_data
        })


# 전역 WebSocket 매니저 인스턴스
ws_manager = WebSocketManager()
