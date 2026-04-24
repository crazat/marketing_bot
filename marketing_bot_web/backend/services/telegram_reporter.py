"""
텔레그램 차트 보고서 자동 발송
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V3-1] 원장님이 폰에서 30초 내에 파악 가능한 주간 보고서

3계층 구조:
1. 차트 이미지 (matplotlib → PNG → Telegram sendPhoto)
2. AI 내러티브 요약 (Gemini → 한국어 200자 이내)
3. 대시보드 딥링크 (선택적)

핵심 알림 임계값:
- 순위 5위+ 하락 → 즉시 CRITICAL
- TOP3 진입 → 즉시 축하
- 경쟁사 리뷰 20건+/일 → 즉시
- 나머지 → 주간 다이제스트
"""

import io
import os
import sys
import json
import sqlite3
import logging
import requests
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# matplotlib 백엔드 설정 (GUI 불필요)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# 한글 폰트 설정
plt.rcParams['font.family'] = 'Malgun Gothic' if sys.platform == 'win32' else 'NanumGothic'
plt.rcParams['axes.unicode_minus'] = False


class TelegramReporter:
    """텔레그램 차트 보고서 발송기"""

    def __init__(self, bot_token: str, chat_id: str, db_path: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.db_path = db_path

    @classmethod
    def from_config(cls, db_path: str) -> Optional["TelegramReporter"]:
        """config.json에서 설정 로드"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            config_path = os.path.join(project_root, "config", "config.json")

            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                tg = config.get("telegram", {})
                token = tg.get("bot_token", "")
                chat_id = tg.get("chat_id", "")

            if token and chat_id:
                return cls(token, chat_id, db_path)
            return None
        except Exception:
            return None

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 차트 생성
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def generate_weekly_rank_chart(self) -> Optional[bytes]:
        """주간 순위 추이 차트 (PNG bytes)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT keyword, date, AVG(rank) as avg_rank
                FROM rank_history
                WHERE status = 'found' AND rank > 0
                  AND date >= date('now', '-7 days')
                  AND device_type = 'mobile'
                GROUP BY keyword, date
                ORDER BY keyword, date
            """)
            rows = cursor.fetchall()
            if not rows:
                return None

            # 키워드별 데이터 그룹화
            from collections import defaultdict
            data = defaultdict(lambda: {"dates": [], "ranks": []})
            for r in rows:
                data[r["keyword"]]["dates"].append(r["date"][-5:])  # MM-DD
                data[r["keyword"]]["ranks"].append(r["avg_rank"])

            # 상위 7개 키워드만
            top_keywords = sorted(data.keys(),
                                  key=lambda k: min(data[k]["ranks"]))[:7]

            fig, ax = plt.subplots(figsize=(8, 5), dpi=150)

            for kw in top_keywords:
                d = data[kw]
                ax.plot(d["dates"], d["ranks"], marker='o', markersize=4,
                        linewidth=2, label=kw)

            ax.set_title("주간 순위 추이 (모바일)", fontsize=14, fontweight='bold', pad=10)
            ax.set_xlabel("")
            ax.set_ylabel("순위", fontsize=11)
            ax.invert_yaxis()  # 1위가 위
            ax.legend(fontsize=8, loc='upper right', ncol=2)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()

            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()

        except Exception as e:
            logger.error(f"차트 생성 실패: {e}")
            return None
        finally:
            conn.close()

    def generate_review_summary_chart(self) -> Optional[bytes]:
        """경쟁사 리뷰 현황 차트 (수평 바)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT competitor_name, COUNT(*) as cnt
                FROM competitor_reviews
                WHERE review_date >= date('now', '-30 days')
                GROUP BY competitor_name
                ORDER BY cnt DESC
                LIMIT 8
            """)
            rows = cursor.fetchall()
            if not rows:
                return None

            names = [r["competitor_name"][:12] for r in rows]
            counts = [r["cnt"] for r in rows]

            fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
            colors = ['#3B82F6'] + ['#94A3B8'] * (len(names) - 1)
            ax.barh(names[::-1], counts[::-1], color=colors[::-1])
            ax.set_title("최근 30일 리뷰 현황", fontsize=14, fontweight='bold')
            ax.set_xlabel("리뷰 수")

            for i, v in enumerate(counts[::-1]):
                ax.text(v + 0.5, i, str(v), va='center', fontsize=10)

            plt.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format='png', bbox_inches='tight')
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()

        except Exception as e:
            logger.error(f"리뷰 차트 생성 실패: {e}")
            return None
        finally:
            conn.close()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # AI 내러티브 요약
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def generate_narrative(self, metrics: Dict[str, Any]) -> str:
        """AI로 한국어 내러티브 요약 생성"""
        try:
            from services.ai_client import ai_generate

            prompt = f"""한의원 원장님에게 보내는 주간 마케팅 요약을 200자 이내로 작성해주세요.
존댓말(~습니다)을 사용하고, 핵심 숫자와 추세만 간결하게 전달하세요.

데이터:
{json.dumps(metrics, ensure_ascii=False, indent=2)}

형식: 이모지 없이, 줄바꿈으로 구분, 가장 중요한 변화를 먼저"""

            return ai_generate(prompt, temperature=0.3, max_tokens=300)

        except Exception as e:
            logger.error(f"AI 내러티브 생성 실패: {e}")
            return self._fallback_narrative(metrics)

    def _fallback_narrative(self, metrics: Dict) -> str:
        """AI 실패 시 템플릿 기반 요약"""
        parts = []
        if "rank_changes" in metrics:
            up = sum(1 for r in metrics["rank_changes"] if r.get("change", 0) > 0)
            down = sum(1 for r in metrics["rank_changes"] if r.get("change", 0) < 0)
            parts.append(f"순위: {up}개 상승, {down}개 하락")
        if "new_reviews" in metrics:
            parts.append(f"새 리뷰: {metrics['new_reviews']}건")
        if "new_leads" in metrics:
            parts.append(f"새 리드: {metrics['new_leads']}건")
        return "\n".join(parts) if parts else "이번 주 데이터를 요약할 수 없습니다."

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 텔레그램 전송
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def send_photo(self, image_bytes: bytes, caption: str = "") -> bool:
        """텔레그램으로 차트 이미지 전송"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"

        files = {"photo": ("chart.png", image_bytes, "image/png")}
        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption[:1024]  # 캡션 제한

        try:
            resp = requests.post(url, data=data, files=files, timeout=15)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"차트 전송 실패: {e}")
            return False

    def send_text(self, text: str) -> bool:
        """텔레그램 텍스트 메시지 전송"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        try:
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text[:4096],
            }, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"메시지 전송 실패: {e}")
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 주간 보고서 메인
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def send_weekly_report(self) -> Dict[str, Any]:
        """주간 보고서 생성 및 발송"""
        results = {"charts_sent": 0, "narrative_sent": False}

        # 1. 순위 차트
        rank_chart = self.generate_weekly_rank_chart()
        if rank_chart:
            if self.send_photo(rank_chart, "주간 순위 추이 (모바일)"):
                results["charts_sent"] += 1

        # 2. 리뷰 차트
        review_chart = self.generate_review_summary_chart()
        if review_chart:
            if self.send_photo(review_chart, "최근 30일 리뷰 현황"):
                results["charts_sent"] += 1

        # 3. AI 내러티브
        metrics = self._collect_weekly_metrics()
        narrative = await self.generate_narrative(metrics)

        header = f"[주간 마케팅 보고서] {datetime.now().strftime('%Y-%m-%d')}\n\n"
        if self.send_text(header + narrative):
            results["narrative_sent"] = True

        logger.info(f"📊 주간 보고서 발송: {results}")
        return results

    def _collect_weekly_metrics(self) -> Dict[str, Any]:
        """주간 지표 수집"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        metrics = {}

        try:
            # 순위 변동
            cursor.execute("""
                SELECT keyword,
                    (SELECT rank FROM rank_history r2
                     WHERE r2.keyword = r1.keyword AND r2.device_type='mobile'
                       AND r2.status='found' AND r2.rank > 0
                     ORDER BY r2.date DESC LIMIT 1) as current_rank,
                    (SELECT rank FROM rank_history r3
                     WHERE r3.keyword = r1.keyword AND r3.device_type='mobile'
                       AND r3.status='found' AND r3.rank > 0
                       AND r3.date <= date('now', '-7 days')
                     ORDER BY r3.date DESC LIMIT 1) as prev_rank
                FROM rank_history r1
                WHERE r1.date >= date('now', '-7 days') AND r1.device_type='mobile'
                GROUP BY r1.keyword
            """)
            rank_changes = []
            for row in cursor.fetchall():
                if row["current_rank"] and row["prev_rank"]:
                    change = row["prev_rank"] - row["current_rank"]
                    rank_changes.append({
                        "keyword": row["keyword"],
                        "current": row["current_rank"],
                        "previous": row["prev_rank"],
                        "change": change,
                    })
            metrics["rank_changes"] = rank_changes

            # 새 리뷰 수
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM competitor_reviews
                WHERE scraped_at >= datetime('now', '-7 days')
            """)
            metrics["new_reviews"] = cursor.fetchone()["cnt"]

            # 새 리드 수
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM viral_targets
                WHERE created_at >= datetime('now', '-7 days')
            """)
            metrics["new_leads"] = cursor.fetchone()["cnt"]

        except Exception as e:
            logger.error(f"지표 수집 실패: {e}")
        finally:
            conn.close()

        return metrics
