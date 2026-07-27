# -*- coding: utf-8 -*-
"""마이페이지 — 내 활동/정보 수정/비번 변경/탈퇴."""
from extensions import db
from models import User


def test_requires_login(client):
    for path in ("/mypage/",):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
    for path in ("/mypage/update", "/mypage/password", "/mypage/withdraw"):
        assert client.post(path, follow_redirects=False).status_code == 302


def test_home_sections(client, login_as):
    login_as("user1@example.com")
    html = client.get("/mypage/").get_data(as_text=True)
    assert "상담" in html and "커뮤니티" in html


def test_update_info(app, client, login_as):
    login_as("user4@example.com")
    r = client.post("/mypage/update", data={"name": "새이름", "phone": "010-7777-8888"},
                    follow_redirects=True)
    assert "회원 정보가 수정되었습니다" in r.get_data(as_text=True)
    with app.app_context():
        u = User.query.filter_by(email="user4@example.com").first()
        assert u.name == "새이름" and u.phone == "010-7777-8888"


def test_password_wrong_current(client, login_as):
    login_as("user4@example.com")
    r = client.post("/mypage/password",
                    data={"current_password": "wrong", "new_password": "newpw-12345"},
                    follow_redirects=True)
    assert "현재 비밀번호가 올바르지 않습니다" in r.get_data(as_text=True)


def test_password_too_short(client, login_as):
    login_as("user4@example.com")
    r = client.post("/mypage/password",
                    data={"current_password": "user-1234", "new_password": "short"},
                    follow_redirects=True)
    assert "8자 이상" in r.get_data(as_text=True)


def test_password_change_success(app, client, login_as):
    login_as("user4@example.com")
    client.post("/mypage/password",
                data={"current_password": "user-1234", "new_password": "newpw-12345"})
    client.get("/logout")
    r = client.post("/login", data={"email": "user4@example.com", "password": "newpw-12345"},
                    follow_redirects=False)
    assert r.status_code == 302 and "/login" not in (r.headers.get("Location") or "")


def test_withdraw_wrong_password(client, login_as):
    login_as("user5@example.com")
    r = client.post("/mypage/withdraw", data={"password": "wrong"}, follow_redirects=True)
    assert "비밀번호가 올바르지 않습니다" in r.get_data(as_text=True)


def test_withdraw_success_blocks_login(app, client, login_as):
    login_as("user5@example.com")
    client.post("/mypage/withdraw", data={"password": "user-1234"})
    with app.app_context():
        u = User.query.filter_by(email="user5@example.com").first()
        assert u.status == "withdrawn" and u.deleted_at is not None
    # 세션 종료 + 재로그인 차단
    assert client.get("/mypage/", follow_redirects=False).status_code == 302
    r = client.post("/login", data={"email": "user5@example.com", "password": "user-1234"})
    assert "올바르지 않습니다" in r.get_data(as_text=True)
