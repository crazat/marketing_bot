#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[4단계] Lead Manager CLI
리드 상태 관리 도구 - cafe_spy에서 수집한 리드의 상태를 관리합니다.

사용법:
    python lead_manager.py list --status New
    python lead_manager.py list --status New --source naver_cafe
    python lead_manager.py update 123 --status Reviewed --memo "검토완료"
    python lead_manager.py bulk-update 123,124,125 --status Responded
    python lead_manager.py stats
"""

import argparse
import sys
import os

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from db.database import DatabaseManager


def cmd_list(args):
    """리드 목록 조회."""
    db = DatabaseManager()
    leads = db.get_leads_by_status(
        status=args.status,
        source=args.source,
        limit=args.limit
    )

    if not leads:
        print(f"'{args.status}' 상태의 리드가 없습니다.")
        return

    print(f"\n📋 '{args.status}' 상태 리드 목록 ({len(leads)}건)")
    print("=" * 80)

    for lead in leads:
        memo_str = f" | 메모: {lead['memo']}" if lead['memo'] else ""
        print(f"[{lead['id']:>4}] {lead['title'][:50]}...")
        print(f"       소스: {lead['source']} | 날짜: {lead['date_posted']} | 스캔: {lead['scraped_at'][:10]}{memo_str}")
        print(f"       URL: {lead['url'][:60]}...")
        print("-" * 80)


def cmd_update(args):
    """단일 리드 상태 업데이트."""
    db = DatabaseManager()

    # 상태 유효성 검사
    if args.status not in db.LEAD_STATUS:
        print(f"❌ 유효하지 않은 상태: {args.status}")
        print(f"   유효한 상태: {', '.join(db.LEAD_STATUS)}")
        return

    db.update_status(args.id, args.status, args.memo)
    print(f"✅ 리드 #{args.id} 상태 업데이트: {args.status}")
    if args.memo:
        print(f"   메모: {args.memo}")


def cmd_bulk_update(args):
    """다수 리드 상태 일괄 업데이트."""
    db = DatabaseManager()

    # 상태 유효성 검사
    if args.status not in db.LEAD_STATUS:
        print(f"❌ 유효하지 않은 상태: {args.status}")
        print(f"   유효한 상태: {', '.join(db.LEAD_STATUS)}")
        return

    # ID 파싱
    try:
        ids = [int(x.strip()) for x in args.ids.split(',')]
    except ValueError:
        print("❌ 유효하지 않은 ID 형식. 예: 123,124,125")
        return

    updated = db.bulk_update_status(ids, args.status, args.memo)
    print(f"✅ {updated}건 리드 상태 업데이트 완료: {args.status}")


def cmd_stats(args):
    """리드 통계 조회."""
    db = DatabaseManager()
    stats = db.get_lead_stats()

    if not stats:
        print("❌ 통계 조회 실패")
        return

    print("\n📊 리드 통계")
    print("=" * 50)
    print(f"총 리드 수: {stats.get('total', 0)}")
    print(f"오늘 수집: {stats.get('today_collected', 0)}")
    print()

    print("📋 상태별 분포:")
    status_order = ['New', 'Reviewed', 'Responded', 'Converted', 'Closed']
    for status in status_order:
        count = stats.get(status, 0)
        if count > 0:
            bar = "█" * min(count // 2, 30)
            print(f"  {status:12} | {count:>5} | {bar}")

    # Unknown 상태도 표시
    unknown = stats.get('Unknown', 0)
    if unknown > 0:
        print(f"  {'Unknown':12} | {unknown:>5}")

    print()
    print("📍 소스별 분포:")
    by_source = stats.get('by_source', {})
    for source, count in sorted(by_source.items(), key=lambda x: -x[1]):
        print(f"  {source:20} | {count:>5}")

    # 전환율 계산
    total = stats.get('total', 0)
    if total > 0:
        reviewed = stats.get('Reviewed', 0) + stats.get('Responded', 0) + stats.get('Converted', 0) + stats.get('Closed', 0)
        responded = stats.get('Responded', 0) + stats.get('Converted', 0)
        converted = stats.get('Converted', 0)

        print()
        print("📈 퍼널 분석:")
        print(f"  검토율:   {reviewed/total*100:.1f}% ({reviewed}/{total})")
        print(f"  응답률:   {responded/total*100:.1f}% ({responded}/{total})")
        print(f"  전환율:   {converted/total*100:.1f}% ({converted}/{total})")


def main():
    parser = argparse.ArgumentParser(
        description="Lead Manager CLI - 리드 상태 관리 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='명령어')

    # list 명령어
    list_parser = subparsers.add_parser('list', help='리드 목록 조회')
    list_parser.add_argument('--status', type=str, default='New',
                             help='조회할 상태 (New/Reviewed/Responded/Converted/Closed)')
    list_parser.add_argument('--source', type=str, default=None,
                             help='소스 필터 (예: naver_cafe)')
    list_parser.add_argument('--limit', type=int, default=50,
                             help='최대 조회 개수')

    # update 명령어
    update_parser = subparsers.add_parser('update', help='단일 리드 상태 업데이트')
    update_parser.add_argument('id', type=int, help='리드 ID')
    update_parser.add_argument('--status', type=str, required=True,
                               help='새 상태 (New/Reviewed/Responded/Converted/Closed)')
    update_parser.add_argument('--memo', type=str, default=None,
                               help='메모 추가')

    # bulk-update 명령어
    bulk_parser = subparsers.add_parser('bulk-update', help='다수 리드 상태 일괄 업데이트')
    bulk_parser.add_argument('ids', type=str, help='리드 ID 목록 (쉼표 구분, 예: 123,124,125)')
    bulk_parser.add_argument('--status', type=str, required=True,
                             help='새 상태')
    bulk_parser.add_argument('--memo', type=str, default=None,
                             help='메모 추가')

    # stats 명령어
    stats_parser = subparsers.add_parser('stats', help='리드 통계 조회')

    args = parser.parse_args()

    if args.command == 'list':
        cmd_list(args)
    elif args.command == 'update':
        cmd_update(args)
    elif args.command == 'bulk-update':
        cmd_bulk_update(args)
    elif args.command == 'stats':
        cmd_stats(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
