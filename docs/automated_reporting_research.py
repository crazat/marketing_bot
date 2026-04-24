"""
=============================================================================
자동 리포팅 시스템 구현 가이드 - 한의원 마케팅 봇
=============================================================================

대상: 바쁜 한의원 원장 (휴대폰으로 확인)
채널: Telegram Bot
기술: matplotlib/plotly (서버사이드 렌더링) + AI (한국어 내러티브)

이 파일은 실행 가능한 Python 코드 예제와 구현 패턴을 포함합니다.
기존 marketing_bot 프로젝트의 DB 스키마와 alert_bot.py에 통합됩니다.
"""

# =============================================================================
# 0. 의존성 및 설치
# =============================================================================
"""
pip install python-telegram-bot[job-queue]>=21.0
pip install matplotlib>=3.9
pip install plotly>=5.24
pip install kaleido>=0.2.1    # plotly 정적 이미지 내보내기
기존 requirements.txt에 plotly는 이미 있음.
추가 필요: python-telegram-bot[job-queue], kaleido
"""

import io
import os
import sys
import sqlite3
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Path setup
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'marketing_bot_web', 'backend'))

from services.ai_client import ai_generate


# =============================================================================
# 1. 주간 리포트 포맷 - 원장이 실제로 읽는 형태
# =============================================================================
"""
[설계 원칙]
- 전체 리포트를 Telegram 1화면(~4000자)에 맞춤
- 숫자보다 방향성(상승/하락/유지)을 먼저 보여줌
- 차트 이미지 1장 + 텍스트 요약 1개 = 2개 메시지로 구성
- Critical 알림만 즉시, 나머지는 주간 묶음

[핵심: 3-Layer 구조]
Layer 1: 차트 이미지 (1초 내 파악 가능한 시각 정보)
Layer 2: AI 내러티브 요약 (30초 읽기, 한국어 자연어)
Layer 3: 상세 링크 (웹 대시보드, 선택적)
"""


@dataclass
class WeeklyReportData:
    """주간 리포트 데이터 구조"""
    period_start: str
    period_end: str

    # 순위 변동
    rank_changes: List[Dict[str, Any]] = field(default_factory=list)
    # [{"keyword": "청주 한의원", "start_rank": 22, "end_rank": 18, "delta": -4}]

    # 리뷰 현황
    our_review_count: int = 0
    competitor_review_counts: Dict[str, int] = field(default_factory=dict)

    # 키워드 발굴
    new_keywords_count: int = 0
    top_new_keywords: List[str] = field(default_factory=list)

    # 바이럴 성과
    viral_targets_found: int = 0
    viral_comments_posted: int = 0

    # 리드 발굴
    new_leads_count: int = 0
    hot_leads_count: int = 0


class WeeklyReportFormatter:
    """
    주간 리포트를 Telegram 친화적 포맷으로 변환

    MarkdownV2 특수문자 이스케이프 필수:
    _ * [ ] ( ) ~ ` > # + - = | { } . !
    """

    @staticmethod
    def escape_md(text: str) -> str:
        """MarkdownV2용 특수문자 이스케이프"""
        special_chars = r'_*[]()~`>#+-=|{}.!'
        result = ''
        for char in text:
            if char in special_chars:
                result += f'\\{char}'
            else:
                result += char
        return result

    @staticmethod
    def format_rank_arrow(delta: int) -> str:
        """순위 변동을 직관적 화살표로 표시"""
        if delta < -3:
            return f"{'🔥'} {abs(delta)}계단 상승"
        elif delta < 0:
            return f"{'📈'} {abs(delta)}계단 상승"
        elif delta == 0:
            return "➖ 변동없음"
        elif delta <= 3:
            return f"{'📉'} {delta}계단 하락"
        else:
            return f"{'🚨'} {delta}계단 급락"

    def format_weekly_text(self, data: WeeklyReportData) -> str:
        """
        주간 리포트 텍스트 (Telegram 메시지용)

        목표: 휴대폰 화면 1개에 핵심 내용이 전부 보여야 함
        Telegram 메시지 최대: 4096자
        Telegram 캡션 최대: 1024자
        """
        esc = self.escape_md

        lines = []
        lines.append(f"{'📊'} *주간 마케팅 리포트*")
        lines.append(f"{esc(data.period_start)} \\~ {esc(data.period_end)}")
        lines.append("")

        # --- 순위 섹션 (가장 중요) ---
        lines.append(f"{'🏆'} *\\[순위 변동\\]*")

        if data.rank_changes:
            # 변동이 큰 순으로 정렬
            sorted_changes = sorted(data.rank_changes, key=lambda x: x['delta'])
            for rc in sorted_changes[:7]:  # 최대 7개만
                kw = esc(rc['keyword'])
                arrow = esc(self.format_rank_arrow(rc['delta']))
                lines.append(
                    f"  {kw}: {rc['end_rank']}위 \\({arrow}\\)"
                )
        else:
            lines.append("  데이터 수집 중")
        lines.append("")

        # --- 리뷰 섹션 ---
        lines.append(f"{'⭐'} *\\[리뷰 현황\\]*")
        lines.append(f"  이번주 경쟁사 리뷰: {data.our_review_count}건")
        if data.competitor_review_counts:
            top_comp = max(data.competitor_review_counts,
                          key=data.competitor_review_counts.get)
            top_count = data.competitor_review_counts[top_comp]
            lines.append(f"  가장 활발: {esc(top_comp)} \\({top_count}건\\)")
        lines.append("")

        # --- 마케팅 활동 요약 ---
        lines.append(f"{'🎯'} *\\[마케팅 활동\\]*")
        lines.append(f"  새 키워드 발굴: {data.new_keywords_count}개")
        lines.append(f"  바이럴 타겟: {data.viral_targets_found}건 발견")
        lines.append(f"  댓글 작성: {data.viral_comments_posted}건")
        lines.append(f"  잠재고객 발견: {data.new_leads_count}건")
        if data.hot_leads_count > 0:
            lines.append(f"  {'🔥'} 긴급 리드: {data.hot_leads_count}건")
        lines.append("")

        # --- AI 한줄 요약 (별도 생성) ---
        lines.append(f"{'💡'} *\\[AI 분석\\]*")
        lines.append("_아래 메시지에서 확인_")

        return "\n".join(lines)


# =============================================================================
# 2. Telegram Bot API: 차트 이미지 전송
# =============================================================================

class TelegramReportBot:
    """
    리포트 전송 전용 Telegram Bot

    기존 alert_bot.py의 TelegramBot 클래스를 확장합니다.
    이미지 전송, MarkdownV2, 메시지 그룹핑을 지원합니다.
    """

    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def send_photo_bytes(
        self,
        image_bytes: bytes,
        caption: str = "",
        filename: str = "report.png",
        parse_mode: str = "MarkdownV2"
    ) -> bool:
        """
        matplotlib/plotly로 생성한 차트 이미지를 바이트로 전송

        Args:
            image_bytes: PNG 이미지 바이트 데이터
            caption: 이미지 캡션 (최대 1024자)
            filename: 파일명
            parse_mode: "MarkdownV2" 또는 "HTML"

        Telegram sendPhoto API:
        - photo: multipart/form-data로 업로드
        - caption: 최대 1024자
        - parse_mode: MarkdownV2 | HTML
        """
        url = f"{self.base_url}/sendPhoto"

        # multipart/form-data로 이미지 업로드
        files = {
            "photo": (filename, image_bytes, "image/png")
        }
        data = {
            "chat_id": self.chat_id,
        }
        if caption:
            data["caption"] = caption[:1024]  # 캡션 1024자 제한
            data["parse_mode"] = parse_mode

        try:
            response = requests.post(url, data=data, files=files, timeout=30)
            if response.status_code == 200:
                return True
            else:
                # MarkdownV2 파싱 실패 시 plain text 재시도
                if "can't parse entities" in response.text:
                    data.pop("parse_mode", None)
                    response = requests.post(url, data=data, files=files, timeout=30)
                    return response.status_code == 200
                print(f"Telegram photo error: {response.text}")
                return False
        except Exception as e:
            print(f"Failed to send photo: {e}")
            return False

    def send_message_md2(self, text: str) -> bool:
        """MarkdownV2 메시지 전송 (plain text 폴백 포함)"""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "MarkdownV2"
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            # MarkdownV2 실패 시 plain으로 재시도
            if "can't parse entities" in response.text:
                payload.pop("parse_mode")
                # MarkdownV2 문법 제거
                clean_text = text.replace("*", "").replace("_", "").replace("\\", "")
                payload["text"] = clean_text
                retry = requests.post(url, json=payload, timeout=10)
                return retry.status_code == 200
            return False
        except Exception as e:
            print(f"Failed to send message: {e}")
            return False

    def send_report_group(
        self,
        chart_image: bytes,
        chart_caption: str,
        narrative_text: str,
        detail_link: str = ""
    ) -> bool:
        """
        리포트 묶음 전송: 차트 이미지 + AI 내러티브 + 링크

        원장이 Telegram에서 보는 순서:
        1. 차트 이미지 (썸네일로 한눈에 파악)
        2. AI가 작성한 한국어 분석 텍스트
        3. (선택) 웹 대시보드 링크
        """
        success = True

        # 1단계: 차트 이미지 + 짧은 캡션
        if chart_image:
            if not self.send_photo_bytes(chart_image, chart_caption):
                success = False

        # 2단계: AI 내러티브 텍스트
        if narrative_text:
            if not self.send_message_md2(narrative_text):
                success = False

        # 3단계: 대시보드 링크 (선택)
        if detail_link:
            esc = WeeklyReportFormatter.escape_md
            link_msg = f"{'🔗'} [상세 대시보드에서 확인]({esc(detail_link)})"
            self.send_message_md2(link_msg)

        return success


# =============================================================================
# 3. 서버사이드 차트 렌더링 (matplotlib)
# =============================================================================

class MobileChartRenderer:
    """
    Telegram 모바일 화면에 최적화된 차트 생성

    [핵심 설정값]
    - figsize: (8, 5) - 가로형 (Telegram 썸네일에 최적)
    - DPI: 200 (Retina 디스플레이 대응)
    - 폰트: 큰 사이즈 (12-16pt) - 작은 화면에서도 가독성
    - 색상: 고대비 팔레트
    - 배경: 화이트 (다크모드에서도 깔끔)
    """

    # 규림한의원 브랜드 컬러 팔레트
    BRAND_COLORS = {
        'primary': '#2563EB',     # 파란색 (우리)
        'success': '#16A34A',     # 녹색 (상승)
        'danger': '#DC2626',      # 빨간색 (하락)
        'warning': '#F59E0B',     # 노란색 (주의)
        'neutral': '#6B7280',     # 회색
        'competitor1': '#F97316',  # 주황색
        'competitor2': '#8B5CF6',  # 보라색
        'competitor3': '#EC4899',  # 분홍색
    }

    def __init__(self):
        """matplotlib 한글 폰트 설정"""
        import matplotlib
        matplotlib.use('Agg')  # 서버사이드 렌더링 (디스플레이 없음)
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm

        # 한글 폰트 설정 (Windows/WSL 환경)
        font_candidates = [
            'Malgun Gothic',           # Windows
            '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',  # Ubuntu
            'NanumGothic',
            'AppleGothic',             # macOS
        ]

        font_set = False
        for font in font_candidates:
            if os.path.exists(font):
                fm.fontManager.addfont(font)
                plt.rcParams['font.family'] = fm.FontProperties(fname=font).get_name()
                font_set = True
                break

        if not font_set:
            # 시스템에 설치된 한글 폰트 검색
            for f in fm.fontManager.ttflist:
                if 'Gothic' in f.name or 'Nanum' in f.name or 'Malgun' in f.name:
                    plt.rcParams['font.family'] = f.name
                    font_set = True
                    break

        plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지

    def render_rank_trend_chart(
        self,
        rank_data: List[Dict[str, Any]],
        title: str = "주요 키워드 순위 추이"
    ) -> bytes:
        """
        주간 순위 추이 차트 (Line Chart)

        rank_data: [
            {"keyword": "청주 한의원", "dates": ["03-18", "03-19", ...],
             "ranks": [22, 21, 20, 18, 18, 20, 19]}
        ]

        모바일 최적화:
        - Y축 반전 (1위가 위로)
        - 굵은 선 (linewidth=2.5)
        - 큰 마커 (markersize=8)
        - 큰 폰트 (14pt 제목, 11pt 라벨)
        """
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker

        fig, ax = plt.subplots(figsize=(8, 5), dpi=200)
        fig.patch.set_facecolor('white')
        ax.set_facecolor('#FAFAFA')

        colors = [
            self.BRAND_COLORS['primary'],
            self.BRAND_COLORS['competitor1'],
            self.BRAND_COLORS['competitor2'],
            self.BRAND_COLORS['success'],
            self.BRAND_COLORS['danger'],
        ]

        for i, kw_data in enumerate(rank_data[:5]):  # 최대 5개 키워드
            color = colors[i % len(colors)]
            ax.plot(
                kw_data['dates'],
                kw_data['ranks'],
                marker='o',
                markersize=8,
                linewidth=2.5,
                label=kw_data['keyword'],
                color=color,
                zorder=3
            )
            # 마지막 순위 숫자 표시
            last_rank = kw_data['ranks'][-1]
            ax.annotate(
                f"{last_rank}위",
                (kw_data['dates'][-1], last_rank),
                textcoords="offset points",
                xytext=(10, 0),
                fontsize=11,
                fontweight='bold',
                color=color
            )

        # Y축 반전 (1위가 위로)
        ax.invert_yaxis()
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_ylabel('순위', fontsize=11)
        ax.legend(
            fontsize=10, loc='upper left',
            bbox_to_anchor=(0, -0.12), ncol=3,
            frameon=False
        )
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.tick_params(axis='x', rotation=45, labelsize=9)

        plt.tight_layout()

        # bytes로 내보내기
        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def render_competitor_comparison_card(
        self,
        our_data: Dict[str, Any],
        competitor_data: List[Dict[str, Any]],
        title: str = "경쟁사 비교"
    ) -> bytes:
        """
        경쟁사 비교 카드 (수평 바 차트)

        모바일에서 수평 바 차트가 가장 가독성이 좋음:
        - 긴 텍스트 라벨 수용 가능
        - 세로 스크롤 없이 비교 가능
        - 값이 직관적으로 보임

        our_data: {"name": "규림한의원", "reviews": 45, "avg_rank": 18}
        competitor_data: [{"name": "OO한의원", "reviews": 32, "avg_rank": 12}, ...]
        """
        import matplotlib.pyplot as plt
        import numpy as np

        fig, axes = plt.subplots(1, 2, figsize=(10, 5), dpi=200)
        fig.patch.set_facecolor('white')
        fig.suptitle(title, fontsize=14, fontweight='bold', y=1.02)

        all_data = [our_data] + competitor_data[:4]  # 최대 5개
        names = [d['name'] for d in all_data]
        colors = [self.BRAND_COLORS['primary']] + \
                 [self.BRAND_COLORS['neutral']] * len(competitor_data[:4])

        # --- 좌측: 리뷰 수 비교 ---
        ax1 = axes[0]
        reviews = [d.get('reviews', 0) for d in all_data]
        bars1 = ax1.barh(names, reviews, color=colors, height=0.6)
        ax1.set_title('이번주 리뷰 수', fontsize=12, fontweight='bold')
        ax1.set_xlabel('건', fontsize=10)

        # 바 위에 값 표시
        for bar, val in zip(bars1, reviews):
            ax1.text(
                bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                str(val), va='center', fontsize=11, fontweight='bold'
            )

        # --- 우측: 평균 순위 비교 ---
        ax2 = axes[1]
        avg_ranks = [d.get('avg_rank', 50) for d in all_data]
        bars2 = ax2.barh(names, avg_ranks, color=colors, height=0.6)
        ax2.set_title('평균 순위 (낮을수록 좋음)', fontsize=12, fontweight='bold')
        ax2.set_xlabel('위', fontsize=10)
        ax2.invert_xaxis()  # 1위가 오른쪽

        for bar, val in zip(bars2, avg_ranks):
            ax2.text(
                bar.get_width() - 0.5, bar.get_y() + bar.get_height() / 2,
                f"{val:.0f}위", va='center', ha='right',
                fontsize=11, fontweight='bold', color='white'
            )

        for ax in axes:
            ax.set_facecolor('#FAFAFA')
            ax.grid(True, axis='x', alpha=0.3, linestyle='--')
            ax.tick_params(labelsize=10)

        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def render_weekly_summary_card(
        self,
        metrics: Dict[str, Tuple[int, int]],
        title: str = "이번주 성과"
    ) -> bytes:
        """
        주간 성과 요약 카드 (대시보드 스타일)

        metrics: {
            "순위 상승": (current, previous),
            "신규 키워드": (current, previous),
            "바이럴 활동": (current, previous),
            "리드 발굴": (current, previous),
        }

        카드 형태로 4개 메트릭을 2x2 그리드에 표시
        이전 주 대비 변동률 포함
        """
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches

        fig, axes = plt.subplots(2, 2, figsize=(8, 6), dpi=200)
        fig.patch.set_facecolor('white')
        fig.suptitle(title, fontsize=16, fontweight='bold', y=0.98)

        items = list(metrics.items())
        icons = ['🏆', '🔍', '📣', '🎯']  # 카드별 아이콘

        for idx, (ax, (label, (current, previous))) in enumerate(
            zip(axes.flat, items)
        ):
            ax.set_xlim(0, 10)
            ax.set_ylim(0, 10)
            ax.axis('off')

            # 카드 배경
            card = mpatches.FancyBboxPatch(
                (0.5, 0.5), 9, 9,
                boxstyle="round,pad=0.3",
                facecolor='#F8FAFC',
                edgecolor='#E2E8F0',
                linewidth=1.5
            )
            ax.add_patch(card)

            # 라벨
            ax.text(5, 8, label, ha='center', fontsize=12,
                    fontweight='bold', color='#1E293B')

            # 현재 값 (큰 숫자)
            ax.text(5, 5.5, str(current), ha='center', fontsize=28,
                    fontweight='bold', color=self.BRAND_COLORS['primary'])

            # 변동률
            if previous > 0:
                delta_pct = ((current - previous) / previous) * 100
                if delta_pct > 0:
                    delta_text = f"+{delta_pct:.0f}%"
                    delta_color = self.BRAND_COLORS['success']
                elif delta_pct < 0:
                    delta_text = f"{delta_pct:.0f}%"
                    delta_color = self.BRAND_COLORS['danger']
                else:
                    delta_text = "0%"
                    delta_color = self.BRAND_COLORS['neutral']
            else:
                delta_text = "NEW"
                delta_color = self.BRAND_COLORS['success']

            ax.text(5, 2.5, f"전주 대비 {delta_text}", ha='center',
                    fontsize=10, color=delta_color, fontweight='bold')

        plt.tight_layout(rect=[0, 0, 1, 0.95])

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def render_monthly_trend(
        self,
        monthly_data: Dict[str, List[float]],
        title: str = "월간 트렌드"
    ) -> bytes:
        """
        월간 트렌드 리포트 (4주간 추이)

        monthly_data: {
            "평균순위": [25.3, 22.1, 20.5, 18.8],
            "리뷰수": [12, 18, 22, 28],
            "키워드수": [45, 52, 61, 68],
            "리드수": [3, 7, 11, 15],
        }
        """
        import matplotlib.pyplot as plt
        import numpy as np

        weeks = ['1주차', '2주차', '3주차', '4주차']
        fig, axes = plt.subplots(2, 2, figsize=(10, 8), dpi=200)
        fig.patch.set_facecolor('white')
        fig.suptitle(title, fontsize=16, fontweight='bold', y=0.98)

        metric_configs = [
            ("평균순위", self.BRAND_COLORS['primary'], True),   # invert=True
            ("리뷰수", self.BRAND_COLORS['success'], False),
            ("키워드수", self.BRAND_COLORS['competitor2'], False),
            ("리드수", self.BRAND_COLORS['warning'], False),
        ]

        for ax, (metric_name, color, invert) in zip(axes.flat, metric_configs):
            values = monthly_data.get(metric_name, [0, 0, 0, 0])
            ax.fill_between(weeks, values, alpha=0.15, color=color)
            ax.plot(weeks, values, marker='o', markersize=8,
                    linewidth=2.5, color=color)

            # 값 라벨
            for i, v in enumerate(values):
                offset = -12 if invert else 12
                ax.annotate(
                    f"{v:.1f}" if isinstance(v, float) else str(v),
                    (weeks[i], v),
                    textcoords="offset points",
                    xytext=(0, offset),
                    ha='center', fontsize=10, fontweight='bold',
                    color=color
                )

            ax.set_title(metric_name, fontsize=13, fontweight='bold')
            if invert:
                ax.invert_yaxis()
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.set_facecolor('#FAFAFA')
            ax.tick_params(labelsize=9)

        plt.tight_layout(rect=[0, 0, 1, 0.95])

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)
        return buf.read()


# =============================================================================
# 3b. Plotly 대안 렌더러 (인터랙티브 -> 정적 변환)
# =============================================================================

class PlotlyChartRenderer:
    """
    Plotly로 차트 생성 후 정적 PNG로 내보내기 (kaleido 사용)

    matplotlib 대비 장점:
    - 더 세련된 시각화
    - 내장 테마 (plotly_white가 모바일에 적합)
    - 호버 데이터를 주석으로 표시 가능

    matplotlib 대비 단점:
    - kaleido 의존성 필요 (Chrome/Chromium)
    - 초기 렌더링이 약간 느림 (~1초)
    """

    def render_rank_heatmap(
        self,
        keywords: List[str],
        days: List[str],
        ranks: List[List[int]],
        title: str = "키워드 순위 히트맵"
    ) -> bytes:
        """
        순위 히트맵 (특히 다수 키워드 비교 시 유용)

        Plotly를 사용하면 20+ 키워드도 한눈에 비교 가능

        Returns: PNG 이미지 바이트
        """
        import plotly.graph_objects as go

        fig = go.Figure(data=go.Heatmap(
            z=ranks,
            x=days,
            y=keywords,
            colorscale=[
                [0.0, '#16A34A'],   # 1위 = 진한 녹색
                [0.2, '#4ADE80'],   # ~20위 = 연한 녹색
                [0.5, '#FCD34D'],   # ~50위 = 노란색
                [0.8, '#F97316'],   # ~80위 = 주황색
                [1.0, '#DC2626'],   # 100위 = 빨간색
            ],
            text=[[f"{r}위" if r else "-" for r in row] for row in ranks],
            texttemplate="%{text}",
            textfont={"size": 10},
            hoverongaps=False,
            colorbar=dict(title="순위"),
            reversescale=True
        ))

        fig.update_layout(
            title=dict(text=title, font=dict(size=16)),
            width=800,
            height=max(400, len(keywords) * 35),
            template="plotly_white",
            margin=dict(l=150, r=50, t=50, b=50),
        )

        # 정적 PNG로 내보내기 (kaleido)
        img_bytes = fig.to_image(format="png", scale=2)
        return img_bytes


# =============================================================================
# 4. AI 내러티브 요약 (Gemini로 한국어 자연어 생성)
# =============================================================================

class AIReportNarrator:
    """
    원시 메트릭을 한국어 자연어 리포트로 변환

    Gemini AI 사용 (기존 프로젝트의 gemini-3-flash-preview)
    """

    WEEKLY_SYSTEM_PROMPT = """당신은 한의원 마케팅 전문 분석가입니다.
아래 데이터를 바탕으로 원장님이 30초 안에 읽을 수 있는 주간 분석을 작성하세요.

[작성 규칙]
1. 반드시 한국어로 작성
2. 존댓말 사용 (원장님 대상)
3. 핵심 인사이트 3-4개를 글머리 기호로
4. 각 인사이트에 구체적 수치 포함
5. 마지막에 "이번주 핵심 액션" 1가지 권고
6. 이모지 사용 금지 (텔레그램 MarkdownV2 호환)
7. 전체 길이: 200자 이내
8. 긍정적인 변화는 강조, 부정적인 변화는 대응 방안과 함께 언급

[톤앤매너]
- "~습니다" 체 사용
- 전문적이되 이해하기 쉽게
- 숫자는 "22위에서 18위로 4계단 상승" 형태로
"""

    MONTHLY_SYSTEM_PROMPT = """당신은 한의원 마케팅 전문 컨설턴트입니다.
아래 4주간의 데이터를 바탕으로 월간 트렌드 분석을 작성하세요.

[작성 규칙]
1. 반드시 한국어로 작성
2. 존댓말 사용 (원장님 대상)
3. 전체 방향성을 먼저 한 문장으로 요약
4. 카테고리별 분석 (순위, 리뷰, 키워드, 리드)
5. 경쟁사 동향과 우리의 포지셔닝
6. 다음 달 전략 제안 2-3가지
7. 전체 길이: 400자 이내
"""

    COMPETITOR_SYSTEM_PROMPT = """당신은 경쟁 분석 전문가입니다.
아래 데이터를 바탕으로 경쟁사 대비 우리 한의원의 포지셔닝을 분석하세요.

[작성 규칙]
1. 한국어, 존댓말
2. 우리의 강점/약점 각 1-2개
3. 가장 위협적인 경쟁사 1곳 언급
4. 즉시 실행 가능한 대응 전략 1개
5. 전체 길이: 150자 이내
"""

    def __init__(self, api_key: str = None):
        """AI 클라이언트 초기화 - centralized ai_client 사용"""
        pass  # ai_client module handles initialization

    def generate_weekly_narrative(self, data: WeeklyReportData) -> str:
        """
        주간 데이터를 AI 내러티브로 변환

        Temperature: 0.3 (사실 기반, 창의성 낮춤)
        """
        # 데이터를 구조화된 텍스트로 변환
        data_text = self._format_data_for_ai(data)

        try:
            prompt = f"{self.WEEKLY_SYSTEM_PROMPT}\n\n[이번주 데이터]\n{data_text}"
            result = ai_generate(prompt, temperature=0.3, max_tokens=500)
            return result
        except Exception as e:
            # AI 실패 시 템플릿 폴백
            return self._fallback_narrative(data)

    def generate_monthly_analysis(self, monthly_data: Dict) -> str:
        """월간 트렌드 AI 분석"""
        data_text = json.dumps(monthly_data, ensure_ascii=False, indent=2)

        try:
            prompt = f"{self.MONTHLY_SYSTEM_PROMPT}\n\n[4주간 데이터]\n{data_text}"
            result = ai_generate(prompt, temperature=0.4, max_tokens=800)
            return result
        except Exception as e:
            return f"월간 분석 생성 실패: {e}"

    def generate_competitor_insight(self, comparison_data: Dict) -> str:
        """경쟁사 비교 AI 인사이트"""
        data_text = json.dumps(comparison_data, ensure_ascii=False, indent=2)

        try:
            prompt = f"{self.COMPETITOR_SYSTEM_PROMPT}\n\n[경쟁사 비교 데이터]\n{data_text}"
            result = ai_generate(prompt, temperature=0.3, max_tokens=400)
            return result
        except Exception as e:
            return f"경쟁사 분석 생성 실패: {e}"

    def _format_data_for_ai(self, data: WeeklyReportData) -> str:
        """AI 입력용으로 데이터 포맷팅"""
        lines = []
        lines.append(f"기간: {data.period_start} ~ {data.period_end}")
        lines.append("")

        lines.append("[순위 변동]")
        for rc in data.rank_changes:
            direction = "상승" if rc['delta'] < 0 else "하락" if rc['delta'] > 0 else "유지"
            lines.append(
                f"- {rc['keyword']}: {rc['start_rank']}위 -> {rc['end_rank']}위 "
                f"({abs(rc['delta'])}계단 {direction})"
            )

        lines.append(f"\n[리뷰] 경쟁사 리뷰: {data.our_review_count}건")
        for comp, count in data.competitor_review_counts.items():
            lines.append(f"- {comp}: {count}건")

        lines.append(f"\n[마케팅 활동]")
        lines.append(f"- 새 키워드: {data.new_keywords_count}개")
        lines.append(f"- 바이럴 타겟 발견: {data.viral_targets_found}건")
        lines.append(f"- 댓글 작성: {data.viral_comments_posted}건")
        lines.append(f"- 잠재고객(리드): {data.new_leads_count}건 (긴급: {data.hot_leads_count}건)")

        return "\n".join(lines)

    def _fallback_narrative(self, data: WeeklyReportData) -> str:
        """AI 실패 시 템플릿 기반 폴백"""
        # 순위 변동 요약
        improved = [rc for rc in data.rank_changes if rc['delta'] < 0]
        declined = [rc for rc in data.rank_changes if rc['delta'] > 0]

        parts = []
        if improved:
            best = min(improved, key=lambda x: x['delta'])
            parts.append(
                f"'{best['keyword']}' 키워드가 {abs(best['delta'])}계단 상승하여 "
                f"{best['end_rank']}위를 기록했습니다."
            )
        if declined:
            worst = max(declined, key=lambda x: x['delta'])
            parts.append(
                f"'{worst['keyword']}'는 {worst['delta']}계단 하락하여 "
                f"콘텐츠 보강이 필요합니다."
            )

        parts.append(
            f"이번주 {data.new_leads_count}건의 잠재고객이 발굴되었습니다."
        )

        return "\n".join(parts)


# =============================================================================
# 5. 실시간 알림 임계값 시스템
# =============================================================================

class AlertThresholds:
    """
    실행 가능한 알림 임계값 설정

    [원장의 시간을 존중하는 알림 전략]
    - CRITICAL만 즉시 전송 (하루 최대 3건)
    - WARNING은 주간 리포트에 묶어서 전송
    - INFO는 대시보드에서만 확인

    [핵심 임계값]
    """

    # --- 순위 변동 임계값 ---
    RANK_DROP_CRITICAL = 5     # 5위 이상 급락 -> 즉시 알림
    RANK_DROP_WARNING = 3      # 3위 이상 하락 -> 주간 리포트
    RANK_IMPROVE_NOTABLE = 3   # 3위 이상 상승 -> 주간 리포트
    RANK_TOP5_ENTRY = 5        # TOP5 진입 -> 즉시 축하 알림
    RANK_TOP3_ENTRY = 3        # TOP3 진입 -> 즉시 축하 알림

    # --- 리뷰 볼륨 임계값 ---
    COMPETITOR_REVIEW_SPIKE = 10      # 경쟁사 일일 리뷰 10건 이상 -> WARNING
    COMPETITOR_REVIEW_BURST = 20      # 경쟁사 일일 리뷰 20건 이상 -> CRITICAL
    NO_REVIEW_DAYS = 7                # 7일간 리뷰 없음 -> WARNING

    # --- 바이럴/리드 임계값 ---
    HOT_LEAD_THRESHOLD = 3      # 긴급 리드 3건 이상 -> 즉시 알림
    VIRAL_OPPORTUNITY_SCORE = 80  # 80점 이상 바이럴 기회 -> 알림

    # --- 경쟁사 임계값 ---
    COMPETITOR_NEW_CAMPAIGN = 5   # 경쟁사 신규 콘텐츠 5건/일 -> WARNING
    COMPETITOR_RANK_OVERTAKE = True  # 경쟁사가 우리 순위를 추월 -> CRITICAL


class SmartAlertEngine:
    """
    기존 AlertSystem과 통합되는 스마트 알림 엔진

    alert_bot.py의 AlertSystem.check_rank_changes()를
    임계값 기반으로 고도화합니다.
    """

    def __init__(self, db_path: str, thresholds: AlertThresholds = None):
        self.db_path = db_path
        self.t = thresholds or AlertThresholds()

    def check_rank_alerts(self) -> List[Dict[str, Any]]:
        """
        순위 변동 기반 스마트 알림 생성

        기존 alert_bot.py의 check_rank_changes()를 대체/보강
        """
        alerts = []
        conn = None

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 최근 2일 순위 데이터 (모바일 기준)
            cursor.execute("""
                SELECT keyword, rank, checked_at,
                       LAG(rank) OVER (PARTITION BY keyword ORDER BY checked_at) as prev_rank
                FROM rank_history
                WHERE date(checked_at) >= date('now', '-2 days')
                  AND device_type = 'mobile'
                  AND status = 'found'
                ORDER BY keyword, checked_at DESC
            """)
            rows = cursor.fetchall()

            seen_keywords = set()
            for row in rows:
                keyword, rank, checked_at, prev_rank = row

                if keyword in seen_keywords or prev_rank is None:
                    continue
                seen_keywords.add(keyword)

                delta = rank - prev_rank

                # CRITICAL: 5위 이상 급락
                if delta >= self.t.RANK_DROP_CRITICAL:
                    alerts.append({
                        "priority": "critical",
                        "type": "rank_drop",
                        "keyword": keyword,
                        "message": f"'{keyword}' {prev_rank}위 -> {rank}위 ({delta}계단 급락)",
                        "action": "경쟁사 활동 확인 및 긴급 콘텐츠 발행 필요"
                    })

                # CRITICAL: TOP3 진입
                elif rank <= self.t.RANK_TOP3_ENTRY and prev_rank > self.t.RANK_TOP3_ENTRY:
                    alerts.append({
                        "priority": "critical",
                        "type": "rank_milestone",
                        "keyword": keyword,
                        "message": f"'{keyword}' TOP3 진입 ({prev_rank}위 -> {rank}위)",
                        "action": "현재 전략 유지, 추가 콘텐츠로 포지션 강화"
                    })

                # WARNING: 3위 이상 하락
                elif delta >= self.t.RANK_DROP_WARNING:
                    alerts.append({
                        "priority": "warning",
                        "type": "rank_drop",
                        "keyword": keyword,
                        "message": f"'{keyword}' {prev_rank}위 -> {rank}위 ({delta}계단 하락)",
                        "action": "관련 키워드 콘텐츠 발행 검토"
                    })

                # INFO: TOP5 진입
                elif rank <= self.t.RANK_TOP5_ENTRY and prev_rank > self.t.RANK_TOP5_ENTRY:
                    alerts.append({
                        "priority": "info",
                        "type": "rank_milestone",
                        "keyword": keyword,
                        "message": f"'{keyword}' TOP5 진입 ({prev_rank}위 -> {rank}위)"
                    })

        except Exception as e:
            print(f"순위 알림 체크 실패: {e}")
        finally:
            if conn:
                conn.close()

        return alerts

    def check_review_volume_alerts(self) -> List[Dict[str, Any]]:
        """경쟁사 리뷰 볼륨 이상 감지"""
        alerts = []
        conn = None

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 오늘 경쟁사별 리뷰 수
            cursor.execute("""
                SELECT competitor_name, COUNT(*) as cnt
                FROM competitor_reviews
                WHERE date(scraped_at) = date('now')
                GROUP BY competitor_name
            """)
            rows = cursor.fetchall()

            for comp_name, count in rows:
                if count >= self.t.COMPETITOR_REVIEW_BURST:
                    alerts.append({
                        "priority": "critical",
                        "type": "review_burst",
                        "competitor": comp_name,
                        "message": f"'{comp_name}' 오늘 리뷰 {count}건 급증 (이벤트/캠페인 추정)",
                        "action": "경쟁사 이벤트 내용 파악 및 대응 전략 수립"
                    })
                elif count >= self.t.COMPETITOR_REVIEW_SPIKE:
                    alerts.append({
                        "priority": "warning",
                        "type": "review_spike",
                        "competitor": comp_name,
                        "message": f"'{comp_name}' 오늘 리뷰 {count}건 (평소 대비 높음)",
                        "action": "리뷰 내용 분석으로 트렌드 파악"
                    })

        except Exception as e:
            print(f"리뷰 볼륨 알림 체크 실패: {e}")
        finally:
            if conn:
                conn.close()

        return alerts


# =============================================================================
# 6. 월간 트렌드 리포트 + AI 분석
# =============================================================================

class MonthlyReportGenerator:
    """
    월간 트렌드 리포트 생성기

    매월 1일(또는 마지막 일요일) 자동 실행
    4주간의 데이터를 집계하여:
    1. 트렌드 차트 (4주 추이)
    2. AI가 작성한 월간 분석 리포트
    3. 경쟁사 비교 카드
    4. 다음 달 전략 제안
    """

    def __init__(self, db_path: str, gemini_api_key: str = None):
        self.db_path = db_path
        self.chart_renderer = MobileChartRenderer()
        self.narrator = AIReportNarrator()

    def collect_monthly_data(self) -> Dict[str, Any]:
        """4주간 데이터 집계"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            data = {"weeks": []}

            for week_offset in range(4, 0, -1):
                week_start = (datetime.now() - timedelta(weeks=week_offset)).strftime('%Y-%m-%d')
                week_end = (datetime.now() - timedelta(weeks=week_offset - 1)).strftime('%Y-%m-%d')

                # 주간 평균 순위
                cursor.execute("""
                    SELECT AVG(rank) FROM rank_history
                    WHERE date(checked_at) BETWEEN ? AND ?
                      AND status = 'found' AND device_type = 'mobile'
                """, (week_start, week_end))
                avg_rank = cursor.fetchone()[0] or 0

                # 주간 리뷰 수
                cursor.execute("""
                    SELECT COUNT(*) FROM competitor_reviews
                    WHERE date(scraped_at) BETWEEN ? AND ?
                """, (week_start, week_end))
                review_count = cursor.fetchone()[0] or 0

                # 주간 신규 키워드
                cursor.execute("""
                    SELECT COUNT(*) FROM keyword_insights
                    WHERE date(created_at) BETWEEN ? AND ?
                """, (week_start, week_end))
                keyword_count = cursor.fetchone()[0] or 0

                # 주간 리드
                cursor.execute("""
                    SELECT COUNT(*) FROM mentions
                    WHERE date(created_at) BETWEEN ? AND ?
                      AND status = 'New'
                """, (week_start, week_end))
                lead_count = cursor.fetchone()[0] or 0

                data["weeks"].append({
                    "period": f"{week_start} ~ {week_end}",
                    "avg_rank": round(avg_rank, 1),
                    "review_count": review_count,
                    "keyword_count": keyword_count,
                    "lead_count": lead_count,
                })

            return data

        except Exception as e:
            print(f"월간 데이터 수집 실패: {e}")
            return {"weeks": []}
        finally:
            if conn:
                conn.close()

    def generate_monthly_report(self, bot: TelegramReportBot):
        """
        월간 리포트 전체 파이프라인

        전송 순서:
        1. 월간 트렌드 차트 이미지
        2. AI 월간 분석 텍스트
        3. 경쟁사 비교 카드 이미지
        4. AI 경쟁사 인사이트
        """
        data = self.collect_monthly_data()

        if not data["weeks"]:
            bot.send_message_md2("월간 데이터가 부족합니다\\.")
            return

        # 1. 트렌드 차트 생성
        monthly_chart_data = {
            "평균순위": [w["avg_rank"] for w in data["weeks"]],
            "리뷰수": [w["review_count"] for w in data["weeks"]],
            "키워드수": [w["keyword_count"] for w in data["weeks"]],
            "리드수": [w["lead_count"] for w in data["weeks"]],
        }

        trend_chart = self.chart_renderer.render_monthly_trend(
            monthly_chart_data,
            title=f"월간 트렌드 ({data['weeks'][0]['period'].split('~')[0].strip()} ~ "
                  f"{data['weeks'][-1]['period'].split('~')[1].strip()})"
        )

        # 2. AI 분석
        ai_analysis = self.narrator.generate_monthly_analysis(data)

        # 3. 전송
        esc = WeeklyReportFormatter.escape_md
        bot.send_report_group(
            chart_image=trend_chart,
            chart_caption="월간 트렌드 리포트",
            narrative_text=esc(ai_analysis),
        )


# =============================================================================
# 7. 경쟁사 비교 카드 (모바일용)
# =============================================================================

class CompetitorCardGenerator:
    """
    모바일 친화적 경쟁사 비교 카드

    [디자인 원칙]
    1. 한 화면에 우리 vs 경쟁사 TOP3 비교
    2. 색상으로 우리(파란색) vs 경쟁사(회색) 구분
    3. 핵심 지표 3개만: 순위, 리뷰수, 활동량
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.chart_renderer = MobileChartRenderer()

    def collect_comparison_data(self) -> Tuple[Dict, List[Dict]]:
        """우리 vs 경쟁사 비교 데이터 수집"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 우리 평균 순위 (최근 7일)
            cursor.execute("""
                SELECT AVG(rank) FROM rank_history
                WHERE date(checked_at) >= date('now', '-7 days')
                  AND status = 'found' AND device_type = 'mobile'
            """)
            our_avg_rank = cursor.fetchone()[0] or 0

            our_data = {
                "name": "규림한의원",
                "avg_rank": round(our_avg_rank, 1),
                "reviews": 0,  # 우리 리뷰는 별도 수집
            }

            # 경쟁사 데이터
            cursor.execute("""
                SELECT competitor_name,
                       COUNT(*) as review_count
                FROM competitor_reviews
                WHERE date(scraped_at) >= date('now', '-7 days')
                GROUP BY competitor_name
                ORDER BY review_count DESC
                LIMIT 4
            """)
            competitors = []
            for name, review_count in cursor.fetchall():
                # 경쟁사 평균 순위 (competitor_rankings 테이블)
                cursor.execute("""
                    SELECT AVG(rank) FROM competitor_rankings
                    WHERE competitor_name = ?
                      AND date(scanned_date) >= date('now', '-7 days')
                """, (name,))
                comp_rank = cursor.fetchone()
                avg_rank = comp_rank[0] if comp_rank and comp_rank[0] else 50

                competitors.append({
                    "name": name,
                    "reviews": review_count,
                    "avg_rank": round(avg_rank, 1),
                })

            return our_data, competitors

        except Exception as e:
            print(f"경쟁사 비교 데이터 수집 실패: {e}")
            return {"name": "규림한의원", "avg_rank": 0, "reviews": 0}, []
        finally:
            if conn:
                conn.close()

    def generate_comparison_card(self) -> bytes:
        """경쟁사 비교 차트 이미지 생성"""
        our_data, competitors = self.collect_comparison_data()
        return self.chart_renderer.render_competitor_comparison_card(
            our_data=our_data,
            competitor_data=competitors,
            title="이번주 경쟁사 비교"
        )


# =============================================================================
# 8. 스케줄러 통합 (background_scheduler.py 확장)
# =============================================================================

"""
기존 background_scheduler.py의 SchedulerService에 통합하는 패턴:

```python
# background_scheduler.py에 추가
from automated_reporting import WeeklyReportPipeline, MonthlyReportGenerator

class SchedulerService:
    def __init__(self):
        ...
        self.weekly_reporter = WeeklyReportPipeline(
            db_path=self.config.db_path,
            telegram_token=secrets.get("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=secrets.get("TELEGRAM_CHAT_ID", ""),
        )
        self.monthly_reporter = MonthlyReportGenerator(
            db_path=self.config.db_path,
        )

    def start(self):
        ...
        # 매주 월요일 오전 9시 주간 리포트
        schedule.every().monday.at("09:00").do(self.job_weekly_report)

        # 매월 1일 오전 10시 월간 리포트
        schedule.every().day.at("10:00").do(self.job_monthly_report_if_first)

    def job_weekly_report(self):
        logger.info("Generating weekly report...")
        self.weekly_reporter.run()

    def job_monthly_report_if_first(self):
        if datetime.now().day == 1:
            logger.info("Generating monthly report...")
            self.monthly_reporter.generate_monthly_report(self.weekly_reporter.bot)
```

[python-telegram-bot JobQueue 대안]

python-telegram-bot의 JobQueue를 사용하면 더 정교한 스케줄링이 가능합니다:

```python
from telegram.ext import Application
import datetime

application = Application.builder().token("TOKEN").build()
job_queue = application.job_queue

# 매주 월요일 09:00 KST
job_queue.run_daily(
    send_weekly_report,
    time=datetime.time(hour=9, minute=0, tzinfo=KST),
    days=(0,),  # Monday=0
)

# 매월 1일 10:00 KST
job_queue.run_monthly(
    send_monthly_report,
    when=datetime.time(hour=10, minute=0, tzinfo=KST),
    day=1,
)
```

그러나 기존 프로젝트가 `schedule` 라이브러리를 사용하므로,
일관성을 위해 schedule 기반 통합을 권장합니다.
"""


# =============================================================================
# 9. 전체 파이프라인 (Weekly Report)
# =============================================================================

class WeeklyReportPipeline:
    """
    주간 리포트 전체 파이프라인

    실행 순서:
    1. DB에서 주간 데이터 수집
    2. 차트 이미지 렌더링 (순위 추이 + 경쟁사 비교)
    3. AI 내러티브 생성
    4. Telegram으로 전송

    기존 통합 포인트:
    - alert_bot.py의 TelegramBot 클래스와 토큰/chat_id 공유
    - background_scheduler.py에서 job으로 등록
    - db/marketing_data.db의 rank_history, competitor_reviews 등 사용
    """

    def __init__(
        self,
        db_path: str,
        gemini_api_key: str = None,
        telegram_token: str = "",
        telegram_chat_id: str = "",
    ):
        self.db_path = db_path
        self.bot = TelegramReportBot(telegram_token, telegram_chat_id)
        self.chart_renderer = MobileChartRenderer()
        self.narrator = AIReportNarrator()
        self.formatter = WeeklyReportFormatter()

    def collect_weekly_data(self) -> WeeklyReportData:
        """DB에서 주간 데이터 수집"""
        now = datetime.now()
        week_ago = now - timedelta(days=7)

        data = WeeklyReportData(
            period_start=week_ago.strftime("%m/%d"),
            period_end=now.strftime("%m/%d"),
        )

        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # --- 순위 변동 ---
            cursor.execute("""
                WITH recent AS (
                    SELECT keyword, rank, checked_at,
                           ROW_NUMBER() OVER (
                               PARTITION BY keyword
                               ORDER BY checked_at DESC
                           ) as rn
                    FROM rank_history
                    WHERE date(checked_at) >= date('now', '-7 days')
                      AND status = 'found'
                      AND device_type = 'mobile'
                ),
                current_ranks AS (
                    SELECT keyword, rank as current_rank FROM recent WHERE rn = 1
                ),
                week_ago_ranks AS (
                    SELECT keyword, rank as week_ago_rank FROM recent
                    WHERE rn = (SELECT MAX(rn) FROM recent r2 WHERE r2.keyword = recent.keyword)
                )
                SELECT c.keyword, w.week_ago_rank, c.current_rank,
                       c.current_rank - w.week_ago_rank as delta
                FROM current_ranks c
                JOIN week_ago_ranks w ON c.keyword = w.keyword
                ORDER BY ABS(c.current_rank - w.week_ago_rank) DESC
            """)

            for row in cursor.fetchall():
                data.rank_changes.append({
                    "keyword": row["keyword"],
                    "start_rank": row["week_ago_rank"],
                    "end_rank": row["current_rank"],
                    "delta": row["delta"],
                })

            # --- 리뷰 현황 ---
            cursor.execute("""
                SELECT competitor_name, COUNT(*) as cnt
                FROM competitor_reviews
                WHERE date(scraped_at) >= date('now', '-7 days')
                GROUP BY competitor_name
            """)
            for row in cursor.fetchall():
                data.competitor_review_counts[row["competitor_name"]] = row["cnt"]
            data.our_review_count = sum(data.competitor_review_counts.values())

            # --- 키워드 발굴 ---
            cursor.execute("""
                SELECT COUNT(*) FROM keyword_insights
                WHERE date(created_at) >= date('now', '-7 days')
            """)
            data.new_keywords_count = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT keyword FROM keyword_insights
                WHERE date(created_at) >= date('now', '-7 days')
                  AND grade IN ('S', 'A')
                ORDER BY created_at DESC LIMIT 5
            """)
            data.top_new_keywords = [r[0] for r in cursor.fetchall()]

            # --- 바이럴 ---
            cursor.execute("""
                SELECT COUNT(*) FROM viral_targets
                WHERE date(created_at) >= date('now', '-7 days')
            """)
            data.viral_targets_found = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM posted_comments
                WHERE date(posted_at) >= date('now', '-7 days')
            """)
            data.viral_comments_posted = cursor.fetchone()[0] or 0

            # --- 리드 ---
            cursor.execute("""
                SELECT COUNT(*) FROM mentions
                WHERE date(created_at) >= date('now', '-7 days')
                  AND status = 'New'
            """)
            data.new_leads_count = cursor.fetchone()[0] or 0

            cursor.execute("""
                SELECT COUNT(*) FROM mentions
                WHERE date(created_at) >= date('now', '-7 days')
                  AND (title LIKE '%추천%' OR title LIKE '%급해요%'
                       OR title LIKE '%어디가%')
            """)
            data.hot_leads_count = cursor.fetchone()[0] or 0

        except Exception as e:
            print(f"주간 데이터 수집 실패: {e}")
        finally:
            if conn:
                conn.close()

        return data

    def _collect_rank_trend_for_chart(self) -> List[Dict[str, Any]]:
        """차트용 순위 추이 데이터 수집 (7일간)"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT DISTINCT keyword FROM rank_history
                WHERE date(checked_at) >= date('now', '-7 days')
                  AND status = 'found' AND device_type = 'mobile'
            """)
            keywords = [r[0] for r in cursor.fetchall()]

            chart_data = []
            for kw in keywords[:5]:  # 최대 5개 키워드
                cursor.execute("""
                    SELECT strftime('%m-%d', checked_at) as day, rank
                    FROM rank_history
                    WHERE keyword = ?
                      AND date(checked_at) >= date('now', '-7 days')
                      AND status = 'found' AND device_type = 'mobile'
                    ORDER BY checked_at
                """, (kw,))
                rows = cursor.fetchall()
                if rows:
                    chart_data.append({
                        "keyword": kw,
                        "dates": [r[0] for r in rows],
                        "ranks": [r[1] for r in rows],
                    })

            return chart_data

        except Exception as e:
            print(f"차트 데이터 수집 실패: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def run(self):
        """전체 주간 리포트 파이프라인 실행"""
        print(f"[{datetime.now()}] Starting weekly report generation...")

        # 1. 데이터 수집
        data = self.collect_weekly_data()
        chart_data = self._collect_rank_trend_for_chart()

        # 2. 차트 이미지 생성
        rank_chart = None
        if chart_data:
            rank_chart = self.chart_renderer.render_rank_trend_chart(
                chart_data,
                title=f"순위 추이 ({data.period_start} ~ {data.period_end})"
            )

        # 3. 경쟁사 비교 카드
        comp_gen = CompetitorCardGenerator(self.db_path)
        comp_chart = comp_gen.generate_comparison_card()

        # 4. AI 내러티브
        narrative = self.narrator.generate_weekly_narrative(data)

        # 5. 텍스트 요약
        text_summary = self.formatter.format_weekly_text(data)

        # 6. Telegram 전송 (순서가 중요)
        esc = WeeklyReportFormatter.escape_md

        # 6a. 순위 추이 차트 + 텍스트 요약
        if rank_chart:
            self.bot.send_photo_bytes(
                rank_chart,
                caption=f"주간 순위 추이 ({data.period_start} ~ {data.period_end})"
            )

        # 6b. 텍스트 요약
        self.bot.send_message_md2(text_summary)

        # 6c. AI 분석
        ai_header = f"{'💡'} *AI 주간 분석*\n\n"
        self.bot.send_message_md2(ai_header + esc(narrative))

        # 6d. 경쟁사 비교 카드
        if comp_chart:
            self.bot.send_photo_bytes(
                comp_chart,
                caption="이번주 경쟁사 비교"
            )

        print(f"[{datetime.now()}] Weekly report sent successfully!")


# =============================================================================
# 10. 실행 예제 및 테스트
# =============================================================================

def example_usage():
    """사용 예제 (테스트용)"""

    # --- 환경 변수에서 설정 로드 ---
    from dotenv import load_dotenv
    load_dotenv()

    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "marketing_data.db")

    # --- 주간 리포트 실행 ---
    pipeline = WeeklyReportPipeline(
        db_path=DB_PATH,
        telegram_token=TELEGRAM_TOKEN,
        telegram_chat_id=TELEGRAM_CHAT_ID,
    )
    pipeline.run()


def test_chart_rendering():
    """차트 렌더링 테스트 (Telegram 없이 로컬 파일로 저장)"""
    renderer = MobileChartRenderer()

    # 테스트 데이터
    rank_data = [
        {
            "keyword": "청주 한의원",
            "dates": ["03-18", "03-19", "03-20", "03-21", "03-22", "03-23", "03-24"],
            "ranks": [22, 21, 20, 18, 18, 20, 19]
        },
        {
            "keyword": "청주 다이어트 한약",
            "dates": ["03-18", "03-19", "03-20", "03-21", "03-22", "03-23", "03-24"],
            "ranks": [11, 12, 10, 9, 8, 8, 7]
        },
        {
            "keyword": "청주 교통사고 한의원",
            "dates": ["03-18", "03-19", "03-20", "03-21", "03-22", "03-23", "03-24"],
            "ranks": [25, 24, 23, 22, 23, 21, 20]
        },
    ]

    # 순위 추이 차트
    chart_bytes = renderer.render_rank_trend_chart(rank_data)
    output_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, "test_rank_chart.png"), "wb") as f:
        f.write(chart_bytes)
    print(f"Chart saved to {output_dir}/test_rank_chart.png")

    # 경쟁사 비교 카드
    comp_chart = renderer.render_competitor_comparison_card(
        our_data={"name": "규림한의원", "reviews": 28, "avg_rank": 18},
        competitor_data=[
            {"name": "OO한의원", "reviews": 45, "avg_rank": 8},
            {"name": "XX한방병원", "reviews": 32, "avg_rank": 12},
            {"name": "YY한의원", "reviews": 15, "avg_rank": 25},
        ]
    )

    with open(os.path.join(output_dir, "test_competitor_card.png"), "wb") as f:
        f.write(comp_chart)
    print(f"Competitor card saved to {output_dir}/test_competitor_card.png")

    # 주간 성과 카드
    summary_chart = renderer.render_weekly_summary_card({
        "순위 상승": (4, 2),
        "신규 키워드": (15, 12),
        "바이럴 활동": (23, 18),
        "리드 발굴": (8, 5),
    })

    with open(os.path.join(output_dir, "test_summary_card.png"), "wb") as f:
        f.write(summary_chart)
    print(f"Summary card saved to {output_dir}/test_summary_card.png")

    # 월간 트렌드
    monthly_chart = renderer.render_monthly_trend({
        "평균순위": [25.3, 22.1, 20.5, 18.8],
        "리뷰수": [12, 18, 22, 28],
        "키워드수": [45, 52, 61, 68],
        "리드수": [3, 7, 11, 15],
    })

    with open(os.path.join(output_dir, "test_monthly_trend.png"), "wb") as f:
        f.write(monthly_chart)
    print(f"Monthly trend saved to {output_dir}/test_monthly_trend.png")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test-charts":
        test_chart_rendering()
    elif len(sys.argv) > 1 and sys.argv[1] == "--run":
        example_usage()
    else:
        print("Usage:")
        print("  python automated_reporting_research.py --test-charts  # 차트 테스트")
        print("  python automated_reporting_research.py --run          # 전체 파이프라인")
