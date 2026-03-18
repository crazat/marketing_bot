"""
FileWatcher Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

로그 파일 변경 감지 및 WebSocket 브로드캐스트
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

# watchdog은 선택적 의존성
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False
    print("⚠️ watchdog 미설치 - 폴링 모드로 동작")


class LogFileHandler(FileSystemEventHandler):
    """로그 파일 변경 이벤트 핸들러"""

    def __init__(self, log_file: str, callback: Callable):
        self.log_file = log_file
        self.callback = callback
        self.last_position = 0

        # 파일이 존재하면 끝으로 이동
        if os.path.exists(log_file):
            self.last_position = os.path.getsize(log_file)

    def on_modified(self, event):
        if event.is_directory:
            return

        # 우리가 감시하는 파일인지 확인
        if os.path.abspath(event.src_path) == os.path.abspath(self.log_file):
            self._read_new_lines()

    def _read_new_lines(self):
        """새로 추가된 줄 읽기"""
        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(self.last_position)
                new_content = f.read()
                self.last_position = f.tell()

                if new_content.strip():
                    # 새 줄들을 콜백으로 전달
                    lines = new_content.strip().split('\n')
                    for line in lines:
                        if line.strip():
                            self.callback(line)
        except Exception as e:
            print(f"로그 읽기 오류: {e}")


class FileWatcher:
    """로그 파일 감시 서비스"""

    def __init__(self, ws_manager):
        self.ws_manager = ws_manager
        self.observer: Optional[Observer] = None
        self.running = False
        self._polling_task: Optional[asyncio.Task] = None

        # 프로젝트 루트 경로 (backend -> marketing_bot_web -> marketing_bot)
        self.project_root = Path(__file__).parent.parent.parent.parent
        self.log_dir = self.project_root / 'logs'
        self.log_file = self.log_dir / 'pathfinder_live.log'
        self.status_file = self.log_dir / 'pathfinder_status.json'

        # 마지막 읽은 위치
        self._last_position = 0
        self._last_status = None

    async def start(self):
        """파일 감시 시작"""
        self.running = True

        # 로그 디렉토리 생성
        self.log_dir.mkdir(parents=True, exist_ok=True)

        if HAS_WATCHDOG:
            await self._start_watchdog()
        else:
            # watchdog 없으면 폴링 모드
            self._polling_task = asyncio.create_task(self._polling_loop())

        print(f"📁 FileWatcher 시작: {self.log_file}")

    async def stop(self):
        """파일 감시 중지"""
        self.running = False

        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=2)
            self.observer = None

        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        print("📁 FileWatcher 중지됨")

    async def _start_watchdog(self):
        """watchdog 기반 파일 감시"""
        def on_new_line(line: str):
            # asyncio 이벤트 루프에서 브로드캐스트
            asyncio.create_task(self._broadcast_log(line))

        handler = LogFileHandler(str(self.log_file), on_new_line)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.log_dir), recursive=False)
        self.observer.start()

        # 상태 파일 폴링 (별도 태스크)
        self._polling_task = asyncio.create_task(self._status_polling_loop())

    async def _polling_loop(self):
        """폴링 기반 파일 감시 (watchdog 없을 때)"""
        while self.running:
            try:
                await self._check_log_file()
                await self._check_status_file()
                await asyncio.sleep(0.5)  # 500ms 간격
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"폴링 오류: {e}")
                await asyncio.sleep(1)

    async def _status_polling_loop(self):
        """상태 파일만 폴링 (watchdog 모드에서 사용)"""
        while self.running:
            try:
                await self._check_status_file()
                await asyncio.sleep(1)  # 1초 간격
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"상태 폴링 오류: {e}")
                await asyncio.sleep(1)

    async def _check_log_file(self):
        """로그 파일 변경 확인"""
        if not self.log_file.exists():
            return

        try:
            current_size = self.log_file.stat().st_size

            if current_size > self._last_position:
                with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    f.seek(self._last_position)
                    new_content = f.read()
                    self._last_position = f.tell()

                    if new_content.strip():
                        lines = new_content.strip().split('\n')
                        for line in lines:
                            if line.strip():
                                await self._broadcast_log(line)

            elif current_size < self._last_position:
                # 파일이 새로 시작됨 (truncated)
                self._last_position = 0
                with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    self._last_position = f.tell()
                    if content.strip():
                        lines = content.strip().split('\n')
                        for line in lines:
                            if line.strip():
                                await self._broadcast_log(line)

        except Exception as e:
            print(f"로그 파일 읽기 오류: {e}")

    async def _check_status_file(self):
        """상태 파일 변경 확인"""
        if not self.status_file.exists():
            return

        try:
            with open(self.status_file, 'r', encoding='utf-8') as f:
                status_data = json.load(f)

            # 상태가 변경되었으면 브로드캐스트
            if status_data != self._last_status:
                self._last_status = status_data
                await self._broadcast_status(status_data)

        except Exception as e:
            pass  # 상태 파일 읽기 실패는 무시

    async def _broadcast_log(self, line: str):
        """로그 라인 브로드캐스트"""
        try:
            await self.ws_manager.send_pathfinder_log(line)
        except Exception as e:
            print(f"로그 브로드캐스트 오류: {e}")

    async def _broadcast_status(self, status_data: dict):
        """상태 변경 브로드캐스트"""
        try:
            await self.ws_manager.send_pathfinder_status(status_data)
        except Exception as e:
            print(f"상태 브로드캐스트 오류: {e}")

    def get_recent_logs(self, lines: int = 50) -> list:
        """최근 로그 라인 가져오기"""
        if not self.log_file.exists():
            return []

        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
                return [line.strip() for line in all_lines[-lines:] if line.strip()]
        except (IOError, OSError):
            return []

    def get_status(self) -> dict:
        """현재 상태 가져오기"""
        if not self.status_file.exists():
            return {'status': 'idle', 'message': '대기 중'}

        try:
            with open(self.status_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError, OSError):
            return {'status': 'idle', 'message': '대기 중'}


# 전역 FileWatcher 인스턴스 (ws_manager 연결 후 설정)
file_watcher: Optional[FileWatcher] = None


def get_file_watcher() -> Optional[FileWatcher]:
    """FileWatcher 인스턴스 가져오기"""
    return file_watcher


def create_file_watcher(ws_manager) -> FileWatcher:
    """FileWatcher 인스턴스 생성"""
    global file_watcher
    file_watcher = FileWatcher(ws_manager)
    return file_watcher
