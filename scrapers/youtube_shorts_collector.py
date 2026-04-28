"""[External Signals R3-2] YouTube 자동완성 + Shorts 댓글 수집기.

목적:
  1. YouTube 자동완성 (suggestqueries.google.com) — 한국어 ko/KR 검색 키워드 발굴
  2. YouTube Data API v3 — 청주/한의/다이어트 등 키워드의 Shorts 댓글에서 잠재 리드 수집
     (videoDuration=short, regionCode=KR)

자동완성 → keyword_insights (source='youtube_autocomplete', grade='C')
댓글 → mentions (source='youtube', source_subtype='shorts_comment')

운영자 트리거 (cron 안 씀):
  python scrapers/youtube_shorts_collector.py --keyword "청주 한의원" --mode autocomplete
  python scrapers/youtube_shorts_collector.py --keyword "청주 다이어트 한약" --mode comments --top 20
  python scrapers/youtube_shorts_collector.py --keyword "청주 한의원" --mode both --dry-run

키: YOUTUBE_API_KEY (config/secrets.json) — 댓글 수집용. 자동완성은 키 불필요.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'marketing_bot_web', 'backend'))
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    from backend_utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
    logger = logging.getLogger(__name__)

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
SECRETS_PATH = os.path.join(ROOT_DIR, 'config', 'secrets.json')

YT_AUTOCOMPLETE_URL = "https://suggestqueries.google.com/complete/search"


def _load_secret(key: str) -> Optional[str]:
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get(key)
    except Exception:
        return os.environ.get(key)


def fetch_youtube_autocomplete(keyword: str, top: int = 20) -> List[str]:
    """YouTube 자동완성 (XML toolbar, ds=yt, hl=ko, gl=kr).

    XML 실패 시 firefox client JSON 폴백.
    """
    suggestions: List[str] = []
    # 1차: XML toolbar
    try:
        r = requests.get(YT_AUTOCOMPLETE_URL, params={
            'client': 'youtube', 'ds': 'yt', 'q': keyword,
            'hl': 'ko', 'gl': 'kr', 'output': 'toolbar',
        }, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200:
            try:
                root = ET.fromstring(r.text)
                for sug in root.findall('.//suggestion'):
                    val = sug.get('data')
                    if val and val != keyword and val not in suggestions:
                        suggestions.append(val)
                    if len(suggestions) >= top:
                        break
            except ET.ParseError:
                pass
    except Exception as e:
        logger.warning(f"[yt-autocomplete xml] {e}")

    # 2차: firefox client JSON (XML 실패 또는 0개일 때)
    if not suggestions:
        try:
            r = requests.get(YT_AUTOCOMPLETE_URL, params={
                'client': 'firefox', 'ds': 'yt', 'q': keyword,
                'hl': 'ko', 'gl': 'kr',
            }, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                try:
                    import json as _json
                    data = _json.loads(r.text)
                    if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
                        for s in data[1]:
                            if isinstance(s, str) and s != keyword and s not in suggestions:
                                # 한글/영문/숫자/공백만 통과 (이상한 token 차단)
                                if re.match(r'^[\w\s가-힣ㄱ-ㅎㅏ-ㅣ\-_.,!?]+$', s):
                                    suggestions.append(s)
                            if len(suggestions) >= top:
                                break
                except (ValueError, TypeError):
                    pass
        except Exception as e:
            logger.warning(f"[yt-autocomplete json] {e}")
    return suggestions[:top]


def get_youtube_client():
    """YouTubeAPIClient 또는 직접 build."""
    api_key = _load_secret('YOUTUBE_API_KEY') or os.environ.get('YOUTUBE_API_KEY')
    if not api_key:
        return None
    try:
        from googleapiclient.discovery import build
        return build('youtube', 'v3', developerKey=api_key)
    except Exception as e:
        logger.warning(f"[yt] client init 실패: {e}")
        return None


def search_shorts(youtube, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """Shorts 동영상 검색 (videoDuration=short)."""
    try:
        request = youtube.search().list(
            part='snippet',
            q=query,
            type='video',
            videoDuration='short',
            regionCode='KR',
            relevanceLanguage='ko',
            maxResults=min(max_results, 50),
        )
        response = request.execute()
        videos = []
        for item in response.get('items', []):
            vid = item['id'].get('videoId')
            if not vid:
                continue
            videos.append({
                'video_id': vid,
                'title': item['snippet'].get('title', ''),
                'channel': item['snippet'].get('channelTitle', ''),
                'published': item['snippet'].get('publishedAt', ''),
                'url': f"https://www.youtube.com/shorts/{vid}",
            })
        return videos
    except Exception as e:
        logger.warning(f"[yt-search] error: {e}")
        return []


def fetch_comments(youtube, video_id: str, max_results: int = 20) -> List[Dict[str, Any]]:
    """commentThreads.list — 동영상 상위 댓글."""
    try:
        request = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            maxResults=min(max_results, 100),
            order='relevance',
            textFormat='plainText',
        )
        response = request.execute()
        comments = []
        for item in response.get('items', []):
            sn = item['snippet']['topLevelComment']['snippet']
            comments.append({
                'author': sn.get('authorDisplayName'),
                'text': sn.get('textDisplay', ''),
                'like_count': sn.get('likeCount', 0),
                'published': sn.get('publishedAt', ''),
            })
        return comments
    except Exception as e:
        err = str(e).lower()
        if 'disabled' in err:
            return []
        logger.warning(f"[yt-comments] {video_id}: {e}")
        return []


def upsert_keyword(conn: sqlite3.Connection, kw: str, parent_kw: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT OR IGNORE INTO keyword_insights
                (keyword, source, grade, search_intent, region, category, memo, created_at)
            VALUES (?, 'youtube_autocomplete', 'C', 'informational', '청주', '자동완성', ?, CURRENT_TIMESTAMP)
            """,
            (kw, f'parent={parent_kw}'),
        )
        return cur.rowcount > 0
    except Exception as e:
        logger.warning(f"[upsert_keyword] {kw}: {e}")
        return False


def upsert_comment_lead(conn: sqlite3.Connection, comment: Dict[str, Any],
                        video: Dict[str, Any], keyword: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO mentions
                (target_name, keyword, source, source_subtype, source_module,
                 platform, title, content, author, url, date_posted, status, scraped_at, created_at)
            VALUES (?, ?, 'youtube', 'shorts_comment', 'youtube_shorts_collector',
                    'youtube', ?, ?, ?, ?, ?, 'New', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                video.get('title', '')[:100],
                keyword,
                video.get('title', '')[:200],
                (comment.get('text') or '')[:2000],
                comment.get('author'),
                video.get('url'),
                comment.get('published', '')[:10],
            ),
        )
        return cur.rowcount > 0
    except Exception as e:
        logger.warning(f"[upsert_comment_lead] {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--keyword', required=True, help='검색 키워드 (예: "청주 한의원")')
    parser.add_argument('--top', type=int, default=20, help='자동완성 최대 개수 / 댓글 / 영상')
    parser.add_argument('--mode', choices=['autocomplete', 'comments', 'both'], default='both')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print(f'[yt-shorts] keyword={args.keyword} mode={args.mode} top={args.top}')

    conn = sqlite3.connect(DB_PATH)
    try:
        # 1) 자동완성
        new_kw = 0
        if args.mode in ('autocomplete', 'both'):
            suggestions = fetch_youtube_autocomplete(args.keyword, top=args.top)
            print(f'  자동완성 {len(suggestions)}건')
            for s in suggestions[:5]:
                print(f'    - {s}')
            if len(suggestions) > 5:
                print(f'    ... 외 {len(suggestions) - 5}건')
            if not args.dry_run:
                for s in suggestions:
                    if upsert_keyword(conn, s, args.keyword):
                        new_kw += 1
                conn.commit()
                print(f'  신규 키워드 {new_kw}건 → keyword_insights 적재')

        # 2) Shorts 댓글
        if args.mode in ('comments', 'both'):
            yt = get_youtube_client()
            if not yt:
                print('  [yt] YOUTUBE_API_KEY 없음 — 댓글 수집 스킵')
                return 0
            videos = search_shorts(yt, args.keyword, max_results=min(args.top, 10))
            print(f'  Shorts 영상 {len(videos)}개 발견')
            total_comments = 0
            new_leads = 0
            for v in videos:
                comments = fetch_comments(yt, v['video_id'], max_results=args.top)
                total_comments += len(comments)
                if not args.dry_run:
                    for c in comments:
                        if upsert_comment_lead(conn, c, v, args.keyword):
                            new_leads += 1
                print(f'    {v["title"][:40]:<40} 댓글 {len(comments)}건')
            if not args.dry_run:
                conn.commit()
                print(f'\n  댓글 총 {total_comments}건, 신규 mentions {new_leads}건 적재')
            else:
                print(f'\n  [dry-run] 댓글 총 {total_comments}건 (적재 X)')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
