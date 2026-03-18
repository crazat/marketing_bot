#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
엑셀 보고서 분석 스크립트
"""

import pandas as pd
import sys
import os

# Windows 환경에서 UTF-8 출력 설정
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8')

def analyze_excel(file_path):
    """엑셀 파일 분석"""

    try:
        # 모든 시트 이름 확인
        xl_file = pd.ExcelFile(file_path)
        print("[Excel Sheet List]")
        for i, sheet in enumerate(xl_file.sheet_names):
            print(f"   {i+1}. {sheet}")

        print("\n" + "="*70)

        # 각 시트 상세 분석
        for sheet_name in xl_file.sheet_names:
            print(f"\n[Sheet: {sheet_name}]")
            print("="*70)

            df = pd.read_excel(file_path, sheet_name=sheet_name)

            print(f"   Size: {df.shape[0]} rows x {df.shape[1]} columns")
            print(f"   Columns: {list(df.columns)}")

            # 빈 행 제거
            df = df.dropna(how='all')

            if len(df) > 0:
                print(f"\n   [Preview - Top 10 rows]")
                print(df.head(10).to_string(index=False, max_colwidth=50))

                # 키워드 관련 컬럼 찾기
                keyword_cols = [col for col in df.columns if '키워드' in str(col) or 'keyword' in str(col).lower()]
                if keyword_cols:
                    print(f"\n   [Keyword Columns Found]: {keyword_cols}")

                    # 키워드 추출
                    keywords = []
                    for col in keyword_cols:
                        keywords.extend(df[col].dropna().astype(str).tolist())

                    # 중복 제거
                    keywords = list(set([k.strip() for k in keywords if k.strip() and k != 'nan']))
                    print(f"   [Total Keywords]: {len(keywords)}")

                    if len(keywords) > 0:
                        print(f"\n   [Sample Keywords - First 20]:")
                        for i, kw in enumerate(keywords[:20], 1):
                            print(f"      {i}. {kw}")

                # 검색량, 순위 관련 컬럼 찾기
                volume_cols = [col for col in df.columns if '검색' in str(col) or '순위' in str(col) or '노출' in str(col)]
                if volume_cols:
                    print(f"\n   [Metric Columns Found]: {volume_cols}")

            print("")

    except Exception as e:
        print(f"[ERROR]: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    file_path = r"C:\Users\craza\Downloads\보고서-규림청주-2025-9월말일.xlsx"
    analyze_excel(file_path)
