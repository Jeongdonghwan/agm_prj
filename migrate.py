# -*- coding: utf-8 -*-
"""스키마 마이그레이션 — 기존 데이터를 보존한 채 컬럼만 추가한다.

seed.py는 drop_all로 전체를 지우므로 운영/개발 데이터가 있으면 절대 쓰지 말고,
모델에 컬럼이 늘어날 때마다 여기에 한 줄 등록한 뒤 이 스크립트를 실행한다.

    python migrate.py

여러 번 실행해도 안전하다(이미 있는 컬럼은 건너뜀).
"""
import sys

from sqlalchemy import text

from app import create_app
from extensions import db

# (테이블, 컬럼, 정의) — 추가만 한다. 삭제/변경은 수동 검토 후 별도 처리.
MIGRATIONS = [
    ("lawyer_profiles", "show_in_new", "TINYINT(1) DEFAULT 1"),
    ("lawyer_profiles", "show_in_ad", "TINYINT(1) DEFAULT 0"),
    ("lawyer_profiles", "show_in_adlist", "TINYINT(1) DEFAULT 0"),
    ("community_posts", "attachments", "JSON NULL"),
]

# 데이터 보정 — 여러 번 실행해도 결과가 같아야 한다. (설명, SQL)
DATA_FIXES = [
    (
        "사이드 배너의 옛 아이콘 참조 제거(기본 일러스트로 복귀)",
        "UPDATE banners SET image_url = NULL "
        "WHERE position = 'main_side' AND image_url LIKE '/static/icons/%'",
    ),
]


def _column_exists(table, column):
    row = db.session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() AND table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    ).scalar()
    return bool(row)


def _table_exists(table):
    row = db.session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = :t"
        ),
        {"t": table},
    ).scalar()
    return bool(row)


def run():
    app = create_app()
    with app.app_context():
        print(f"[migrate] DB: {app.config['SQLALCHEMY_DATABASE_URI'].rsplit('/', 1)[-1]}")
        applied = skipped = 0
        for table, column, ddl in MIGRATIONS:
            if not _table_exists(table):
                print(f"  ! {table} 테이블 없음 — 건너뜀 (최초 설치는 seed.py 사용)")
                continue
            if _column_exists(table, column):
                skipped += 1
                continue
            db.session.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {ddl}"))
            db.session.commit()
            print(f"  + {table}.{column} 추가")
            applied += 1

        for label, sql in DATA_FIXES:
            result = db.session.execute(text(sql))
            db.session.commit()
            if result.rowcount:
                print(f"  * {label} — {result.rowcount}건")
                applied += 1

        print(f"[migrate] 적용 {applied}건 / 이미 반영 {skipped}건 — 데이터는 보존됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
