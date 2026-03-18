"""
Adaptive Scheduler - Self-Optimizing Schedule System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 2.3] 적응형 스케줄링 시스템
- 성공률 기반 스케줄 조정
- 실행 시간 분석 및 최적화
- 자원 사용량 모니터링
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class ScheduleHealth(Enum):
    """스케줄 건강도 상태"""
    HEALTHY = "healthy"      # 성공률 90% 이상
    WARNING = "warning"      # 성공률 70-90%
    CRITICAL = "critical"    # 성공률 70% 미만
    UNKNOWN = "unknown"      # 데이터 부족


@dataclass
class JobMetrics:
    """작업 메트릭"""
    job_name: str
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    avg_duration_seconds: float = 0.0
    last_run: Optional[str] = None
    last_status: str = "unknown"
    recommended_interval: Optional[int] = None  # 분 단위


@dataclass
class ScheduleRecommendation:
    """스케줄 조정 권장사항"""
    job_name: str
    current_schedule: str
    recommended_schedule: str
    reason: str
    priority: str  # high/medium/low
    auto_apply: bool = False


class AdaptiveScheduler:
    """
    적응형 스케줄러

    성공률, 실행 시간 분석을 통해 최적의 스케줄을 자동 조정
    """

    def __init__(self):
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.metrics_file = os.path.join(self.root_dir, 'db', 'schedule_metrics.json')
        self.schedule_config = os.path.join(self.root_dir, 'config', 'schedule.json')
        self.metrics: Dict[str, JobMetrics] = {}
        self._load_metrics()
        logger.info("AdaptiveScheduler initialized")

    def _load_metrics(self):
        """메트릭 로드"""
        if os.path.exists(self.metrics_file):
            try:
                with open(self.metrics_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for name, m in data.items():
                        self.metrics[name] = JobMetrics(**m)
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")

    def _save_metrics(self):
        """메트릭 저장"""
        try:
            os.makedirs(os.path.dirname(self.metrics_file), exist_ok=True)
            with open(self.metrics_file, 'w', encoding='utf-8') as f:
                json.dump(
                    {name: asdict(m) for name, m in self.metrics.items()},
                    f, indent=2, ensure_ascii=False
                )
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")

    def record_execution(
        self,
        job_name: str,
        status: str,  # success, failed, timeout
        duration_seconds: float
    ):
        """
        작업 실행 기록

        Args:
            job_name: 작업 이름
            status: 실행 상태
            duration_seconds: 실행 시간 (초)
        """
        if job_name not in self.metrics:
            self.metrics[job_name] = JobMetrics(job_name=job_name)

        m = self.metrics[job_name]
        m.total_runs += 1

        if status == "success":
            m.success_count += 1
        elif status == "failed":
            m.failure_count += 1
        elif status == "timeout":
            m.timeout_count += 1

        # 이동 평균으로 평균 시간 업데이트
        if m.avg_duration_seconds == 0:
            m.avg_duration_seconds = duration_seconds
        else:
            m.avg_duration_seconds = (m.avg_duration_seconds * 0.8 + duration_seconds * 0.2)

        m.last_run = datetime.now().isoformat()
        m.last_status = status

        self._save_metrics()

        # 자동 분석 실행 (매 10회 실행마다)
        if m.total_runs % 10 == 0:
            self._analyze_job(job_name)

    def _analyze_job(self, job_name: str):
        """작업 분석 및 권장사항 생성"""
        if job_name not in self.metrics:
            return

        m = self.metrics[job_name]

        if m.total_runs < 5:
            return  # 데이터 부족

        success_rate = m.success_count / m.total_runs * 100

        # 권장 간격 계산
        if success_rate >= 95 and m.avg_duration_seconds < 120:
            # 매우 안정적이고 빠름 → 간격 줄일 수 있음
            m.recommended_interval = max(30, int(m.avg_duration_seconds * 2))
        elif success_rate >= 80:
            # 안정적 → 현재 간격 유지
            m.recommended_interval = None
        elif success_rate >= 50:
            # 불안정 → 간격 늘림
            m.recommended_interval = int(m.avg_duration_seconds * 3)
        else:
            # 매우 불안정 → 비활성화 권장
            m.recommended_interval = -1  # 비활성화 신호

        self._save_metrics()
        logger.info(f"Job analyzed: {job_name} (success_rate={success_rate:.1f}%, recommended_interval={m.recommended_interval})")

    def get_job_health(self, job_name: str) -> ScheduleHealth:
        """작업 건강도 조회"""
        if job_name not in self.metrics:
            return ScheduleHealth.UNKNOWN

        m = self.metrics[job_name]
        if m.total_runs < 3:
            return ScheduleHealth.UNKNOWN

        success_rate = m.success_count / m.total_runs * 100

        if success_rate >= 90:
            return ScheduleHealth.HEALTHY
        elif success_rate >= 70:
            return ScheduleHealth.WARNING
        else:
            return ScheduleHealth.CRITICAL

    def get_recommendations(self) -> List[ScheduleRecommendation]:
        """스케줄 조정 권장사항 목록 반환"""
        recommendations = []

        for name, m in self.metrics.items():
            if m.total_runs < 5:
                continue

            success_rate = m.success_count / m.total_runs * 100
            health = self.get_job_health(name)

            if health == ScheduleHealth.CRITICAL:
                recommendations.append(ScheduleRecommendation(
                    job_name=name,
                    current_schedule="Unknown",
                    recommended_schedule="비활성화 또는 간격 증가",
                    reason=f"성공률 {success_rate:.1f}%로 매우 낮음. 타임아웃 {m.timeout_count}회 발생.",
                    priority="high",
                    auto_apply=False
                ))

            elif health == ScheduleHealth.WARNING:
                recommendations.append(ScheduleRecommendation(
                    job_name=name,
                    current_schedule="Unknown",
                    recommended_schedule="간격 1.5배 증가 권장",
                    reason=f"성공률 {success_rate:.1f}%로 불안정. 평균 실행시간 {m.avg_duration_seconds:.1f}초",
                    priority="medium",
                    auto_apply=False
                ))

            elif m.recommended_interval and m.recommended_interval > 0:
                if m.avg_duration_seconds < 60 and success_rate >= 95:
                    recommendations.append(ScheduleRecommendation(
                        job_name=name,
                        current_schedule="Unknown",
                        recommended_schedule=f"간격 {m.recommended_interval}분으로 단축 가능",
                        reason=f"성공률 {success_rate:.1f}%, 평균 {m.avg_duration_seconds:.1f}초로 매우 빠름",
                        priority="low",
                        auto_apply=True
                    ))

        return recommendations

    def get_dashboard_data(self) -> Dict[str, Any]:
        """대시보드용 데이터 반환"""
        total_jobs = len(self.metrics)
        total_runs = sum(m.total_runs for m in self.metrics.values())
        total_success = sum(m.success_count for m in self.metrics.values())

        health_counts = {
            "healthy": 0,
            "warning": 0,
            "critical": 0,
            "unknown": 0
        }

        job_summaries = []
        for name, m in self.metrics.items():
            health = self.get_job_health(name)
            health_counts[health.value] += 1

            success_rate = (m.success_count / m.total_runs * 100) if m.total_runs > 0 else 0

            job_summaries.append({
                "name": name,
                "health": health.value,
                "success_rate": round(success_rate, 1),
                "total_runs": m.total_runs,
                "avg_duration": round(m.avg_duration_seconds, 1),
                "last_run": m.last_run,
                "last_status": m.last_status
            })

        # 성공률 순으로 정렬 (낮은 것부터)
        job_summaries.sort(key=lambda x: x["success_rate"])

        return {
            "summary": {
                "total_jobs": total_jobs,
                "total_runs": total_runs,
                "overall_success_rate": round(total_success / total_runs * 100, 1) if total_runs > 0 else 0,
                "health_counts": health_counts
            },
            "jobs": job_summaries,
            "recommendations": [asdict(r) for r in self.get_recommendations()],
            "last_updated": datetime.now().isoformat()
        }

    def analyze_peak_hours(self) -> Dict[str, Any]:
        """
        피크 시간대 분석

        DB의 schedule_history를 분석하여 최적의 실행 시간대 파악
        """
        try:
            from db.database import DatabaseManager
            db = DatabaseManager()

            # 시간대별 실행 통계
            db.cursor.execute('''
                SELECT
                    strftime('%H', executed_at) as hour,
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success,
                    AVG(duration_seconds) as avg_duration
                FROM schedule_history
                WHERE executed_at >= date('now', '-7 days')
                GROUP BY hour
                ORDER BY hour
            ''')
            rows = db.cursor.fetchall()

            hourly_stats = {}
            for row in rows:
                hour, total, success, avg_duration = row
                if hour:
                    hourly_stats[hour] = {
                        "total": total,
                        "success": success or 0,
                        "success_rate": round((success or 0) / total * 100, 1) if total > 0 else 0,
                        "avg_duration": round(avg_duration or 0, 1)
                    }

            # 최적/비최적 시간대 식별
            best_hours = []
            worst_hours = []

            for hour, stats in hourly_stats.items():
                if stats["success_rate"] >= 90 and stats["total"] >= 3:
                    best_hours.append(hour)
                elif stats["success_rate"] < 70 and stats["total"] >= 3:
                    worst_hours.append(hour)

            return {
                "hourly_stats": hourly_stats,
                "best_hours": sorted(best_hours),
                "worst_hours": sorted(worst_hours),
                "analysis_period": "last_7_days"
            }

        except Exception as e:
            logger.error(f"Peak hours analysis failed: {e}")
            return {"error": str(e)}

    def get_health_report(self) -> str:
        """건강도 보고서 텍스트 생성"""
        data = self.get_dashboard_data()
        summary = data["summary"]
        recommendations = data["recommendations"]

        lines = [
            "═" * 50,
            "📊 스케줄러 건강도 보고서",
            "═" * 50,
            "",
            f"전체 작업 수: {summary['total_jobs']}",
            f"총 실행 횟수: {summary['total_runs']}",
            f"전체 성공률: {summary['overall_success_rate']}%",
            "",
            "상태별 작업 수:",
            f"  ✅ Healthy: {summary['health_counts']['healthy']}",
            f"  ⚠️ Warning: {summary['health_counts']['warning']}",
            f"  🔴 Critical: {summary['health_counts']['critical']}",
            f"  ❓ Unknown: {summary['health_counts']['unknown']}",
        ]

        if recommendations:
            lines.extend([
                "",
                "─" * 50,
                "💡 권장 조치사항:",
                ""
            ])

            for r in recommendations:
                priority_icon = {"high": "🔴", "medium": "🟡", "low": "🔵"}[r["priority"]]
                lines.extend([
                    f"{priority_icon} {r['job_name']}",
                    f"   → {r['recommended_schedule']}",
                    f"   이유: {r['reason']}",
                    ""
                ])

        lines.append("═" * 50)
        return "\n".join(lines)


# 싱글톤 인스턴스
_adaptive_scheduler = None


def get_adaptive_scheduler() -> AdaptiveScheduler:
    """AdaptiveScheduler 싱글톤 인스턴스 반환"""
    global _adaptive_scheduler
    if _adaptive_scheduler is None:
        _adaptive_scheduler = AdaptiveScheduler()
    return _adaptive_scheduler


# =============================================================================
# [Phase 4-1-C] 메트릭 기반 스케줄 자동 조정
# =============================================================================

class AdaptiveSchedulerExtended(AdaptiveScheduler):
    """
    [Phase 4-1-C] 확장된 적응형 스케줄러

    권장사항 중 auto_apply=True인 항목을 자동으로 적용
    """

    def apply_auto_adjustments(self) -> Dict[str, Any]:
        """
        권장사항 중 auto_apply=True인 항목 자동 적용

        Returns:
            {
                "applied": [적용된 권장사항 목록],
                "skipped": [건너뛴 권장사항 목록],
                "errors": [오류 목록]
            }
        """
        recommendations = self.get_recommendations()
        result = {
            "applied": [],
            "skipped": [],
            "errors": [],
            "timestamp": datetime.now().isoformat()
        }

        for rec in recommendations:
            try:
                if rec.auto_apply:
                    # 스케줄 설정 업데이트
                    success = self._update_schedule_config(
                        rec.job_name,
                        rec.recommended_interval
                    )

                    if success:
                        result["applied"].append({
                            "job_name": rec.job_name,
                            "current": rec.current_schedule,
                            "new": rec.recommended_schedule,
                            "reason": rec.reason
                        })
                        logger.info(f"Auto-applied: {rec.job_name} → {rec.recommended_schedule}")
                    else:
                        result["skipped"].append({
                            "job_name": rec.job_name,
                            "reason": "Config update failed"
                        })
                else:
                    result["skipped"].append({
                        "job_name": rec.job_name,
                        "reason": "auto_apply=False"
                    })

            except Exception as e:
                result["errors"].append({
                    "job_name": rec.job_name,
                    "error": str(e)
                })
                logger.error(f"Failed to apply adjustment for {rec.job_name}: {e}")

        # 결과 저장
        self._save_adjustment_history(result)

        return result

    def _update_schedule_config(self, job_name: str, recommended_interval: Optional[int]) -> bool:
        """
        스케줄 설정 동적 업데이트

        Args:
            job_name: 작업 이름
            recommended_interval: 권장 간격 (분)

        Returns:
            성공 여부
        """
        if recommended_interval is None or recommended_interval <= 0:
            return False

        try:
            # schedule.json 로드
            if os.path.exists(self.schedule_config):
                with open(self.schedule_config, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            else:
                config = {"jobs": {}}

            # 작업 설정 업데이트
            if "jobs" not in config:
                config["jobs"] = {}

            # 스크래퍼 이름에서 .py 제거
            job_key = job_name.replace('.py', '')

            config["jobs"][job_key] = {
                "interval_minutes": recommended_interval,
                "auto_adjusted": True,
                "adjusted_at": datetime.now().isoformat(),
                "reason": "adaptive_scheduler_auto_adjustment"
            }

            # 설정 저장
            os.makedirs(os.path.dirname(self.schedule_config), exist_ok=True)
            with open(self.schedule_config, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            return True

        except Exception as e:
            logger.error(f"Failed to update schedule config: {e}")
            return False

    def _save_adjustment_history(self, result: Dict[str, Any]):
        """조정 히스토리 저장"""
        try:
            history_file = os.path.join(self.root_dir, 'db', 'schedule_adjustments.json')

            history = []
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)

            history.append(result)

            # 최근 100개만 유지
            history = history[-100:]

            os.makedirs(os.path.dirname(history_file), exist_ok=True)
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to save adjustment history: {e}")

    def get_adjustment_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """조정 히스토리 조회"""
        try:
            history_file = os.path.join(self.root_dir, 'db', 'schedule_adjustments.json')

            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    return history[-limit:]

            return []

        except Exception as e:
            logger.error(f"Failed to load adjustment history: {e}")
            return []

    def get_extended_dashboard_data(self) -> Dict[str, Any]:
        """확장된 대시보드 데이터"""
        base_data = self.get_dashboard_data()

        # 추가 데이터
        base_data["adjustment_history"] = self.get_adjustment_history(5)
        base_data["auto_adjustable_count"] = sum(
            1 for r in self.get_recommendations() if r.auto_apply
        )
        base_data["peak_hours"] = self.analyze_peak_hours()

        return base_data


def get_adaptive_scheduler_extended() -> AdaptiveSchedulerExtended:
    """확장된 AdaptiveScheduler 인스턴스 반환"""
    return AdaptiveSchedulerExtended()
