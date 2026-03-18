import sqlite3
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("DBRecovery")

CORRUPTED_DB = "db/marketing_data_corrupted_20260119_123548.db"
NEW_DB = "db/marketing_data.db"

# [Security] 허용된 테이블 화이트리스트
ALLOWED_TABLES = {
    'mentions', 'rank_history', 'insights', 'system_logs',
    'competitors', 'influencers', 'scan_history', 'chat_sessions',
    'chat_messages', 'daily_stats', 'competitor_reviews',
    'influencer_collaborations', 'sentinel_threats', 'keyword_insights'
}

def recover_data():
    """
    손상된 DB에서 데이터 복구

    Returns:
        bool: 복구 성공 여부
    """
    if not os.path.exists(CORRUPTED_DB):
        logger.error(f"Corrupted DB not found: {CORRUPTED_DB}")
        return False

    logger.info(f"Attempting recovery from {CORRUPTED_DB} to {NEW_DB}")

    conn_old = None
    conn_new = None

    try:
        conn_old = sqlite3.connect(CORRUPTED_DB)
        cursor_old = conn_old.cursor()

        conn_new = sqlite3.connect(NEW_DB)
        cursor_new = conn_new.cursor()

        # Get list of tables from NEW DB (to ensure schema compatibility)
        cursor_new.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor_new.fetchall() if row[0] != 'sqlite_sequence']

        total_recovered = 0
        total_failed = 0

        for table in tables:
            # [Security] 테이블명 화이트리스트 검증
            if table not in ALLOWED_TABLES:
                logger.warning(f"Skipping unknown table: {table}")
                continue

            logger.info(f"Recovering table: {table}")
            try:
                # Select * from old (테이블명이 화이트리스트에 있으므로 안전)
                cursor_old.execute(f"SELECT * FROM {table}")
                rows = cursor_old.fetchall()

                if not rows:
                    logger.info(f"  - No data in {table}")
                    continue

                # Get column count to create placeholders
                col_count = len(rows[0])
                placeholders = ','.join(['?'] * col_count)

                success_count = 0
                fail_count = 0

                for row in rows:
                    try:
                        cursor_new.execute(f"INSERT OR IGNORE INTO {table} VALUES ({placeholders})", row)
                        success_count += 1
                    except Exception as e:
                        fail_count += 1
                        # logger.warning(f"Failed to insert row in {table}: {e}")

                conn_new.commit()
                logger.info(f"  - Recovered {success_count} rows. Failed: {fail_count}")
                total_recovered += success_count
                total_failed += fail_count

            except sqlite3.DatabaseError as e:
                logger.error(f"  - Failed to read table {table} from corrupted DB: {e}")
            except Exception as e:
                logger.error(f"  - Unexpected error on table {table}: {e}")

        logger.info(f"Recovery process completed. Total: {total_recovered} recovered, {total_failed} failed.")
        return True

    except Exception as e:
        logger.critical(f"Critical failure during recovery: {e}")
        return False

    finally:
        # 항상 연결 닫기
        if conn_old:
            try:
                conn_old.close()
            except Exception:
                pass
        if conn_new:
            try:
                conn_new.close()
            except Exception:
                pass

if __name__ == "__main__":
    recover_data()
