"""
🎯 바이럴 헌터 웹앱 (Flask 백엔드)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

실행: python app.py
접속: http://localhost:5000
"""

from flask import Flask, render_template, jsonify, request
import json
import sys
import os

# 상위 디렉토리를 path에 추가 (viral_hunter 모듈 import용)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from viral_hunter import ViralHunter, ViralTarget

app = Flask(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 카테고리 매핑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CATEGORY_MAPPING = {
    "다이어트": ["다이어트", "살빼", "체중", "비만", "감량", "산후다이어트", "살빼기"],
    "비대칭/교정": ["비대칭", "안면비대칭", "얼굴비대칭", "체형교정", "골반", "교정"],
    "피부": ["피부", "여드름", "리프팅", "주름", "탄력", "흉터", "트러블", "피부관리"],
    "교통사고": ["교통사고", "자동차사고", "사고치료", "교통사고입원", "사고후유증"],
    "통증/디스크": ["허리", "목", "어깨", "무릎", "통증", "디스크", "추나", "도수", "요통"],
    "두통/어지럼": ["두통", "편두통", "어지럼", "어지러움", "현훈"],
    "소화기": ["소화", "위염", "역류", "설사", "변비", "소화불량"],
    "호흡기": ["감기", "비염", "알레르기", "천식", "기침"],
    "기타증상": ["이석증", "탈모", "다한증", "불면", "수면", "불면증"],
}

def auto_categorize(title, keywords):
    """제목과 키워드로 카테고리 자동 분류"""
    text = f"{title} {' '.join(keywords)}".lower()

    for category, patterns in CATEGORY_MAPPING.items():
        if any(pattern.lower() in text for pattern in patterns):
            return category

    return "기타"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 라우트
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    """전체 통계"""
    try:
        hunter = ViralHunter()
        stats = hunter.get_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/categories')
def get_categories():
    """카테고리별 통계"""
    try:
        hunter = ViralHunter()
        all_targets = hunter.list_targets(status='pending', limit=10000)

        category_stats = {}

        for target in all_targets:
            keywords = target.get('matched_keywords', [])
            if isinstance(keywords, str):
                keywords = json.loads(keywords)

            category = auto_categorize(target.get('title', ''), keywords)

            if category not in category_stats:
                category_stats[category] = {
                    'count': 0,
                    'max_score': 0,
                    'scores': []
                }

            category_stats[category]['count'] += 1
            score = target.get('priority_score', 0)
            category_stats[category]['scores'].append(score)
            category_stats[category]['max_score'] = max(
                category_stats[category]['max_score'],
                score
            )

        # 평균 점수 및 우선순위 계산
        for cat, stats in category_stats.items():
            if stats['scores']:
                stats['avg_score'] = sum(stats['scores']) / len(stats['scores'])
                stats['priority'] = (
                    stats['max_score'] * 0.5 +
                    stats['avg_score'] * 0.3 +
                    stats['count'] * 0.2
                )
            else:
                stats['avg_score'] = 0
                stats['priority'] = 0
            del stats['scores']  # 클라이언트로 전송 안함

        # 우선순위 순 정렬
        sorted_categories = sorted(
            category_stats.items(),
            key=lambda x: x[1]['priority'],
            reverse=True
        )

        return jsonify(sorted_categories)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/targets/<path:category>')
def get_targets(category):
    """특정 카테고리의 타겟 목록"""
    try:
        # URL 디코딩
        from urllib.parse import unquote
        category = unquote(category)

        hunter = ViralHunter()
        all_targets = hunter.list_targets(status='pending', limit=10000)

        category_targets = []
        for target in all_targets:
            keywords = target.get('matched_keywords', [])
            if isinstance(keywords, str):
                keywords = json.loads(keywords)

            target_category = auto_categorize(target.get('title', ''), keywords)

            if target_category == category:
                # JSON 직렬화 가능하도록 변환
                target_dict = dict(target)
                if isinstance(target_dict.get('matched_keywords'), str):
                    target_dict['matched_keywords'] = json.loads(target_dict['matched_keywords'])
                category_targets.append(target_dict)

        # 우선순위 순 정렬
        category_targets.sort(
            key=lambda x: x.get('priority_score', 0),
            reverse=True
        )

        return jsonify(category_targets)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate_comment', methods=['POST'])
def generate_comment():
    """AI 댓글 생성"""
    try:
        data = request.json
        hunter = ViralHunter()

        # ViralTarget 객체 생성
        target_obj = ViralTarget(
            platform=data.get('platform', 'unknown'),
            url=data.get('url', ''),
            title=data.get('title', ''),
            content_preview=data.get('content_preview', ''),
            matched_keywords=data.get('matched_keywords', []),
            category=data.get('category', '기타'),
            priority_score=data.get('priority_score', 0)
        )

        # 댓글 생성
        comment = hunter.generator.generate(target_obj)

        if comment:
            return jsonify({'success': True, 'comment': comment})
        else:
            return jsonify({'success': False, 'error': '댓글 생성 실패'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/approve', methods=['POST'])
def approve_target():
    """타겟 승인"""
    try:
        data = request.json
        hunter = ViralHunter()

        hunter.db.update_viral_target(data['target_id'], {
            'generated_comment': data['comment'],
            'comment_status': 'posted'
        })

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/skip', methods=['POST'])
def skip_target():
    """타겟 건너뛰기"""
    try:
        data = request.json
        hunter = ViralHunter()

        hunter.db.update_viral_target(data['target_id'], {
            'comment_status': 'skipped'
        })

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete', methods=['POST'])
def delete_target():
    """타겟 삭제"""
    try:
        data = request.json
        hunter = ViralHunter()

        hunter.db.update_viral_target(data['target_id'], {
            'comment_status': 'deleted'
        })

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == '__main__':
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🎯 바이럴 헌터 웹앱 시작")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("📍 URL: http://localhost:5000")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    app.run(debug=True, host='0.0.0.0', port=5000)
