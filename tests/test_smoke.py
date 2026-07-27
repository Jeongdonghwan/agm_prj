# -*- coding: utf-8 -*-
"""픽스처 동작 확인 — 앱 기동, 시드, 트랜잭션 격리."""
from extensions import db
from models import User


def test_index_200(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "안기모" in r.get_data(as_text=True)


def test_login_fixture(client, login_as):
    login_as("user1@example.com")
    r = client.get("/mypage/")
    assert r.status_code == 200


def test_isolation_write(app, client, login_as):
    """이 테스트가 커밋한 데이터는 다음 테스트에서 보이면 안 된다."""
    login_as("user1@example.com")
    r = client.post(
        "/counsel/write",
        data={"title": "격리 검증 질문", "content": "본문", "category_id": "1", "is_public": "1"},
        follow_redirects=True,
    )
    assert "격리 검증 질문" in r.get_data(as_text=True)


def test_isolation_rolled_back(app):
    from models import Consultation

    with app.app_context():
        cnt = Consultation.query.filter_by(title="격리 검증 질문").count()
    assert cnt == 0


def test_seed_accounts(app):
    with app.app_context():
        assert User.query.filter_by(email="admin@angimo.kr").first().role == "admin"
        assert User.query.filter_by(role="lawyer").count() == 10
