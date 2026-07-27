# -*- coding: utf-8 -*-
"""공용 픽스처 — 테스트 DB angimo_test + 세션 1회 시드 + 테스트별 트랜잭션 롤백 격리.

격리 원리: 뷰가 db.session.commit()을 직접 호출하므로, 테스트마다 db.engines의
Engine을 외부 트랜잭션이 열린 Connection으로 스왑하고 세션을 SAVEPOINT 조인
모드로 두면 commit이 SAVEPOINT까지만 반영되고 teardown의 rollback으로 전부 취소된다.
(Flask-SQLAlchemy 3.1의 Session.get_bind()는 sessionmaker(bind=)를 무시하고
db.engines[None]을 참조하므로 engines dict 스왑이 유일하게 동작하는 방법.)
"""
import io
import sys

import bcrypt
import pymysql
import pytest

# bcrypt rounds=4 — 시드 16계정 해싱 수 초 → 즉시. models/user.py가 호출 시점에
# bcrypt.gensalt를 참조하므로 모듈 속성 패치가 set_password에 그대로 전파된다.
_orig_gensalt = bcrypt.gensalt
bcrypt.gensalt = lambda rounds=4, prefix=b"2b": _orig_gensalt(rounds=rounds, prefix=prefix)

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import Config  # noqa: E402


class TestConfig(Config):
    TESTING = True
    DB_NAME = "angimo_test"
    # 부모 URI는 클래스 본문 f-string으로 확정돼 있어 재정의 필수
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{Config.DB_USER}:{Config.DB_PASSWORD}"
        f"@{Config.DB_HOST}:{Config.DB_PORT}/angimo_test?charset=utf8mb4"
    )


def _ensure_test_database():
    # seed.ensure_database()는 Config.DB_NAME을 하드참조하므로 재사용 불가
    conn = pymysql.connect(
        host=TestConfig.DB_HOST, port=TestConfig.DB_PORT,
        user=TestConfig.DB_USER, password=TestConfig.DB_PASSWORD, charset="utf8mb4",
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE DATABASE IF NOT EXISTS `angimo_test` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    from app import create_app
    from extensions import db
    from seed import run_seed

    _ensure_test_database()
    app = create_app(TestConfig)
    app.config["UPLOAD_FOLDER"] = str(tmp_path_factory.mktemp("uploads"))

    # 뷰의 commit()/rollback()을 SAVEPOINT로 흡수. lawyer_admin의 실제 rollback()
    # 호출이 외부 트랜잭션을 죽이지 않도록 create_savepoint를 명시한다.
    db.session = db._make_scoped_session({"join_transaction_mode": "create_savepoint"})

    run_seed(app)  # drop_all + create_all + 시드 (angimo_test)
    yield app


@pytest.fixture(autouse=True)
def db_txn(app):
    """테스트마다 외부 트랜잭션을 열고 engines dict의 Engine을 Connection으로 스왑."""
    from extensions import db

    with app.app_context():
        engines = db.engines  # 내부 dict 그 자체 (살아있는 참조)
    cleanup = []
    for key, engine in list(engines.items()):
        conn = engine.connect()
        txn = conn.begin()
        engines[key] = conn
        cleanup.append((key, engine, conn, txn))

    yield

    with app.app_context():
        db.session.remove()
    for key, engine, conn, txn in cleanup:
        txn.rollback()
        conn.close()
        engines[key] = engine


@pytest.fixture(autouse=True)
def clear_cache(app):
    """SimpleCache 누수 차단 — cached_page(page:*)와 login_fail:* 카운터."""
    from extensions import cache

    with app.app_context():
        cache.clear()
    yield


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login_as(app, client):
    """login_as('user1@example.com') — 세션쿠키에 user_id 주입(before_request가 g.user 로드)."""
    def _login(email):
        from extensions import db
        from models import User

        with app.app_context():
            uid = db.session.query(User.id).filter_by(email=email).scalar()
            assert uid, f"seed에 없는 계정: {email}"
        with client.session_transaction() as sess:
            sess["user_id"] = uid
        return uid
    return _login


# 유효한 1x1 PNG (매직 바이트 포함)
PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def sample_file():
    """multipart 업로드용 튜플 생성 — data={'photo': sample_file('a.png')}"""
    def _make(name="test.png", content: bytes = PNG_1PX):
        return (io.BytesIO(content), name)
    return _make
