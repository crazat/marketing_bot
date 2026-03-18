#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NoneType 에러 방어 코드 패치
기존 데이터는 유지하면서 None 체크 추가
"""

import sys
import os
from pathlib import Path

# UTF-8 설정
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8')

def fix_pathfinder_v3_legion():
    """pathfinder_v3_legion.py의 NoneType 방어 코드 추가"""

    file_path = Path(__file__).parent.parent / "pathfinder_v3_legion.py"

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 체크 포인트 1: get_autocomplete 결과 None 체크
    old_pattern1 = """        for seed in self.base_seeds:
            suggestions = self.collector.get_autocomplete(seed)
            round1_keywords.update(suggestions)"""

    new_pattern1 = """        for seed in self.base_seeds:
            suggestions = self.collector.get_autocomplete(seed)
            if suggestions is not None:  # None 방어
                round1_keywords.update(suggestions)"""

    if old_pattern1 in content:
        content = content.replace(old_pattern1, new_pattern1)
        print("[1] Round 1 get_autocomplete None 체크 추가")

    # 체크 포인트 2: Round 2 get_autocomplete
    old_pattern2 = """        for kw in sa_keywords[:30]:  # 상위 30개만
            suggestions = self.collector.get_autocomplete(kw)
            round2_keywords.update(suggestions)"""

    new_pattern2 = """        for kw in sa_keywords[:30]:  # 상위 30개만
            suggestions = self.collector.get_autocomplete(kw)
            if suggestions is not None:  # None 방어
                round2_keywords.update(suggestions)"""

    if old_pattern2 in content:
        content = content.replace(old_pattern2, new_pattern2)
        print("[2] Round 2 get_autocomplete None 체크 추가")

    # 체크 포인트 3: Round 3
    old_pattern3 = """                seed = f"{dong} {term}"
                suggestions = self.collector.get_autocomplete(seed)
                round3_keywords.update(suggestions)"""

    new_pattern3 = """                seed = f"{dong} {term}"
                suggestions = self.collector.get_autocomplete(seed)
                if suggestions is not None:  # None 방어
                    round3_keywords.update(suggestions)"""

    if old_pattern3 in content:
        content = content.replace(old_pattern3, new_pattern3)
        print("[3] Round 3 get_autocomplete None 체크 추가")

    # 체크 포인트 4: Round 4
    old_pattern4 = """                # 자동완성도 확인
                suggestions = self.collector.get_autocomplete(new_kw)
                round4_keywords.update(suggestions)"""

    new_pattern4 = """                # 자동완성도 확인
                suggestions = self.collector.get_autocomplete(new_kw)
                if suggestions is not None:  # None 방어
                    round4_keywords.update(suggestions)"""

    if old_pattern4 in content:
        content = content.replace(old_pattern4, new_pattern4)
        print("[4] Round 4 get_autocomplete None 체크 추가")

    # 체크 포인트 5: Round 5
    old_pattern5 = """                        # 블로그 검색
                        suggestions = self.collector.get_autocomplete(f"{blog_id} 한의원")
                        round5_keywords.update(suggestions)"""

    new_pattern5 = """                        # 블로그 검색
                        suggestions = self.collector.get_autocomplete(f"{blog_id} 한의원")
                        if suggestions is not None:  # None 방어
                            round5_keywords.update(suggestions)"""

    if old_pattern5 in content:
        content = content.replace(old_pattern5, new_pattern5)
        print("[5] Round 5 get_autocomplete None 체크 추가")

    # 체크 포인트 6: Round 6 get_related_keywords
    old_pattern6 = """        for kw in sa_keywords[:20]:
            related = self.collector.get_related_keywords(kw)
            for r in related:"""

    new_pattern6 = """        for kw in sa_keywords[:20]:
            related = self.collector.get_related_keywords(kw)
            if related is not None:  # None 방어
                for r in related:"""

    if old_pattern6 in content:
        # 들여쓰기 조정 필요
        content = content.replace(
            old_pattern6,
            """        for kw in sa_keywords[:20]:
            related = self.collector.get_related_keywords(kw)
            if related is not None:  # None 방어
                for r in related:"""
        )
        print("[6] Round 6 get_related_keywords None 체크 추가")

    # 체크 포인트 7: Extra rounds
    old_pattern7 = """            for kw in b_keywords[:20]:
                suggestions = self.collector.get_autocomplete(kw)
                extra_keywords.update(suggestions)"""

    new_pattern7 = """            for kw in b_keywords[:20]:
                suggestions = self.collector.get_autocomplete(kw)
                if suggestions is not None:  # None 방어
                    extra_keywords.update(suggestions)"""

    if old_pattern7 in content:
        content = content.replace(old_pattern7, new_pattern7)
        print("[7] Extra rounds get_autocomplete None 체크 추가")

    # 저장
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"\n✅ {file_path} 패치 완료")

if __name__ == "__main__":
    print("=" * 70)
    print("NoneType 에러 방어 코드 패치")
    print("=" * 70)
    fix_pathfinder_v3_legion()
    print("\n패치 완료! 기존 DB 데이터는 모두 보존되었습니다.")
