"""[R13] 의료광고심의 가이드북 PDF → sqlite-vec RAG 인덱스 빌드.

목적: 한방의료광고심의 2025 가이드북 + 금지표현 리스트를 RAG로 임베딩.
       Pathfinder 발굴 키워드/Viral 댓글에 자동 컴플라이언스 게이트.

전제:
  - 가이드북 PDF 다운로드: https://ad.akom.org/  (대한한의사협회 의료광고심의)
  - 파일 경로: data/medical_ad_guideline.pdf  (사용자가 직접 다운로드)
  - sqlite-vec + BGE-M3 (이미 services/rag/qa_search.py에 인프라 존재)

운영자 트리거:
  python scripts/build_medical_ad_index.py --pdf data/medical_ad_guideline.pdf
  python scripts/build_medical_ad_index.py --status      # 인덱스 상태만

이후 services/content_compliance.py가 자동 활용.
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import struct
import sys
from typing import Iterable

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'marketing_bot_web', 'backend'))
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
DEFAULT_PDF = os.path.join(ROOT_DIR, 'data', 'medical_ad_guideline.pdf')
EMBED_DIM = 1024  # BGE-M3 차원


def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    """문단 단위 청킹. 한국어 문장 끝 휴리스틱."""
    text = re.sub(r'\s+', ' ', text).strip()
    chunks = []
    i = 0
    while i < len(text):
        end = min(i + chunk_size, len(text))
        # 가능하면 문장 끝(., 다.)에서 잘라내기
        if end < len(text):
            for delim in ['다. ', '. ', '? ', '! ']:
                idx = text.rfind(delim, i, end)
                if idx != -1:
                    end = idx + len(delim)
                    break
        chunks.append(text[i:end].strip())
        i = max(end - overlap, i + 1)
    return [c for c in chunks if len(c) > 30]


def extract_pdf_text(pdf_path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise RuntimeError('pypdf 또는 PyPDF2 필요. pip install pypdf')
    reader = PdfReader(pdf_path)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or '')
    return '\n'.join(parts)


def get_embedder():
    """services/rag/qa_search 의 BGE-M3 모델 재사용."""
    from sentence_transformers import SentenceTransformer
    model_id = os.environ.get('MARKETING_BOT_EMBED_MODEL', 'BAAI/bge-m3')
    return SentenceTransformer(model_id)


def embed_to_blob(vec) -> bytes:
    return struct.pack(f'{len(vec)}f', *vec)


def ensure_table(conn: sqlite3.Connection) -> None:
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception as e:
        print(f'sqlite-vec load 실패: {e}')
        raise

    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS medical_ad_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT,
            chunk_text TEXT NOT NULL,
            source TEXT,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS medical_ad_vec USING vec0(
            chunk_id INTEGER PRIMARY KEY,
            embedding FLOAT[{EMBED_DIM}]
        );
    """)


def show_status() -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='medical_ad_chunks'")
    if not cur.fetchone():
        print('medical_ad_chunks 테이블 없음. 빌드 안 됨.')
        return 0
    n = cur.execute('SELECT COUNT(*) FROM medical_ad_chunks').fetchone()[0]
    last = cur.execute('SELECT MAX(indexed_at) FROM medical_ad_chunks').fetchone()[0]
    print(f'medical_ad_chunks: {n}건, 최종 색인 {last}')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--pdf', default=DEFAULT_PDF, help='가이드북 PDF 경로')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--rebuild', action='store_true', help='기존 인덱스 삭제 후 재빌드')
    args = parser.parse_args()

    if args.status:
        return show_status()

    if not os.path.exists(args.pdf):
        print(f'PDF 없음: {args.pdf}')
        print('1. https://ad.akom.org/ 에서 "한방의료광고심의 2025 가이드북" 다운로드')
        print(f'2. {args.pdf} 위치에 저장')
        print('3. python scripts/build_medical_ad_index.py 재실행')
        return 1

    print(f'PDF 로드: {args.pdf}')
    text = extract_pdf_text(args.pdf)
    print(f'추출 텍스트: {len(text):,}자')

    chunks = chunk_text(text)
    print(f'청크 {len(chunks)}개 생성')

    print('BGE-M3 임베딩 모델 로드 중...')
    embedder = get_embedder()

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    cur = conn.cursor()

    if args.rebuild:
        cur.execute('DELETE FROM medical_ad_chunks')
        cur.execute('DELETE FROM medical_ad_vec')

    print('임베딩 + 적재 중...')
    for i, chunk in enumerate(chunks):
        # 가이드북 섹션 추정 (첫 줄 또는 키워드)
        section = '가이드북'
        if '금지' in chunk[:80]:
            section = '금지 표현'
        elif '심의' in chunk[:80]:
            section = '심의 절차'

        cur.execute(
            "INSERT INTO medical_ad_chunks (section, chunk_text, source) VALUES (?, ?, ?)",
            (section, chunk, '한방의료광고심의 2025 가이드북'),
        )
        chunk_id = cur.lastrowid

        vec = embedder.encode(chunk, normalize_embeddings=True).tolist()
        cur.execute(
            "INSERT INTO medical_ad_vec (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, embed_to_blob(vec)),
        )

        if (i + 1) % 50 == 0:
            conn.commit()
            print(f'  진행: {i + 1}/{len(chunks)}')

    conn.commit()
    conn.close()

    print(f'\n완료: {len(chunks)}개 청크 인덱싱')
    print('이제 services/content_compliance.py가 자동 RAG 게이트 적용')
    return 0


if __name__ == '__main__':
    sys.exit(main())
