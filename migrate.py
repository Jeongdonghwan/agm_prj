# -*- coding: utf-8 -*-
"""스키마 마이그레이션 — 기존 데이터를 보존한 채 스키마만 맞춘다.

seed.py는 drop_all로 전체를 지우므로 운영/개발 데이터가 있으면 절대 쓰지 말고
이 스크립트를 쓴다. 하는 일:
  1) 새로 생긴 테이블 생성(db.create_all — 기존 테이블은 건드리지 않음)
  2) MIGRATIONS의 컬럼 추가(이미 있으면 건너뜀)
  3) DATA_FIXES의 데이터 보정(여러 번 실행해도 결과 동일)

    python migrate.py
"""
import sys

from sqlalchemy import text

from app import create_app
from extensions import db

# (테이블, 컬럼, 정의) — 추가만 한다. 삭제/변경은 수동 검토 후 별도 처리.
MIGRATIONS = [
    ("lawyer_profiles", "show_in_new", "TINYINT(1) DEFAULT 1"),
    ("community_posts", "attachments", "JSON NULL"),
]

# 데이터 보정 — (설명, SQL, 필요 컬럼(table, column) 또는 None).
# ⚠️ 반드시 "여러 번 실행해도 같은 결과"여야 한다. 특히 레코드를 새로 만드는 보정은
#    사용자가 지운 데이터를 되살릴 수 있으므로, 원본 조건을 함께 소거해 1회만 동작하게 한다.
DATA_FIXES = [
    (
        "사이드 배너의 옛 아이콘 참조 제거(기본 일러스트로 복귀)",
        "UPDATE banners SET image_url = NULL "
        "WHERE position = 'main_side' AND image_url LIKE '/static/icons/%'",
        None,
    ),
    (
        # 구 전역 플래그(show_in_ad/show_in_adlist) → lawyer_ads 이전은 완료됨.
        # 플래그를 해제해 두지 않으면 관리자가 지운 광고가 migrate 때마다 되살아난다.
        "구 광고 플래그 해제(삭제한 광고가 되살아나지 않도록)",
        "UPDATE lawyer_profiles SET show_in_ad = 0, show_in_adlist = 0 "
        "WHERE show_in_ad = 1 OR show_in_adlist = 1",
        ("lawyer_profiles", "show_in_ad"),
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

        # 새로 생긴 테이블만 생성(기존 테이블·데이터는 그대로)
        import models  # noqa: F401 — 모델 등록 보장

        before = set(db.inspect(db.engine).get_table_names())
        db.create_all()
        for t in sorted(set(db.inspect(db.engine).get_table_names()) - before):
            print(f"  + {t} 테이블 생성")
            applied += 1
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

        for label, sql, requires in DATA_FIXES:
            if requires and not _column_exists(*requires):
                continue  # 해당 컬럼이 없는 DB(신규 설치)에는 적용할 것이 없음
            result = db.session.execute(text(sql))
            db.session.commit()
            if result.rowcount:
                print(f"  * {label} — {result.rowcount}건")
                applied += 1

        # 커뮤니티 게시판 트리 — 테이블이 비어 있을 때만 초기 시드(재실행 안전)
        from board_seed import seed_boards

        n = seed_boards(db)
        if n:
            print(f"  * 커뮤니티 게시판 초기 시드 — {n}건")
            applied += 1

        print(f"[migrate] 적용 {applied}건 / 이미 반영 {skipped}건 — 데이터는 보존됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
