#!/usr/bin/env python3
"""
경쟁사 자동 발견 시스템
- S급 키워드로 네이버 플레이스 검색
- 상위 한의원 자동 추출
- competitors.json 자동 업데이트
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import json
import requests
import time
from bs4 import BeautifulSoup
from typing import List, Dict, Set
from collections import Counter
from pathlib import Path
from datetime import datetime


class CompetitorDiscovery:
    """경쟁사 자동 발견"""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.delay = 1.0
        self._last_call = 0

        # 자사 제외
        self.exclude_names = [
            "규림한의원", "규림 한의원", "청주규림", "규림"
        ]

    def _rate_limit(self):
        """Rate limiting"""
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def search_naver_place(self, keyword: str) -> List[Dict]:
        """네이버 플레이스 검색 (상위 10개)"""
        self._rate_limit()

        url = "https://search.naver.com/search.naver"
        params = {"where": "nexearch", "query": keyword}

        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')

            places = []

            # 플레이스 결과 추출 (다양한 선택자 시도)
            place_list = soup.find('ul', class_='lst_total')
            if not place_list:
                place_list = soup.find('div', class_='place_section')

            if place_list:
                for item in place_list.find_all('li')[:10]:
                    try:
                        # 이름 추출
                        name_tag = item.find('a', class_='place_name') or item.find('a', class_='name')
                        if not name_tag:
                            name_tag = item.find('span', class_='name')

                        if name_tag:
                            name = name_tag.get_text(strip=True)

                            # 자사 제외
                            if any(ex in name for ex in self.exclude_names):
                                continue

                            # 한의원 확인
                            if '한의원' not in name and '한방병원' not in name:
                                continue

                            # 주소 추출 (선택사항)
                            addr_tag = item.find('span', class_='addr')
                            address = addr_tag.get_text(strip=True) if addr_tag else ""

                            # 청주 지역 확인
                            if address and '청주' not in address:
                                continue

                            places.append({
                                'name': name,
                                'address': address,
                                'keyword': keyword
                            })
                    except Exception:
                        continue

            return places[:10]

        except Exception as e:
            print(f"   ⚠️ 검색 실패 ({keyword}): {e}")
            return []

    def discover_from_keywords(self, keywords: List[str], top_n: int = 5) -> Dict:
        """
        키워드 리스트에서 경쟁사 발견

        Args:
            keywords: S급 키워드 리스트
            top_n: 상위 N개 키워드만 사용

        Returns:
            카테고리별 경쟁사 딕셔너리
        """
        print(f"🔍 경쟁사 자동 발견 시작 ({len(keywords)}개 키워드)")

        # 키워드를 카테고리별로 그룹화 (간단한 패턴 매칭)
        category_keywords = {
            "다이어트": [],
            "안면비대칭_교정": [],
            "여드름_피부": [],
            "교통사고_입원": [],
            "리프팅_탄력": []
        }

        for kw in keywords[:top_n]:
            if "다이어트" in kw or "비만" in kw:
                category_keywords["다이어트"].append(kw)
            elif "안면비대칭" in kw or "얼굴비대칭" in kw or "체형교정" in kw:
                category_keywords["안면비대칭_교정"].append(kw)
            elif "여드름" in kw or "피부" in kw or "아토피" in kw:
                category_keywords["여드름_피부"].append(kw)
            elif "교통사고" in kw:
                category_keywords["교통사고_입원"].append(kw)
            elif "리프팅" in kw or "매선" in kw or "탄력" in kw:
                category_keywords["리프팅_탄력"].append(kw)

        # 카테고리별 경쟁사 수집
        discovered_competitors = {}

        for category, cat_keywords in category_keywords.items():
            if not cat_keywords:
                continue

            print(f"\n[{category}] {len(cat_keywords)}개 키워드 검색...")

            all_places = []
            for kw in cat_keywords[:3]:  # 카테고리당 상위 3개만
                places = self.search_naver_place(kw)
                all_places.extend(places)
                print(f"   {kw}: {len(places)}개 발견")

            if not all_places:
                continue

            # 빈도수 계산 (가장 자주 등장하는 한의원)
            name_counter = Counter([p['name'] for p in all_places])
            top_competitors = name_counter.most_common(3)

            discovered_competitors[category] = {
                "main_competitors": [
                    {
                        "name": name,
                        "frequency": count,
                        "priority": "high" if count >= 2 else "medium",
                        "discovered_at": datetime.now().strftime("%Y-%m-%d")
                    }
                    for name, count in top_competitors
                ],
                "keywords_to_monitor": cat_keywords[:9]
            }

            print(f"   발견: {', '.join([c['name'] for c in discovered_competitors[category]['main_competitors']])}")

        return discovered_competitors

    def update_config(self, discovered: Dict, config_path: str = "config/competitors.json"):
        """
        competitors.json 업데이트

        Args:
            discovered: 발견된 경쟁사 딕셔너리
            config_path: 설정 파일 경로
        """
        # 기존 설정 로드
        config_file = Path(config_path)
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {
                "description": "경쟁사 인텔리전스 설정",
                "last_updated": "",
                "auto_discovery_enabled": True,
                "category_competitors": {}
            }

        # 업데이트
        config["last_updated"] = datetime.now().strftime("%Y-%m-%d")

        for category, data in discovered.items():
            if category not in config["category_competitors"]:
                config["category_competitors"][category] = {
                    "main_competitors": [],
                    "keywords_to_monitor": []
                }

            # 기존 경쟁사 유지하면서 신규 추가
            existing_names = {c.get('name') for c in config["category_competitors"][category].get("main_competitors", [])}

            for comp in data["main_competitors"]:
                if comp["name"] not in existing_names:
                    config["category_competitors"][category]["main_competitors"].append({
                        "name": comp["name"],
                        "priority": comp["priority"],
                        "auto_discovered": True,
                        "discovered_at": comp["discovered_at"]
                    })

            # 키워드 업데이트
            config["category_competitors"][category]["keywords_to_monitor"] = list(set(
                config["category_competitors"][category].get("keywords_to_monitor", []) +
                data["keywords_to_monitor"]
            ))[:15]  # 최대 15개

        # 저장
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)

        print(f"\n✅ {config_path} 업데이트 완료")

        return config


def main():
    """CLI 실행"""
    import argparse
    from db.database import DatabaseManager

    parser = argparse.ArgumentParser(description="경쟁사 자동 발견")
    parser.add_argument("--top", type=int, default=20, help="사용할 상위 S급 키워드 수 (기본: 20)")
    args = parser.parse_args()

    # DB에서 S급 키워드 가져오기
    db = DatabaseManager()

    print("📊 DB에서 S급 키워드 로드 중...")
    s_grade_keywords = db.get_keywords_by_filter(grade='S', limit=args.top)

    if not s_grade_keywords:
        print("❌ S급 키워드가 없습니다. 먼저 LEGION을 실행하세요.")
        return

    keywords = [k['keyword'] for k in s_grade_keywords]
    print(f"✅ {len(keywords)}개 S급 키워드 로드 완료")

    # 경쟁사 발견
    discovery = CompetitorDiscovery()
    discovered = discovery.discover_from_keywords(keywords, top_n=args.top)

    if not discovered:
        print("❌ 경쟁사를 발견하지 못했습니다.")
        return

    # 설정 파일 업데이트
    config = discovery.update_config(discovered)

    # 요약 출력
    print("\n" + "=" * 70)
    print("📊 경쟁사 발견 요약")
    print("=" * 70)

    for category, data in discovered.items():
        print(f"\n[{category}]")
        for comp in data['main_competitors']:
            print(f"   - {comp['name']} (빈도: {comp['frequency']}, 우선순위: {comp['priority']})")


if __name__ == "__main__":
    main()
