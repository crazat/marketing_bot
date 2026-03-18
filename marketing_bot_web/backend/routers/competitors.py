"""
Competitor Analysis API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

경쟁사 분석 및 약점 공략
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from typing import Dict, Any, List, Optional, Literal
import sys
import os
from pathlib import Path
import sqlite3
import json

# 상위 디렉토리를 path에 추가 (marketing_bot 루트)
# routers -> backend -> marketing_bot_web -> marketing_bot
parent_dir = str(Path(__file__).parent.parent.parent.parent)  # 프로젝트 루트
backend_dir = str(Path(__file__).parent.parent)  # backend 디렉토리
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from schemas.response import success_response, error_response

router = APIRouter()

class CompetitorAdd(BaseModel):
    name: str
    place_id: Optional[str] = None
    category: str = "한의원"
    priority: Literal["Critical", "High", "Medium", "Low"] = "Medium"

    @field_validator('name')
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('경쟁사 이름은 필수입니다')
        if len(v.strip()) < 2:
            raise ValueError('경쟁사 이름은 최소 2자 이상이어야 합니다')
        return v.strip()

    @field_validator('category')
    @classmethod
    def category_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('카테고리는 필수입니다')
        return v.strip()

@router.get("/list")
@handle_exceptions
async def get_competitors() -> List[Dict[str, Any]]:
    """
    경쟁사 목록 조회

    Returns:
        경쟁사 목록
    """
    try:
        # config/targets.json 파일 읽기
        targets_path = os.path.join(parent_dir, 'config', 'targets.json')
        print(f"[Competitors API] Loading from: {targets_path}")

        if os.path.exists(targets_path):
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                competitors = data.get('targets', [])

                # ID 추가 (인덱스 기반)
                for idx, comp in enumerate(competitors):
                    comp['id'] = idx + 1

                print(f"[Competitors API] Loaded {len(competitors)} competitors")
                return competitors
        else:
            print(f"[Competitors API] File not found: {targets_path}")
            logger.warning(f"경쟁사 타겟 파일을 찾을 수 없습니다: {targets_path}")
            return []

    except Exception as e:
        print(f"[Competitors API] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add")
async def add_competitor(competitor: CompetitorAdd) -> Dict[str, str]:
    """
    경쟁사 추가

    Args:
        competitor: 경쟁사 정보

    Returns:
        상태 메시지
    """
    try:
        # config/targets.json 파일 읽기/쓰기
        targets_path = os.path.join(parent_dir, 'config', 'targets.json')

        # 기존 데이터 읽기
        if os.path.exists(targets_path):
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {'targets': []}

        # 새 경쟁사 추가 (targets.json 구조에 맞게)
        new_competitor = {
            'name': competitor.name,
            'category': competitor.category,
            'priority': competitor.priority,
            'monitor_urls': {},
            'keywords': []
        }

        # place_id가 URL이면 monitor_urls에 추가
        if competitor.place_id:
            if 'place.naver.com' in competitor.place_id or 'naver' in competitor.place_id.lower():
                new_competitor['monitor_urls']['naver_place'] = competitor.place_id
            elif 'instagram' in competitor.place_id.lower():
                new_competitor['monitor_urls']['instagram'] = competitor.place_id
            else:
                new_competitor['monitor_urls']['other'] = competitor.place_id

        data['targets'].append(new_competitor)

        # 파일 저장
        with open(targets_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {
            'status': 'success',
            'message': f'경쟁사 "{competitor.name}" 추가 완료'
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CompetitorUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    keywords: Optional[List[str]] = None


@router.put("/{competitor_id}")
async def update_competitor(competitor_id: int, update: CompetitorUpdate) -> Dict[str, str]:
    """
    경쟁사 정보 업데이트

    Args:
        competitor_id: 경쟁사 ID (1-based index)
        update: 업데이트할 정보

    Returns:
        상태 메시지
    """
    try:
        targets_path = os.path.join(parent_dir, 'config', 'targets.json')

        if not os.path.exists(targets_path):
            raise HTTPException(status_code=404, detail="설정 파일이 없습니다")

        with open(targets_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        targets = data.get('targets', [])
        idx = competitor_id - 1  # 1-based to 0-based

        if idx < 0 or idx >= len(targets):
            raise HTTPException(status_code=404, detail=f"경쟁사 ID {competitor_id}을(를) 찾을 수 없습니다")

        # 업데이트
        if update.name:
            targets[idx]['name'] = update.name
        if update.category:
            targets[idx]['category'] = update.category
        if update.priority:
            targets[idx]['priority'] = update.priority
        if update.keywords is not None:
            targets[idx]['keywords'] = update.keywords

        # 파일 저장
        with open(targets_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {
            'status': 'success',
            'message': f'경쟁사 정보가 업데이트되었습니다'
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{competitor_id}")
async def delete_competitor(competitor_id: int) -> Dict[str, str]:
    """
    경쟁사 삭제

    Args:
        competitor_id: 경쟁사 ID (1-based index)

    Returns:
        상태 메시지
    """
    try:
        targets_path = os.path.join(parent_dir, 'config', 'targets.json')

        if not os.path.exists(targets_path):
            raise HTTPException(status_code=404, detail="설정 파일이 없습니다")

        with open(targets_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        targets = data.get('targets', [])
        idx = competitor_id - 1  # 1-based to 0-based

        if idx < 0 or idx >= len(targets):
            raise HTTPException(status_code=404, detail=f"경쟁사 ID {competitor_id}을(를) 찾을 수 없습니다")

        deleted_name = targets[idx].get('name', 'Unknown')
        del targets[idx]

        # 파일 저장
        with open(targets_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {
            'status': 'success',
            'message': f'경쟁사 "{deleted_name}"이(가) 삭제되었습니다'
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _calculate_impact_score(severity: str, type_count: int, days_old: int) -> int:
    """
    [Phase 5.0] 약점 영향도 점수 계산

    Args:
        severity: 심각도 (Critical/High/Medium/Low)
        type_count: 동일 유형 약점을 가진 경쟁사 수
        days_old: 발견 후 경과 일수

    Returns:
        0-100 범위의 영향도 점수
    """
    # 1. 심각도 점수 (40점 만점)
    severity_scores = {
        'Critical': 40,
        'High': 30,
        'Medium': 20,
        'Low': 10
    }
    severity_score = severity_scores.get(severity, 20)

    # 2. 확산도 점수 - 여러 경쟁사에서 발견될수록 높음 (30점 만점)
    # 1개 경쟁사: 10점, 2개: 20점, 3개+: 30점
    spread_score = min(type_count * 10, 30)

    # 3. 신선도 점수 - 최근 발견일수록 높음 (30점 만점)
    # 0-7일: 30점, 8-14일: 20점, 15-30일: 10점, 30일+: 5점
    if days_old <= 7:
        freshness_score = 30
    elif days_old <= 14:
        freshness_score = 20
    elif days_old <= 30:
        freshness_score = 10
    else:
        freshness_score = 5

    return severity_score + spread_score + freshness_score


@router.get("/weaknesses")
async def get_competitor_weaknesses(days: int = 30) -> List[Dict[str, Any]]:
    """
    경쟁사 약점 분석 결과 조회 (영향도 점수 포함)

    Args:
        days: 조회 기간 (일)

    Returns:
        약점 분석 결과 목록 (impact_score 포함)
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_weaknesses'")
        if not cursor.fetchone():
            print("[Weaknesses API] 테이블이 존재하지 않음")
            conn.close()
            return []

        # 전체 데이터 수 확인
        cursor.execute("SELECT COUNT(*) FROM competitor_weaknesses")
        total_count = cursor.fetchone()[0]
        print(f"[Weaknesses API] 전체 데이터 수: {total_count}")

        # 약점 유형별 경쟁사 수 집계 (확산도 계산용)
        cursor.execute("""
            SELECT weakness_type, COUNT(DISTINCT competitor_name) as comp_count
            FROM competitor_weaknesses
            GROUP BY weakness_type
        """)
        type_counts = {row['weakness_type']: row['comp_count'] for row in cursor.fetchall()}

        # 날짜 필터 (파라미터 바인딩)
        cursor.execute("""
            SELECT
                id,
                competitor_name,
                weakness_type,
                description,
                severity,
                evidence,
                source_url,
                created_at,
                julianday('now') - julianday(created_at) as days_old
            FROM competitor_weaknesses
            WHERE created_at >= datetime('now', '-' || ? || ' days')
            ORDER BY created_at DESC
            LIMIT 1000
        """, (days,))

        weaknesses = []
        for row in cursor.fetchall():
            weakness = dict(row)
            # [Phase 5.0] 영향도 점수 계산
            type_count = type_counts.get(weakness['weakness_type'], 1)
            days_old = int(weakness.get('days_old', 0))
            weakness['impact_score'] = _calculate_impact_score(
                weakness['severity'],
                type_count,
                days_old
            )
            # days_old 필드 제거 (내부용)
            weakness.pop('days_old', None)
            weaknesses.append(weakness)

        conn.close()

        # 영향도 점수 순으로 정렬
        weaknesses.sort(key=lambda x: x['impact_score'], reverse=True)

        return weaknesses

    except Exception as e:
        # 테이블이 없으면 빈 배열 반환
        print(f"[Competitors Weaknesses] Error: {e}")
        return []

@router.get("/weaknesses/summary")
async def get_weakness_summary() -> Dict[str, Any]:
    """
    약점 유형별 요약 통계

    Returns:
        - by_type: 유형별 약점 수
        - by_competitor: 경쟁사별 약점 수
        - total: 총 약점 수
    """
    default_response = {
        'total': 0,
        'by_type': {},
        'by_competitor': {}
    }

    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_weaknesses'")
        if not cursor.fetchone():
            conn.close()
            return default_response

        # 총 약점 수
        cursor.execute("SELECT COUNT(*) FROM competitor_weaknesses")
        total = cursor.fetchone()[0]

        # 유형별 통계
        cursor.execute("""
            SELECT weakness_type, COUNT(*) as count
            FROM competitor_weaknesses
            GROUP BY weakness_type
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

        # 경쟁사별 통계
        cursor.execute("""
            SELECT competitor_name, COUNT(*) as count
            FROM competitor_weaknesses
            GROUP BY competitor_name
        """)
        by_competitor = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

        conn.close()

        return {
            'total': total if total else 0,
            'by_type': by_type,
            'by_competitor': by_competitor
        }

    except Exception as e:
        # 테이블이 없으면 기본값 반환
        print(f"[Competitors Weakness Summary] Error: {e}")
        return default_response

@router.get("/opportunity-keywords")
async def get_opportunity_keywords(status: str = "pending") -> List[Dict[str, Any]]:
    """
    기회 키워드 조회 (약점 기반)

    Args:
        status: 상태 필터 (pending, used)

    Returns:
        기회 키워드 목록
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='opportunity_keywords'")
        if not cursor.fetchone():
            conn.close()
            return []

        cursor.execute("""
            SELECT
                keyword,
                weakness_type,
                opportunity_description,
                priority_score,
                status,
                created_at
            FROM opportunity_keywords
            WHERE status = ?
            ORDER BY priority_score DESC, created_at DESC
            LIMIT 1000
        """, (status,))

        keywords = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return keywords

    except Exception as e:
        # 테이블이 없으면 빈 배열 반환
        print(f"[Competitors Opportunity Keywords] Error: {e}")
        return []

@router.patch("/opportunity-keywords/{keyword}/mark-used")
async def mark_opportunity_used(keyword: str) -> Dict[str, str]:
    """
    기회 키워드를 사용 완료로 표시

    Args:
        keyword: 키워드

    Returns:
        상태 메시지
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='opportunity_keywords'")
        if not cursor.fetchone():
            conn.close()
            return {
                'status': 'warning',
                'message': '테이블이 존재하지 않습니다'
            }

        cursor.execute("""
            UPDATE opportunity_keywords
            SET status = 'used',
                updated_at = datetime('now')
            WHERE keyword = ?
        """, (keyword,))

        conn.commit()
        conn.close()

        return {
            'status': 'success',
            'message': f'"{keyword}" 사용 완료 표시'
        }

    except Exception as e:
        print(f"[Competitors Mark Opportunity Used] Error: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }

@router.post("/analyze-reviews")
async def analyze_reviews_for_weaknesses() -> Dict[str, Any]:
    """
    Gemini AI를 사용하여 competitor_reviews에서 약점을 분석하고 저장

    - gemini-3-flash-preview 모델 사용
    - 경쟁사별로 리뷰를 그룹화하여 일괄 분석
    - 약점 유형, 심각도, 기회 키워드 추출
    """
    from google import genai
    from google.genai import types
    from utils import ConfigManager

    try:
        # Gemini API 설정
        config = ConfigManager()
        api_key = config.get_api_key('GEMINI_API_KEY')
        if not api_key:
            raise HTTPException(status_code=500, detail="Gemini API 키가 설정되지 않았습니다")

        client = genai.Client(api_key=api_key)
        model_name = 'gemini-3-flash-preview'
        generation_config = types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=4096
        )

        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # competitor_weaknesses 테이블 생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS competitor_weaknesses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competitor_name TEXT,
                weakness_type TEXT,
                description TEXT,
                severity TEXT DEFAULT 'Medium',
                opportunity_keywords TEXT,
                source_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # opportunity_keywords 테이블 생성
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT UNIQUE,
                weakness_type TEXT,
                opportunity_description TEXT,
                priority_score REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 기존 데이터 삭제 (재분석)
        cursor.execute("DELETE FROM competitor_weaknesses")
        cursor.execute("DELETE FROM opportunity_keywords")

        # 경쟁사별 리뷰 조회
        cursor.execute("""
            SELECT competitor_name, GROUP_CONCAT(content, ' ||| ') as reviews
            FROM competitor_reviews
            WHERE content IS NOT NULL AND content != ''
            GROUP BY competitor_name
        """)

        competitors_reviews = cursor.fetchall()
        all_weaknesses = []
        all_opportunity_keywords = []

        for comp in competitors_reviews:
            competitor_name = comp['competitor_name']
            reviews_text = comp['reviews']

            # 리뷰가 너무 길면 잘라서 분석
            if len(reviews_text) > 15000:
                reviews_text = reviews_text[:15000] + "..."

            prompt = f"""당신은 마케팅 전략 분석가입니다. 아래는 "{competitor_name}" 한의원의 고객 리뷰입니다.

리뷰 내용:
{reviews_text}

위 리뷰들을 분석하여 "{competitor_name}"의 약점을 찾아주세요.

⚠️ 중요 규칙:
1. 오직 "{competitor_name}"에 대한 직접적인 불만/약점만 추출하세요.
2. 리뷰에서 "다른 병원", "타 병원", "예전에 다니던 곳" 등에 대한 불만은 절대 포함하지 마세요.
3. "{competitor_name}"을 칭찬하면서 타 병원을 비교하는 내용은 약점이 아닙니다.
4. 고객이 "{competitor_name}"에서 직접 겪은 부정적 경험만 약점으로 분류하세요.

다음 JSON 형식으로 정확히 응답해주세요 (다른 텍스트 없이 JSON만):
{{
    "weaknesses": [
        {{
            "type": "서비스|가격|시설|대기시간|효과|기타 중 하나",
            "description": "{competitor_name}의 구체적인 약점 설명 (50자 이내)",
            "severity": "Critical|High|Medium|Low 중 하나",
            "evidence": "리뷰에서 {competitor_name}에 대한 불만 문장 직접 인용"
        }}
    ],
    "opportunity_keywords": [
        {{
            "keyword": "우리가 활용할 수 있는 마케팅 키워드",
            "description": "이 키워드로 어떻게 차별화할 수 있는지",
            "priority": 1-10 점수
        }}
    ],
    "summary": "전체 분석 요약 (100자 이내)"
}}

약점은 최대 5개, 기회 키워드는 최대 3개까지만 추출하세요.
{competitor_name}에 대한 실제 불만만 포함하고, 타 병원에 대한 언급은 무시하세요.
약점을 찾을 수 없으면 빈 배열([])을 반환하세요."""

            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=generation_config
                )
                response_text = response.text.strip()

                # JSON 추출 (마크다운 코드블록 제거)
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]

                # 불완전한 JSON 복구 시도
                response_text = response_text.strip()
                try:
                    result = json.loads(response_text)
                except json.JSONDecodeError:
                    # 끝이 잘린 경우 복구 시도
                    # 마지막 유효한 } 또는 ] 찾기
                    for end_char in ['}', ']']:
                        last_idx = response_text.rfind(end_char)
                        if last_idx > 0:
                            try:
                                result = json.loads(response_text[:last_idx + 1] + '}' * (response_text[:last_idx + 1].count('{') - response_text[:last_idx + 1].count('}')))
                                print(f"[Gemini] {competitor_name} JSON 복구 성공")
                                break
                            except json.JSONDecodeError:
                                continue  # 다음 end_char로 재시도
                    else:
                        # 복구 실패 시 빈 결과
                        print(f"[Gemini] {competitor_name} JSON 복구 실패, 응답 길이: {len(response_text)}")
                        result = {'weaknesses': [], 'opportunity_keywords': [], 'summary': ''}

                # 약점 저장
                for w in result.get('weaknesses', []):
                    weakness_data = {
                        'competitor_name': competitor_name,
                        'weakness_type': w.get('type', '기타'),
                        'description': w.get('description', ''),
                        'severity': w.get('severity', 'Medium'),
                        'evidence': w.get('evidence', ''),
                        'opportunity_keywords': '',
                        'source_url': ''
                    }
                    all_weaknesses.append(weakness_data)

                    cursor.execute("""
                        INSERT INTO competitor_weaknesses
                        (competitor_name, weakness_type, description, severity, evidence, opportunity_keywords, source_url)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        weakness_data['competitor_name'],
                        weakness_data['weakness_type'],
                        weakness_data['description'],
                        weakness_data['severity'],
                        weakness_data['evidence'],
                        weakness_data['opportunity_keywords'],
                        weakness_data['source_url']
                    ))

                # 기회 키워드 저장
                for kw in result.get('opportunity_keywords', []):
                    keyword = kw.get('keyword', '')
                    if keyword:
                        all_opportunity_keywords.append(kw)
                        try:
                            cursor.execute("""
                                INSERT OR IGNORE INTO opportunity_keywords
                                (keyword, weakness_type, opportunity_description, priority_score, status)
                                VALUES (?, ?, ?, ?, 'pending')
                            """, (
                                keyword,
                                competitor_name,
                                kw.get('description', ''),
                                kw.get('priority', 5)
                            ))
                        except sqlite3.Error as e:
                            print(f"[DB] opportunity_keywords 삽입 실패: {e}")

                print(f"[Gemini] {competitor_name} 분석 완료: {len(result.get('weaknesses', []))}개 약점")

            except Exception as e:
                print(f"[Gemini] {competitor_name} 분석 오류: {e}")
                continue

        conn.commit()
        conn.close()

        # 유형별 통계
        type_counts = {}
        for w in all_weaknesses:
            t = w['weakness_type']
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            'status': 'success',
            'message': f'{len(all_weaknesses)}개 약점, {len(all_opportunity_keywords)}개 기회 키워드 분석 완료',
            'competitors_analyzed': len(competitors_reviews),
            'weaknesses_found': len(all_weaknesses),
            'opportunity_keywords_found': len(all_opportunity_keywords),
            'by_type': type_counts
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[analyze-reviews Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 경쟁사 약점 기반 콘텐츠 아웃라인 자동 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.post("/generate-content-outline")
async def generate_content_outline(weakness_type: str = None) -> Dict[str, Any]:
    """
    [Phase 4.0] 경쟁사 약점 기반 콘텐츠 아웃라인 생성

    경쟁사의 약점을 분석하여 우리 한의원의 강점을 부각시키는
    블로그/SNS 콘텐츠 아웃라인을 자동 생성합니다.

    Args:
        weakness_type: 약점 유형 필터 (service, price, facility, wait_time, effect)

    Returns:
        생성된 콘텐츠 아웃라인 목록
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 약점 데이터 조회
        if weakness_type:
            cursor.execute("""
                SELECT weakness_type, description, competitor_name, severity
                FROM competitor_weaknesses
                WHERE weakness_type = ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (weakness_type,))
        else:
            cursor.execute("""
                SELECT weakness_type, description, competitor_name, severity
                FROM competitor_weaknesses
                ORDER BY created_at DESC
                LIMIT 20
            """)

        weaknesses = cursor.fetchall()
        conn.close()

        if not weaknesses:
            return {
                "outlines": [],
                "message": "분석할 약점 데이터가 없습니다. 먼저 경쟁사 리뷰 분석을 실행해주세요."
            }

        # 약점 유형별 그룹화
        weakness_by_type = {}
        for w_type, desc, competitor, severity in weaknesses:
            if w_type not in weakness_by_type:
                weakness_by_type[w_type] = []
            weakness_by_type[w_type].append({
                "description": desc,
                "competitor": competitor,
                "severity": severity
            })

        # Gemini로 콘텐츠 아웃라인 생성
        outlines = []

        try:
            from google import genai
            from google.genai import types

            # API 키 로드
            config_path = os.path.join(parent_dir, 'config', 'config.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            api_key = config.get('gemini_api_key', os.getenv('GEMINI_API_KEY'))

            if not api_key:
                # Gemini 없이 기본 템플릿 사용
                for w_type, items in weakness_by_type.items():
                    outline = _generate_default_outline(w_type, items)
                    outlines.append(outline)
                return {"outlines": outlines, "source": "template"}

            client = genai.Client(api_key=api_key)

            for w_type, items in weakness_by_type.items():
                weakness_text = "\n".join([f"- {item['description']} ({item['competitor']})" for item in items[:5]])

                prompt = f"""당신은 한의원 마케팅 전문가입니다.

경쟁사들의 다음과 같은 약점이 발견되었습니다:

약점 유형: {w_type}
{weakness_text}

이 약점을 바탕으로 우리 한의원(규림한의원)의 강점을 부각시키는 블로그 콘텐츠 아웃라인을 작성해주세요.

다음 JSON 형식으로 응답하세요:
{{
    "title": "블로그 제목 (40자 이내, 클릭 유도형)",
    "hook": "서두 후킹 문구 (50자 이내)",
    "sections": [
        {{
            "heading": "섹션 제목",
            "key_points": ["핵심 포인트 1", "핵심 포인트 2"]
        }}
    ],
    "cta": "마무리 행동 유도 문구",
    "keywords": ["SEO 키워드 1", "SEO 키워드 2", "SEO 키워드 3"],
    "platform": "추천 게시 플랫폼 (블로그/인스타그램/유튜브)"
}}

실질적이고 구체적인 내용으로 작성해주세요."""

                try:
                    response = client.models.generate_content(
                        model="gemini-3-flash-preview",
                        contents=prompt
                    )
                    response_text = response.text.strip()

                    # JSON 파싱
                    if "```json" in response_text:
                        response_text = response_text.split("```json")[1].split("```")[0]
                    elif "```" in response_text:
                        response_text = response_text.split("```")[1].split("```")[0]

                    outline = json.loads(response_text)
                    outline["weakness_type"] = w_type
                    outline["based_on_count"] = len(items)
                    outlines.append(outline)

                except Exception as e:
                    print(f"[Gemini] {w_type} 콘텐츠 생성 오류: {e}")
                    # 오류 시 기본 템플릿 사용
                    outline = _generate_default_outline(w_type, items)
                    outlines.append(outline)

        except ImportError:
            # google-generativeai 없으면 기본 템플릿
            for w_type, items in weakness_by_type.items():
                outline = _generate_default_outline(w_type, items)
                outlines.append(outline)

        return {
            "outlines": outlines,
            "total": len(outlines),
            "source": "gemini" if outlines else "template"
        }

    except Exception as e:
        print(f"[generate-content-outline Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _generate_default_outline(weakness_type: str, items: list) -> Dict[str, Any]:
    """기본 콘텐츠 아웃라인 템플릿"""
    templates = {
        "service": {
            "title": "청주 한의원 추천, 친절한 상담이 다른 규림한의원",
            "hook": "한의원 상담 받으러 갔다가 불친절해서 기분 상하신 적 있으신가요?",
            "sections": [
                {"heading": "왜 친절한 상담이 중요한가요?", "key_points": ["환자 중심 진료", "충분한 설명"]},
                {"heading": "규림한의원의 차별화된 상담 시스템", "key_points": ["1:1 맞춤 상담", "치료 과정 상세 설명"]},
                {"heading": "실제 환자분들의 후기", "key_points": ["친절함에 대한 호평", "재방문 의사"]}
            ],
            "cta": "지금 바로 무료 상담 예약하세요!",
            "keywords": ["청주 한의원", "친절한 한의원", "청주 한의원 추천"],
            "platform": "블로그"
        },
        "price": {
            "title": "청주 한의원 가격, 투명한 진료비 안내",
            "hook": "한의원 비용이 걱정되시나요? 투명한 가격 정책을 알려드립니다.",
            "sections": [
                {"heading": "한의원 치료비, 왜 다를까요?", "key_points": ["치료 방식별 차이", "보험 적용 여부"]},
                {"heading": "규림한의원 가격 정책", "key_points": ["사전 안내", "분할 결제 가능"]},
                {"heading": "가격 대비 효과", "key_points": ["장기적 관점에서의 비용 효율", "부작용 최소화"]}
            ],
            "cta": "부담없이 상담받으세요, 첫 상담 무료!",
            "keywords": ["청주 한의원 가격", "한의원 비용", "청주 한의원 저렴한"],
            "platform": "블로그"
        },
        "facility": {
            "title": "청주 한의원 시설, 쾌적한 치료 환경",
            "hook": "깨끗하고 편안한 환경에서 치료받고 싶으시죠?",
            "sections": [
                {"heading": "치료 환경의 중요성", "key_points": ["청결한 시설", "편안한 분위기"]},
                {"heading": "규림한의원 시설 소개", "key_points": ["최신 장비", "넓은 주차 공간"]},
                {"heading": "환자 편의 시설", "key_points": ["개인 치료실", "쾌적한 대기 공간"]}
            ],
            "cta": "직접 방문해서 확인해보세요!",
            "keywords": ["청주 한의원", "청주 한의원 시설", "깨끗한 한의원"],
            "platform": "인스타그램"
        },
        "wait_time": {
            "title": "청주 한의원 예약제, 대기 없이 빠른 진료",
            "hook": "오래 기다리는 거 싫으시죠? 예약 시간에 바로 진료받으세요!",
            "sections": [
                {"heading": "대기 시간 스트레스", "key_points": ["시간은 금", "예약 시스템의 필요성"]},
                {"heading": "규림한의원 예약 시스템", "key_points": ["온라인 예약", "시간 엄수"]},
                {"heading": "효율적인 진료 흐름", "key_points": ["사전 문진", "신속 정확한 치료"]}
            ],
            "cta": "지금 바로 온라인 예약하세요!",
            "keywords": ["청주 한의원 예약", "대기없는 한의원", "빠른 진료"],
            "platform": "블로그"
        },
        "effect": {
            "title": "청주 한의원 효과, 실제 치료 사례 공개",
            "hook": "한의원 치료 효과가 정말 있을까요? 실제 사례로 보여드립니다.",
            "sections": [
                {"heading": "한방 치료의 과학적 근거", "key_points": ["연구 결과", "임상 경험"]},
                {"heading": "규림한의원 치료 사례", "key_points": ["Before/After", "환자 인터뷰"]},
                {"heading": "개인 맞춤 치료의 중요성", "key_points": ["체질 분석", "맞춤 처방"]}
            ],
            "cta": "효과를 직접 경험해보세요!",
            "keywords": ["청주 한의원 효과", "한의원 후기", "청주 한의원 치료"],
            "platform": "유튜브"
        }
    }

    template = templates.get(weakness_type, templates["service"])
    template["weakness_type"] = weakness_type
    template["based_on_count"] = len(items)
    return template


# ============================================
# [Phase 3.3] 경쟁사 자동 발견
# ============================================

@router.get("/discover")
async def discover_competitors(
    keyword_limit: int = 30,
    min_appearances: int = 3
) -> Dict[str, Any]:
    """
    [Phase 3.3] SERP 분석 기반 경쟁사 자동 발견

    내 키워드에서 반복 등장하는 도메인을 분석하여
    잠재적 경쟁사를 자동으로 발견합니다.

    Args:
        keyword_limit: 분석할 키워드 수 (기본 30개)
        min_appearances: 경쟁사로 판단할 최소 등장 횟수 (기본 3회)

    Returns:
        발견된 경쟁사 목록 및 통계
    """
    from collections import defaultdict, Counter
    import re

    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. 내 주요 키워드 조회 (S/A 등급 우선)
        cursor.execute("""
            SELECT keyword, grade, search_volume
            FROM keyword_insights
            WHERE grade IN ('S', 'A', 'B')
            ORDER BY
                CASE grade WHEN 'S' THEN 1 WHEN 'A' THEN 2 ELSE 3 END,
                search_volume DESC
            LIMIT ?
        """, (keyword_limit,))

        my_keywords = [row['keyword'] for row in cursor.fetchall()]

        if not my_keywords:
            conn.close()
            return {
                'status': 'no_data',
                'message': '분석할 키워드가 없습니다. Pathfinder를 먼저 실행해주세요.',
                'competitors': []
            }

        # 2. 현재 등록된 경쟁사 목록 (제외용)
        targets_path = os.path.join(parent_dir, 'config', 'targets.json')
        known_competitors = set()
        if os.path.exists(targets_path):
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for target in data.get('targets', []):
                    known_competitors.add(target.get('name', '').lower())

        # 내 업체명
        my_names = {'규림한의원', '규림', 'kyurim'}

        # 3. viral_targets에서 경쟁사 후보 추출
        domain_appearances = defaultdict(list)
        author_appearances = defaultdict(list)

        cursor.execute("""
            SELECT
                url,
                author,
                title,
                matched_keywords,
                platform
            FROM viral_targets
            WHERE is_commentable = 1
            ORDER BY scraped_at DESC
            LIMIT 2000
        """)

        for row in cursor.fetchall():
            url = row['url'] or ''
            author = row['author'] or ''
            title = row['title'] or ''
            keywords = (row['matched_keywords'] or '').split(',')

            # URL에서 도메인/카페명 추출
            cafe_match = re.search(r'cafe\.naver\.com/([^/\?]+)', url)
            if cafe_match:
                cafe_name = cafe_match.group(1)
                if cafe_name not in my_names:
                    domain_appearances[cafe_name].append({
                        'keywords': keywords,
                        'title': title,
                        'platform': row['platform']
                    })

            # 블로그 작성자 분석
            if author and len(author) >= 2:
                author_lower = author.lower()
                if author_lower not in my_names and '한의원' in author:
                    author_appearances[author].append({
                        'keywords': keywords,
                        'title': title,
                        'platform': row['platform']
                    })

        conn.close()

        # 4. 경쟁사 후보 집계
        potential_competitors = []

        # 카페/도메인 기반
        for domain, appearances in domain_appearances.items():
            if len(appearances) >= min_appearances:
                all_keywords = []
                for app in appearances:
                    all_keywords.extend(app['keywords'])
                keyword_freq = Counter(kw.strip() for kw in all_keywords if kw.strip())

                potential_competitors.append({
                    'name': domain,
                    'type': 'cafe',
                    'appearance_count': len(appearances),
                    'top_keywords': [kw for kw, _ in keyword_freq.most_common(5)],
                    'is_known': domain.lower() in known_competitors,
                    'confidence': min(len(appearances) / 10, 1.0)  # 0-1 신뢰도
                })

        # 작성자 기반
        for author, appearances in author_appearances.items():
            if len(appearances) >= min_appearances:
                all_keywords = []
                for app in appearances:
                    all_keywords.extend(app['keywords'])
                keyword_freq = Counter(kw.strip() for kw in all_keywords if kw.strip())

                potential_competitors.append({
                    'name': author,
                    'type': 'author',
                    'appearance_count': len(appearances),
                    'top_keywords': [kw for kw, _ in keyword_freq.most_common(5)],
                    'is_known': author.lower() in known_competitors,
                    'confidence': min(len(appearances) / 10, 1.0)
                })

        # 정렬 (등장 횟수 순)
        potential_competitors.sort(key=lambda x: x['appearance_count'], reverse=True)

        # 5. 결과 분류
        new_competitors = [c for c in potential_competitors if not c['is_known']]
        known_found = [c for c in potential_competitors if c['is_known']]

        return {
            'status': 'success',
            'analyzed_keywords': len(my_keywords),
            'total_found': len(potential_competitors),
            'new_competitors': new_competitors[:20],  # 상위 20개
            'known_competitors_activity': known_found,
            'summary': {
                'new_count': len(new_competitors),
                'known_active_count': len(known_found),
                'high_confidence': len([c for c in new_competitors if c['confidence'] >= 0.5])
            }
        }

    except Exception as e:
        print(f"[Competitors Discover] Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'message': str(e),
            'competitors': []
        }


@router.post("/discover/add")
async def add_discovered_competitor(competitor: CompetitorAdd) -> Dict[str, str]:
    """
    발견된 경쟁사를 등록

    Args:
        competitor: 경쟁사 정보

    Returns:
        상태 메시지
    """
    try:
        targets_path = os.path.join(parent_dir, 'config', 'targets.json')

        # 기존 데이터 로드
        if os.path.exists(targets_path):
            with open(targets_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {'targets': []}

        # 중복 체크
        existing_names = {t.get('name', '').lower() for t in data.get('targets', [])}
        if competitor.name.lower() in existing_names:
            return {
                'status': 'duplicate',
                'message': f'"{competitor.name}"은(는) 이미 등록된 경쟁사입니다.'
            }

        # 새 경쟁사 추가
        new_competitor = {
            'name': competitor.name,
            'place_id': competitor.place_id,
            'category': competitor.category,
            'priority': competitor.priority,
            'discovered_at': datetime.now().isoformat() if 'datetime' in dir() else None,
            'source': 'auto_discovery'
        }

        from datetime import datetime
        new_competitor['discovered_at'] = datetime.now().isoformat()

        data['targets'].append(new_competitor)

        # 저장
        with open(targets_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return {
            'status': 'success',
            'message': f'"{competitor.name}" 경쟁사가 등록되었습니다.'
        }

    except Exception as e:
        print(f"[Competitors Add Discovered] Error: {e}")
        return {
            'status': 'error',
            'message': str(e)
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 5.1] 경쟁사 실시간 모니터링
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/monitoring-dashboard")
async def get_monitoring_dashboard() -> Dict[str, Any]:
    """
    [Phase 5.1] 경쟁사 실시간 모니터링 대시보드

    경쟁사들의 최근 활동과 변화를 종합적으로 모니터링합니다.

    모니터링 항목:
    - 최근 리뷰 동향 (긍정/부정/중립)
    - 순위 변동 (우리 vs 경쟁사)
    - 새로운 약점 발견
    - 기회 키워드 추적

    Returns:
        실시간 모니터링 데이터
    """
    from datetime import datetime, timedelta

    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        dashboard = {
            'updated_at': datetime.now().isoformat(),
            'review_activity': {},
            'rank_changes': {},
            'new_weaknesses': [],
            'opportunity_keywords': [],
            'alerts': []
        }

        # 1. 최근 7일 리뷰 활동
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_reviews'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT
                    competitor_name,
                    COUNT(*) as review_count,
                    AVG(CASE
                        WHEN sentiment = 'positive' THEN 5
                        WHEN sentiment = 'neutral' THEN 3
                        ELSE 1
                    END) as avg_sentiment,
                    SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative_count
                FROM competitor_reviews
                WHERE date(scraped_at) >= date('now', '-7 days')
                GROUP BY competitor_name
                ORDER BY review_count DESC
            """)
            review_stats = [dict(row) for row in cursor.fetchall()]

            dashboard['review_activity'] = {
                'period': '7일',
                'competitors': review_stats,
                'total_reviews': sum(r['review_count'] for r in review_stats)
            }

            # 부정 리뷰 급증 경고
            for stat in review_stats:
                if stat['negative_count'] >= 3:
                    dashboard['alerts'].append({
                        'type': 'negative_surge',
                        'severity': 'warning',
                        'message': f"{stat['competitor_name']}에 부정 리뷰 {stat['negative_count']}건 발생",
                        'competitor': stat['competitor_name']
                    })

        # 2. 순위 변동 추적
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rank_history'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT
                    keyword,
                    MIN(rank) as best_rank,
                    MAX(rank) as worst_rank,
                    (SELECT rank FROM rank_history rh2
                     WHERE rh2.keyword = rh.keyword
                     ORDER BY scan_date DESC LIMIT 1) as current_rank,
                    (SELECT rank FROM rank_history rh3
                     WHERE rh3.keyword = rh.keyword
                     ORDER BY scan_date DESC LIMIT 1 OFFSET 7) as week_ago_rank
                FROM rank_history rh
                WHERE status = 'found'
                  AND scan_date >= date('now', '-14 days')
                GROUP BY keyword
                HAVING COUNT(*) >= 2
            """)
            rank_data = cursor.fetchall()

            improvements = []
            declines = []

            for row in rank_data:
                current = row['current_rank']
                week_ago = row['week_ago_rank']

                if current and week_ago:
                    change = week_ago - current  # 양수 = 순위 상승
                    if change >= 3:
                        improvements.append({
                            'keyword': row['keyword'],
                            'current': current,
                            'change': change
                        })
                    elif change <= -3:
                        declines.append({
                            'keyword': row['keyword'],
                            'current': current,
                            'change': change
                        })

            dashboard['rank_changes'] = {
                'improvements': improvements[:5],
                'declines': declines[:5]
            }

            # 순위 하락 경고
            for decline in declines[:3]:
                dashboard['alerts'].append({
                    'type': 'rank_decline',
                    'severity': 'info',
                    'message': f"'{decline['keyword']}' 순위 {abs(decline['change'])}단계 하락",
                    'keyword': decline['keyword']
                })

        # 3. 최근 발견된 약점
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_weaknesses'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT competitor_name, weakness_type, description as weakness_summary, created_at as discovered_at
                FROM competitor_weaknesses
                WHERE date(created_at) >= date('now', '-7 days')
                ORDER BY created_at DESC
                LIMIT 10
            """)
            dashboard['new_weaknesses'] = [dict(row) for row in cursor.fetchall()]

        # 4. 기회 키워드
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='opportunity_keywords'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT keyword, search_volume, competition_level, opportunity_score
                FROM opportunity_keywords
                ORDER BY opportunity_score DESC
                LIMIT 10
            """)
            dashboard['opportunity_keywords'] = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return dashboard

    except Exception as e:
        print(f"[Monitoring Dashboard] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competitor-activity/{competitor_name}")
async def get_competitor_activity(
    competitor_name: str,
    days: int = 30
) -> Dict[str, Any]:
    """
    [Phase 5.1] 특정 경쟁사 활동 상세 조회

    Args:
        competitor_name: 경쟁사 이름
        days: 조회 기간 (일)

    Returns:
        경쟁사 상세 활동 데이터
    """
    from datetime import datetime

    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        activity = {
            'competitor_name': competitor_name,
            'period_days': days,
            'reviews': [],
            'weaknesses': [],
            'sentiment_trend': []
        }

        # 리뷰 조회
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_reviews'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT content, rating, sentiment, scraped_at
                FROM competitor_reviews
                WHERE competitor_name = ?
                  AND date(scraped_at) >= date('now', ? || ' days')
                ORDER BY scraped_at DESC
                LIMIT 50
            """, (competitor_name, f'-{days}'))
            activity['reviews'] = [dict(row) for row in cursor.fetchall()]

            # 일별 sentiment 트렌드
            cursor.execute("""
                SELECT
                    date(scraped_at) as date,
                    COUNT(*) as count,
                    SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as positive,
                    SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative
                FROM competitor_reviews
                WHERE competitor_name = ?
                  AND date(scraped_at) >= date('now', ? || ' days')
                GROUP BY date(scraped_at)
                ORDER BY date
            """, (competitor_name, f'-{days}'))
            activity['sentiment_trend'] = [dict(row) for row in cursor.fetchall()]

        # 약점 조회
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_weaknesses'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT weakness_type, description as weakness_summary, severity, created_at as discovered_at
                FROM competitor_weaknesses
                WHERE competitor_name = ?
                ORDER BY created_at DESC
            """, (competitor_name,))
            activity['weaknesses'] = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return activity

    except Exception as e:
        print(f"[Competitor Activity] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# [Phase 5.2] Content Gap Analyzer
# ============================================================

@router.get("/content-gap")
async def get_content_gap_analysis() -> Dict[str, Any]:
    """
    [Phase 5.2] 콘텐츠 갭 분석

    경쟁사 대비 우리가 놓치고 있는 콘텐츠 영역을 분석합니다.

    Returns:
        - gap_keywords: 경쟁사는 있지만 우리는 없는 키워드
        - our_strengths: 우리만 보유한 키워드
        - shared_keywords: 공통 키워드
        - recommendations: 콘텐츠 제작 추천
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. 우리 키워드 (keyword_insights에서 S, A급)
        cursor.execute("""
            SELECT keyword, grade, search_volume, category
            FROM keyword_insights
            WHERE grade IN ('S', 'A')
            ORDER BY search_volume DESC
        """)
        our_keywords = {row['keyword']: dict(row) for row in cursor.fetchall()}

        # 2. 경쟁사 리뷰에서 언급된 키워드/서비스 추출
        cursor.execute("""
            SELECT content, competitor_name
            FROM competitor_reviews
            WHERE content IS NOT NULL AND content != ''
            ORDER BY scraped_at DESC
            LIMIT 500
        """)
        reviews = cursor.fetchall()

        # 서비스 관련 키워드 패턴
        service_keywords = [
            '다이어트', '체중', '비만', '한약', '침', '뜸', '추나', '교정',
            '통증', '허리', '목', '어깨', '무릎', '디스크', '관절',
            '피부', '여드름', '아토피', '비염', '알레르기',
            '소화', '위장', '변비', '설사', '역류',
            '불면', '스트레스', '우울', '불안', '두통',
            '산후', '갱년기', '생리', '임신', '출산',
            '성장', '키', '소아', '어린이', '청소년'
        ]

        # 경쟁사별 언급 키워드 집계
        competitor_keyword_mentions = {}
        for review in reviews:
            content = (review['content'] or '').lower()
            competitor = review['competitor_name']

            if competitor not in competitor_keyword_mentions:
                competitor_keyword_mentions[competitor] = {}

            for kw in service_keywords:
                if kw in content:
                    competitor_keyword_mentions[competitor][kw] = \
                        competitor_keyword_mentions[competitor].get(kw, 0) + 1

        # 3. 전체 경쟁사 키워드 통합
        all_competitor_keywords = {}
        for competitor, keywords in competitor_keyword_mentions.items():
            for kw, count in keywords.items():
                if kw not in all_competitor_keywords:
                    all_competitor_keywords[kw] = {'count': 0, 'competitors': []}
                all_competitor_keywords[kw]['count'] += count
                if competitor not in all_competitor_keywords[kw]['competitors']:
                    all_competitor_keywords[kw]['competitors'].append(competitor)

        # 4. 갭 분석
        our_keyword_set = set(our_keywords.keys())

        # 경쟁사에는 있지만 우리는 없는 키워드 (갭)
        gap_keywords = []
        for kw, data in all_competitor_keywords.items():
            # 키워드가 우리 목록에 없거나 관련 없는 경우
            has_related = any(kw in our_kw or our_kw in kw for our_kw in our_keyword_set)
            if not has_related and data['count'] >= 3:  # 최소 3회 언급
                gap_keywords.append({
                    'keyword': kw,
                    'mention_count': data['count'],
                    'competitor_count': len(data['competitors']),
                    'competitors': data['competitors'][:3],  # 상위 3개만
                    'priority': 'high' if data['count'] >= 10 else 'medium' if data['count'] >= 5 else 'low'
                })

        gap_keywords.sort(key=lambda x: x['mention_count'], reverse=True)

        # 5. 우리만의 강점 키워드
        our_strengths = []
        for kw, data in our_keywords.items():
            # 경쟁사 리뷰에 거의 언급되지 않은 우리 키워드
            competitor_mentions = all_competitor_keywords.get(kw, {}).get('count', 0)
            if competitor_mentions < 2:
                our_strengths.append({
                    'keyword': kw,
                    'grade': data['grade'],
                    'search_volume': data.get('search_volume', 0),
                    'category': data.get('category', 'general')
                })

        # 6. 공유 키워드 (경쟁 영역)
        shared_keywords = []
        for kw, data in our_keywords.items():
            competitor_data = all_competitor_keywords.get(kw, {})
            if competitor_data.get('count', 0) >= 3:
                shared_keywords.append({
                    'keyword': kw,
                    'our_grade': data['grade'],
                    'competitor_mentions': competitor_data['count'],
                    'competition_level': 'high' if competitor_data['count'] >= 10 else 'medium'
                })

        # 7. 콘텐츠 제작 추천
        recommendations = []
        for gap in gap_keywords[:5]:  # 상위 5개 갭에 대해
            recommendations.append({
                'keyword': gap['keyword'],
                'reason': f"경쟁사 {gap['competitor_count']}곳에서 {gap['mention_count']}회 언급되지만 우리 콘텐츠에 부재",
                'suggested_content': f"'{gap['keyword']}' 관련 블로그 포스트 또는 FAQ 작성 권장",
                'priority': gap['priority']
            })

        conn.close()

        return {
            'gap_keywords': gap_keywords[:20],  # 상위 20개
            'our_strengths': our_strengths[:10],  # 상위 10개
            'shared_keywords': shared_keywords[:10],  # 상위 10개
            'recommendations': recommendations,
            'summary': {
                'total_gaps': len(gap_keywords),
                'total_strengths': len(our_strengths),
                'total_shared': len(shared_keywords),
                'our_keyword_count': len(our_keywords),
                'competitor_keyword_count': len(all_competitor_keywords)
            }
        }

    except Exception as e:
        print(f"[Content Gap Analysis] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# [Phase 5.2] Competitor Weakness Radar
# ============================================================

@router.get("/weakness-radar")
async def get_weakness_radar() -> Dict[str, Any]:
    """
    [Phase 5.2] 경쟁사 약점 레이더

    경쟁사 부정 리뷰에서 반복되는 약점을 분석하고,
    이를 우리의 차별점으로 활용할 수 있는 기회를 발굴합니다.

    Returns:
        - weakness_frequency: 카테고리별 약점 빈도
        - competitor_breakdown: 경쟁사별 주요 약점
        - opportunities: 우리가 활용할 수 있는 기회
        - content_ideas: 콘텐츠 아이디어 제안
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 약점 카테고리 정의
        WEAKNESS_CATEGORIES = {
            'waiting_time': {
                'label': '대기시간',
                'keywords': ['대기', '기다', '오래', '줄', '예약'],
                'our_strength': '예약제 운영으로 대기 시간 최소화',
                'color': '#ef4444'
            },
            'price': {
                'label': '가격',
                'keywords': ['비싸', '가격', '부담', '비용', '돈'],
                'our_strength': '투명한 가격 정책과 사전 안내',
                'color': '#f59e0b'
            },
            'effectiveness': {
                'label': '효과',
                'keywords': ['효과', '안 듣', '실망', '별로', '기대'],
                'our_strength': '체질별 맞춤 치료로 높은 효과',
                'color': '#8b5cf6'
            },
            'service': {
                'label': '서비스',
                'keywords': ['불친절', '설명', '무시', '퉁명', '응대'],
                'our_strength': '친절한 상담과 충분한 설명',
                'color': '#ec4899'
            },
            'accessibility': {
                'label': '접근성',
                'keywords': ['주차', '접근', '위치', '찾기', '교통'],
                'our_strength': '편리한 주차와 좋은 접근성',
                'color': '#06b6d4'
            },
            'facility': {
                'label': '시설',
                'keywords': ['청결', '깨끗', '낡은', '오래', '환경'],
                'our_strength': '청결하고 쾌적한 치료 환경',
                'color': '#22c55e'
            }
        }

        # 1. 경쟁사 리뷰 분석
        cursor.execute("""
            SELECT competitor_name, content, rating, sentiment
            FROM competitor_reviews
            WHERE content IS NOT NULL AND content != ''
            ORDER BY scraped_at DESC
            LIMIT 1000
        """)
        reviews = cursor.fetchall()

        # 2. 카테고리별 약점 집계
        weakness_frequency = {cat: {'count': 0, 'competitors': {}} for cat in WEAKNESS_CATEGORIES}
        competitor_weaknesses = {}

        for review in reviews:
            content = (review['content'] or '').lower()
            competitor = review['competitor_name']
            rating = review['rating'] or 3
            sentiment = review['sentiment'] or 'neutral'

            # 부정적 리뷰만 분석 (평점 3점 이하 또는 부정 sentiment)
            if rating <= 3 or sentiment == 'negative':
                if competitor not in competitor_weaknesses:
                    competitor_weaknesses[competitor] = {cat: 0 for cat in WEAKNESS_CATEGORIES}

                for cat_id, cat_data in WEAKNESS_CATEGORIES.items():
                    for keyword in cat_data['keywords']:
                        if keyword in content:
                            weakness_frequency[cat_id]['count'] += 1
                            competitor_weaknesses[competitor][cat_id] += 1

                            if competitor not in weakness_frequency[cat_id]['competitors']:
                                weakness_frequency[cat_id]['competitors'][competitor] = 0
                            weakness_frequency[cat_id]['competitors'][competitor] += 1
                            break  # 카테고리당 1번만 카운트

        # 3. 결과 정리
        # 카테고리별 약점 빈도 (정렬)
        sorted_weaknesses = []
        for cat_id, data in weakness_frequency.items():
            if data['count'] > 0:
                top_competitors = sorted(
                    data['competitors'].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
                sorted_weaknesses.append({
                    'category': cat_id,
                    'label': WEAKNESS_CATEGORIES[cat_id]['label'],
                    'count': data['count'],
                    'color': WEAKNESS_CATEGORIES[cat_id]['color'],
                    'our_strength': WEAKNESS_CATEGORIES[cat_id]['our_strength'],
                    'top_competitors': [{'name': c[0], 'count': c[1]} for c in top_competitors]
                })

        sorted_weaknesses.sort(key=lambda x: x['count'], reverse=True)

        # 4. 경쟁사별 주요 약점
        competitor_breakdown = []
        for competitor, weaknesses in competitor_weaknesses.items():
            top_weakness = max(weaknesses.items(), key=lambda x: x[1]) if weaknesses else (None, 0)
            total_weaknesses = sum(weaknesses.values())

            if total_weaknesses > 0:
                competitor_breakdown.append({
                    'competitor': competitor,
                    'total_weaknesses': total_weaknesses,
                    'main_weakness': {
                        'category': top_weakness[0],
                        'label': WEAKNESS_CATEGORIES.get(top_weakness[0], {}).get('label', '기타'),
                        'count': top_weakness[1]
                    },
                    'breakdown': {
                        WEAKNESS_CATEGORIES[cat]['label']: count
                        for cat, count in weaknesses.items()
                        if count > 0
                    }
                })

        competitor_breakdown.sort(key=lambda x: x['total_weaknesses'], reverse=True)

        # 5. 기회 발굴
        opportunities = []
        for weakness in sorted_weaknesses[:5]:
            if weakness['count'] >= 3:
                opportunities.append({
                    'weakness_category': weakness['category'],
                    'weakness_label': weakness['label'],
                    'frequency': weakness['count'],
                    'affected_competitors': len(weakness['top_competitors']),
                    'our_differentiation': weakness['our_strength'],
                    'priority': 'high' if weakness['count'] >= 10 else 'medium' if weakness['count'] >= 5 else 'low'
                })

        # 6. 콘텐츠 아이디어
        content_ideas = []
        for opp in opportunities[:3]:
            label = opp['weakness_label']
            content_ideas.append({
                'title': f"왜 {label}이 중요한가요? 규림한의원의 차별화 포인트",
                'angle': f"경쟁사의 {label} 관련 불만을 우리의 강점으로 전환",
                'platforms': ['블로그', '인스타그램'],
                'keywords': [f'청주 한의원 {label}', f'{label} 좋은 한의원', f'청주 {label} 추천'],
                'hook': f"한의원 가서 {label} 때문에 불편하셨던 적 있으신가요?"
            })

        conn.close()

        return {
            'weakness_frequency': sorted_weaknesses,
            'competitor_breakdown': competitor_breakdown[:10],
            'opportunities': opportunities,
            'content_ideas': content_ideas,
            'summary': {
                'total_reviews_analyzed': len(reviews),
                'total_weaknesses_found': sum(w['count'] for w in sorted_weaknesses),
                'competitors_analyzed': len(competitor_breakdown),
                'top_opportunity': opportunities[0] if opportunities else None
            }
        }

    except Exception as e:
        print(f"[Weakness Radar] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
