#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
엑셀 보고서에서 키워드 추출
"""

import pandas as pd
import sys
import os

# Windows 환경에서 UTF-8 출력 설정
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8')

def extract_keywords(file_path):
    """엑셀에서 키워드 추출"""

    all_keywords = set()

    try:
        # 작업보고서 시트 읽기
        print("[Reading Sheet: 작업보고서]")
        df = pd.read_excel(file_path, sheet_name='작업보고서', header=1)  # 2번째 행이 헤더

        print(f"Columns: {list(df.columns)}")
        print(f"\nFirst 15 rows:")
        print(df.head(15))

        # 키워드 컬럼 찾기
        for col in df.columns:
            if '키워드' in str(col):
                keywords = df[col].dropna().astype(str).tolist()
                keywords = [k.strip() for k in keywords if k.strip() and k != 'nan' and k != '키워드']
                all_keywords.update(keywords)
                print(f"\n[Column '{col}']: {len(keywords)} keywords")

        # 노출보고서 시트도 확인
        print("\n" + "="*70)
        print("[Reading Sheet: 노출보고서]")
        df2 = pd.read_excel(file_path, sheet_name='노출보고서')

        print(f"\nAll cell values (first 20 rows):")
        for idx, row in df2.head(20).iterrows():
            for col in df2.columns:
                val = row[col]
                if pd.notna(val) and str(val).strip():
                    # 키워드 패턴 찾기 (한글+숫자 조합)
                    val_str = str(val).strip()
                    if any(char.isalpha() for char in val_str) and len(val_str) > 2:
                        if '/' not in val_str and '블로그' not in val_str and 'http' not in val_str:
                            print(f"   [{idx},{col}]: {val_str}")

        print("\n" + "="*70)
        print(f"[Total Unique Keywords Extracted]: {len(all_keywords)}")

        # 청주 관련 키워드만 필터링
        cheongju_keywords = [kw for kw in all_keywords if '청주' in kw or '충주' in kw or '제천' in kw]
        print(f"[Cheongju Region Keywords]: {len(cheongju_keywords)}")

        # 카테고리별 분류
        categories = {
            '교통사고': [],
            '다이어트': [],
            '여드름': [],
            '탈모': [],
            '추나': [],
            '산후': [],
            '미백': [],
            '기타': []
        }

        for kw in sorted(all_keywords):
            categorized = False
            for cat_name, cat_keywords in categories.items():
                if cat_name in kw:
                    cat_keywords.append(kw)
                    categorized = True
                    break
            if not categorized:
                categories['기타'].append(kw)

        print("\n[Keywords by Category]:")
        for cat, kws in categories.items():
            if kws:
                print(f"\n{cat} ({len(kws)}):")
                for kw in kws[:10]:  # 각 카테고리에서 최대 10개만
                    print(f"   - {kw}")
                if len(kws) > 10:
                    print(f"   ... and {len(kws) - 10} more")

        # CSV로 저장
        output_file = "extracted_keywords_from_report.csv"
        with open(output_file, 'w', encoding='utf-8-sig') as f:
            f.write("keyword,category\n")
            for cat, kws in categories.items():
                for kw in kws:
                    f.write(f"{kw},{cat}\n")

        print(f"\n[Saved to]: {output_file}")

    except Exception as e:
        print(f"[ERROR]: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    file_path = r"C:\Users\craza\Downloads\보고서-규림청주-2025-9월말일.xlsx"
    extract_keywords(file_path)
