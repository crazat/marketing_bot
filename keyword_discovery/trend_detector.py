#!/usr/bin/env python3
"""
검색 트렌드 이상 감지
- 갑자기 급증하는 키워드 포착
- 시즌/이벤트 키워드 선점 기회
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import json
import time
import random
import requests
import hashlib
import hmac
import base64
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from collections import defaultdict


class TrendDetector:
    """검색 트렌드 이상 감지"""

    def __init__(self, region: str = "청주"):
        self.region = region

        # DataLab API 설정
        self.datalab_keys = self._load_datalab_keys()
        self.current_key_index = 0

        # 모니터링할 키워드 그룹
        self.monitoring_groups = {
            "다이어트": [
                f"{region} 다이어트", f"{region} 다이어트 한의원", f"{region} 다이어트 한약",
                f"{region} 살빼는 한약", f"{region} 비만 한의원"
            ],
            "교통사고": [
                f"{region} 교통사고", f"{region} 교통사고 한의원", f"{region} 교통사고 병원",
                f"{region} 자동차사고 치료"
            ],
            "피부/여드름": [
                f"{region} 여드름", f"{region} 여드름 한의원", f"{region} 피부 한의원",
                f"{region} 새살침"
            ],
            "탈모": [
                f"{region} 탈모", f"{region} 탈모 한의원", f"{region} 탈모치료",
                f"{region} 두피 한의원"
            ],
            "통증": [
                f"{region} 허리통증", f"{region} 목통증", f"{region} 어깨통증",
                f"{region} 디스크 한의원", f"{region} 추나"
            ],
            "산후": [
                f"{region} 산후조리", f"{region} 산후 한의원", f"{region} 산후다이어트",
                f"{region} 골반교정"
            ],
            "시즌": [
                f"{region} 봄 알레르기", f"{region} 환절기 감기", f"{region} 면역력",
                f"{region} 보약", f"{region} 수능 집중력"
            ],
        }

        # 이상 감지 임계값
        self.spike_threshold = 1.5  # 50% 이상 급증
        self.drop_threshold = 0.5   # 50% 이상 급감

    def _load_datalab_keys(self) -> List[Dict]:
        """DataLab API 키 로드"""
        keys = []

        # .env 파일에서 로드 시도
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass

        # 환경 변수에서 로드 (SECRET 변수명 사용 - .env 파일 기준)
        for i in range(1, 5):
            client_id = os.environ.get(f'NAVER_DATALAB_CLIENT_ID_{i}')
            client_secret = os.environ.get(f'NAVER_DATALAB_SECRET_{i}')  # SECRET (not CLIENT_SECRET)

            if client_id and client_secret:
                keys.append({
                    'client_id': client_id,
                    'client_secret': client_secret
                })

        # 추가 키 로드 시도 (다른 변수명 포맷)
        if not keys:
            for i in range(1, 5):
                client_id = os.environ.get(f'NAVER_DATALAB_CLIENT_ID_{i}')
                client_secret = os.environ.get(f'NAVER_DATALAB_CLIENT_SECRET_{i}')

                if client_id and client_secret:
                    keys.append({
                        'client_id': client_id,
                        'client_secret': client_secret
                    })

        return keys

    def _get_next_key(self) -> Dict:
        """다음 API 키 가져오기 (로테이션)"""
        if not self.datalab_keys:
            return None

        key = self.datalab_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.datalab_keys)
        return key

    def get_trend_data(self, keywords: List[str], days: int = 30) -> Dict:
        """DataLab API로 트렌드 데이터 가져오기"""
        key = self._get_next_key()
        if not key:
            return {}

        try:
            url = "https://openapi.naver.com/v1/datalab/search"

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # 키워드 그룹 생성 (최대 5개)
            keyword_groups = []
            for kw in keywords[:5]:
                keyword_groups.append({
                    "groupName": kw,
                    "keywords": [kw]
                })

            body = {
                "startDate": start_date.strftime("%Y-%m-%d"),
                "endDate": end_date.strftime("%Y-%m-%d"),
                "timeUnit": "date",
                "keywordGroups": keyword_groups
            }

            headers = {
                "X-Naver-Client-Id": key['client_id'],
                "X-Naver-Client-Secret": key['client_secret'],
                "Content-Type": "application/json"
            }

            response = requests.post(url, json=body, headers=headers, timeout=10)

            if response.status_code == 200:
                return response.json()

            time.sleep(0.5)

        except Exception as e:
            print(f"   DataLab API 오류: {e}")

        return {}

    def calculate_trend_change(self, data: Dict) -> List[Dict]:
        """트렌드 변화율 계산"""
        changes = []

        results = data.get('results', [])

        for result in results:
            keyword = result.get('title', '')
            data_points = result.get('data', [])

            if len(data_points) < 14:  # 최소 2주 데이터 필요
                continue

            # 최근 7일 평균
            recent_7 = [d['ratio'] for d in data_points[-7:]]
            recent_avg = sum(recent_7) / len(recent_7) if recent_7 else 0

            # 이전 7일 평균
            prev_7 = [d['ratio'] for d in data_points[-14:-7]]
            prev_avg = sum(prev_7) / len(prev_7) if prev_7 else 0

            # 변화율 계산
            if prev_avg > 0:
                change_ratio = recent_avg / prev_avg
            else:
                change_ratio = 1.0

            # 트렌드 방향
            if change_ratio >= self.spike_threshold:
                status = "spike"
            elif change_ratio <= self.drop_threshold:
                status = "drop"
            elif change_ratio >= 1.1:
                status = "rising"
            elif change_ratio <= 0.9:
                status = "falling"
            else:
                status = "stable"

            changes.append({
                'keyword': keyword,
                'recent_avg': round(recent_avg, 2),
                'prev_avg': round(prev_avg, 2),
                'change_ratio': round(change_ratio, 2),
                'change_pct': round((change_ratio - 1) * 100, 1),
                'status': status
            })

        return changes

    def detect_anomalies(self) -> Dict:
        """이상 감지 실행"""
        all_changes = []
        spikes = []
        drops = []

        for group_name, keywords in self.monitoring_groups.items():
            print(f"   분석 중: {group_name}")

            data = self.get_trend_data(keywords, days=30)
            changes = self.calculate_trend_change(data)

            for change in changes:
                change['group'] = group_name
                all_changes.append(change)

                if change['status'] == 'spike':
                    spikes.append(change)
                elif change['status'] == 'drop':
                    drops.append(change)

            time.sleep(1)  # API 속도 제한

        # 변화율 순으로 정렬
        spikes.sort(key=lambda x: x['change_ratio'], reverse=True)
        drops.sort(key=lambda x: x['change_ratio'])

        return {
            'all_changes': all_changes,
            'spikes': spikes,
            'drops': drops
        }

    def generate_opportunity_keywords(self, spikes: List[Dict]) -> List[str]:
        """급증 키워드에서 기회 키워드 생성"""
        keywords = set()

        for spike in spikes:
            base_kw = spike['keyword']

            # 관련 확장
            keywords.add(base_kw)
            keywords.add(f"{base_kw} 추천")
            keywords.add(f"{base_kw} 잘하는곳")
            keywords.add(f"{base_kw} 가격")

            # 지역 변형
            if self.region in base_kw:
                # 주변 지역 추가
                for nearby in ["충주", "세종", "오창"]:
                    keywords.add(base_kw.replace(self.region, nearby))

        return list(keywords)

    def run(self) -> Dict:
        """전체 트렌드 분석 실행"""
        print("=" * 60)
        print("📈 검색 트렌드 이상 감지")
        print("=" * 60)
        print()

        if not self.datalab_keys:
            print("⚠️ DataLab API 키가 없습니다. 시뮬레이션 모드로 실행합니다.")
            return self._run_simulation()

        print(f"🔑 API 키: {len(self.datalab_keys)}개 로드됨")
        print(f"📊 모니터링 그룹: {len(self.monitoring_groups)}개")
        print()

        # 이상 감지
        results = self.detect_anomalies()

        # 결과 출력
        print("\n🚀 급증 키워드 (선점 기회!):")
        if results['spikes']:
            for spike in results['spikes'][:10]:
                print(f"   🔥 {spike['keyword']}: +{spike['change_pct']}% ({spike['group']})")
        else:
            print("   급증 키워드 없음")

        print("\n📉 급감 키워드 (주의):")
        if results['drops']:
            for drop in results['drops'][:5]:
                print(f"   ⚠️ {drop['keyword']}: {drop['change_pct']}% ({drop['group']})")
        else:
            print("   급감 키워드 없음")

        # 기회 키워드 생성
        opportunity_keywords = self.generate_opportunity_keywords(results['spikes'])
        print(f"\n🎯 기회 키워드 생성: {len(opportunity_keywords)}개")

        return {
            'spikes': results['spikes'],
            'drops': results['drops'],
            'all_changes': results['all_changes'],
            'opportunity_keywords': opportunity_keywords,
            'timestamp': datetime.now().isoformat()
        }

    def _run_simulation(self) -> Dict:
        """시뮬레이션 모드 (API 없을 때)"""
        # 시즌 기반 시뮬레이션 데이터
        current_month = datetime.now().month

        simulated_spikes = []
        simulated_drops = []

        # 2월 시즌 키워드
        if current_month == 2:
            simulated_spikes = [
                {'keyword': f'{self.region} 졸업 다이어트', 'change_pct': 85, 'status': 'spike', 'group': '시즌'},
                {'keyword': f'{self.region} 봄 피부관리', 'change_pct': 62, 'status': 'spike', 'group': '시즌'},
                {'keyword': f'{self.region} 환절기 면역력', 'change_pct': 45, 'status': 'spike', 'group': '시즌'},
                {'keyword': f'{self.region} 입학 전 교정', 'change_pct': 38, 'status': 'spike', 'group': '시즌'},
            ]

        print("\n🚀 급증 키워드 (시뮬레이션):")
        for spike in simulated_spikes:
            print(f"   🔥 {spike['keyword']}: +{spike['change_pct']}%")

        opportunity_keywords = self.generate_opportunity_keywords(simulated_spikes)

        return {
            'spikes': simulated_spikes,
            'drops': simulated_drops,
            'opportunity_keywords': opportunity_keywords,
            'simulation': True,
            'timestamp': datetime.now().isoformat()
        }


def main():
    detector = TrendDetector(region="청주")
    results = detector.run()

    # 결과 저장
    output_path = "keyword_discovery/trend_detection_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print()
    print(f"💾 결과 저장: {output_path}")

    return results


if __name__ == "__main__":
    main()
