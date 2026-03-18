"""
Weakness Content Generator
==========================
경쟁사 약점 기반 콘텐츠 자동 생성 시스템

워크플로우:
1. opportunity_keywords 테이블에서 pending 상태 키워드 조회
2. 각 키워드에 대해 AgentCrew로 블로그 콘텐츠 생성
3. 생성된 콘텐츠를 파일 및 DB에 저장
4. 키워드를 'used' 상태로 변경

사용법:
    python weakness_content_generator.py              # 기본 3개 키워드 처리
    python weakness_content_generator.py --limit 5    # 5개 키워드 처리
    python weakness_content_generator.py --list       # 대기 중인 키워드 목록
"""

import os
import sys
import argparse
from datetime import datetime
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils import ConfigManager, logger
from db.database import DatabaseManager
from agent_crew import AgentCrew


class WeaknessContentGenerator:
    """경쟁사 약점 기반 콘텐츠 생성기"""

    def __init__(self):
        self.config = ConfigManager()
        self.db = DatabaseManager()
        self.crew = AgentCrew()
        self.output_dir = os.path.join(self.config.root_dir, 'reports_content')

        # 출력 디렉토리 생성
        os.makedirs(self.output_dir, exist_ok=True)

    def get_pending_keywords(self, limit: int = 10) -> list:
        """대기 중인 기회 키워드 조회"""
        return self.db.get_opportunity_keywords(status='pending', limit=limit)

    def generate_content_for_keyword(self, keyword_data: dict) -> dict:
        """
        단일 키워드에 대한 콘텐츠 생성

        Args:
            keyword_data: {
                'keyword': str,
                'competitor_name': str,
                'weakness_type': str,
                'content_suggestion': str
            }

        Returns:
            {
                'keyword': str,
                'success': bool,
                'content': str,
                'file_path': str,
                'error': str (if failed)
            }
        """
        keyword = keyword_data.get('keyword', '')
        competitor = keyword_data.get('competitor_name', '')
        weakness_type = keyword_data.get('weakness_type', '')
        suggestion = keyword_data.get('content_suggestion', '')

        logger.info(f"[WeaknessContent] 콘텐츠 생성 시작: {keyword}")

        try:
            # 콘텐츠 생성 모드 결정
            mode_map = {
                '서비스': 'Service',
                '가격': 'Value',
                '시설': 'Facility',
                '대기시간': 'Convenience',
                '효과': 'Result'
            }
            mode = mode_map.get(weakness_type, 'General')

            # 토픽 구성 (경쟁사 약점 컨텍스트 포함)
            topic = f"""
키워드: {keyword}

[콘텐츠 방향]
경쟁사({competitor})의 약점인 '{weakness_type}' 부분을 우리(규림한의원)의 강점으로 어필하는 블로그 글을 작성하세요.

[콘텐츠 제안]
{suggestion if suggestion else f'{keyword}에 대해 규림한의원의 차별화된 장점을 강조'}

[필수 포함 요소]
- 규림한의원의 해당 분야 강점
- 환자 관점의 실질적 이점
- 자연스러운 내원 유도 (강압적이지 않게)
- 청주 지역 키워드 자연스럽게 포함
"""

            # AgentCrew로 콘텐츠 생성
            result = self.crew.produce_content(topic, mode)
            content = result.get('final', '')

            if not content or content.startswith('Error'):
                raise Exception(f"콘텐츠 생성 실패: {content}")

            # 파일 저장
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_keyword = keyword.replace(' ', '_').replace('/', '_')[:30]
            filename = f"weakness_{safe_keyword}_{timestamp}.md"
            file_path = os.path.join(self.output_dir, filename)

            # 메타데이터 포함 저장
            full_content = f"""---
keyword: {keyword}
competitor: {competitor}
weakness_type: {weakness_type}
generated_at: {datetime.now().isoformat()}
status: draft
---

# {keyword}

{content}

---
*이 콘텐츠는 경쟁사 약점 분석을 기반으로 자동 생성되었습니다.*
*게시 전 검토가 필요합니다.*
"""

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(full_content)

            # DB에 키워드 상태 업데이트
            self.db.mark_opportunity_used(keyword)

            # 생성 기록 저장
            self._save_generation_record(keyword_data, file_path, success=True)

            logger.info(f"[WeaknessContent] 콘텐츠 생성 완료: {file_path}")

            return {
                'keyword': keyword,
                'success': True,
                'content': content[:500] + '...' if len(content) > 500 else content,
                'file_path': file_path
            }

        except Exception as e:
            logger.error(f"[WeaknessContent] 콘텐츠 생성 실패 ({keyword}): {e}")
            self._save_generation_record(keyword_data, '', success=False, error=str(e))

            return {
                'keyword': keyword,
                'success': False,
                'content': '',
                'file_path': '',
                'error': str(e)
            }

    def _save_generation_record(self, keyword_data: dict, file_path: str,
                                 success: bool, error: str = ''):
        """생성 기록을 JSON 파일에 저장"""
        record_file = os.path.join(self.output_dir, 'generation_history.json')

        record = {
            'keyword': keyword_data.get('keyword', ''),
            'competitor': keyword_data.get('competitor_name', ''),
            'weakness_type': keyword_data.get('weakness_type', ''),
            'generated_at': datetime.now().isoformat(),
            'success': success,
            'file_path': file_path,
            'error': error
        }

        # 기존 기록 로드
        history = []
        if os.path.exists(record_file):
            try:
                with open(record_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"히스토리 파일 로드 실패: {e}")
                history = []

        history.append(record)

        # 최근 100개만 유지
        history = history[-100:]

        with open(record_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def run(self, limit: int = 3) -> dict:
        """
        메인 실행 함수

        Args:
            limit: 처리할 최대 키워드 수

        Returns:
            {
                'total': int,
                'success': int,
                'failed': int,
                'results': list
            }
        """
        logger.info(f"[WeaknessContent] 약점 기반 콘텐츠 생성 시작 (최대 {limit}개)")

        # 대기 중인 키워드 조회
        pending = self.get_pending_keywords(limit=limit)

        if not pending:
            logger.info("[WeaknessContent] 대기 중인 기회 키워드가 없습니다.")
            return {
                'total': 0,
                'success': 0,
                'failed': 0,
                'results': []
            }

        logger.info(f"[WeaknessContent] {len(pending)}개 키워드 처리 예정")

        results = []
        success_count = 0

        for i, kw_data in enumerate(pending, 1):
            logger.info(f"[WeaknessContent] 진행 중: {i}/{len(pending)} - {kw_data.get('keyword')}")

            result = self.generate_content_for_keyword(kw_data)
            results.append(result)

            if result['success']:
                success_count += 1

        summary = {
            'total': len(pending),
            'success': success_count,
            'failed': len(pending) - success_count,
            'results': results
        }

        logger.info(f"[WeaknessContent] 완료: {success_count}/{len(pending)} 성공")

        return summary

    def get_generation_history(self, limit: int = 20) -> list:
        """생성 히스토리 조회"""
        record_file = os.path.join(self.output_dir, 'generation_history.json')

        if not os.path.exists(record_file):
            return []

        try:
            with open(record_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            return history[-limit:][::-1]  # 최신순
        except (json.JSONDecodeError, IOError, FileNotFoundError):
            return []


def main():
    parser = argparse.ArgumentParser(description='경쟁사 약점 기반 콘텐츠 생성')
    parser.add_argument('--limit', type=int, default=3, help='처리할 키워드 수')
    parser.add_argument('--list', action='store_true', help='대기 중인 키워드 목록 출력')
    parser.add_argument('--history', action='store_true', help='생성 히스토리 출력')

    args = parser.parse_args()

    generator = WeaknessContentGenerator()

    if args.list:
        pending = generator.get_pending_keywords(limit=50)
        print(f"\n=== 대기 중인 기회 키워드 ({len(pending)}개) ===\n")
        for i, kw in enumerate(pending, 1):
            print(f"{i}. {kw.get('keyword')}")
            print(f"   경쟁사: {kw.get('competitor_name')} | 약점: {kw.get('weakness_type')}")
            print(f"   우선순위: {kw.get('priority_score', 0)}")
            print()
        return

    if args.history:
        history = generator.get_generation_history(limit=20)
        print(f"\n=== 콘텐츠 생성 히스토리 ({len(history)}건) ===\n")
        for record in history:
            status = "✅" if record.get('success') else "❌"
            print(f"{status} {record.get('generated_at', '')[:16]}")
            print(f"   키워드: {record.get('keyword')}")
            if record.get('success'):
                print(f"   파일: {record.get('file_path')}")
            else:
                print(f"   오류: {record.get('error')}")
            print()
        return

    # 콘텐츠 생성 실행
    result = generator.run(limit=args.limit)

    print(f"\n=== 콘텐츠 생성 결과 ===")
    print(f"총 처리: {result['total']}개")
    print(f"성공: {result['success']}개")
    print(f"실패: {result['failed']}개")

    if result['results']:
        print(f"\n=== 상세 결과 ===")
        for r in result['results']:
            status = "✅" if r['success'] else "❌"
            print(f"{status} {r['keyword']}")
            if r['success']:
                print(f"   파일: {r['file_path']}")
            else:
                print(f"   오류: {r.get('error', 'Unknown')}")


if __name__ == "__main__":
    main()
