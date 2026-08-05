# -*- coding: utf-8 -*-
"""관리자 2단계 — 메인관리자 전권 / 부관리자는 허용 메뉴만."""
from extensions import db
from models import User

MAIN = "admin@angimo.kr"


def _make_sub(client, login_as, perms=("cases", "news"), email="sub@angimo.kr"):
    login_as(MAIN)
    data = {"email": email, "password": "sub-12345678", "name": "부관리자1"}
    for k in perms:
        data[f"perm_{k}"] = "1"
    r = client.post("/admin/admins/new", data=data)
    assert r.status_code == 302
    return email


class TestSubAdmin:
    def test_create_and_login(self, app, client, login_as):
        email = _make_sub(client, login_as)
        with app.app_context():
            u = User.query.filter_by(email=email).first()
            assert u.role == "admin" and not u.is_super_admin
            assert u.admin_perms == ["cases", "news"]
        # 부관리자 로그인 (/admin/login 공용)
        client.get("/logout")
        r = client.post("/admin/login", data={"email": email, "password": "sub-12345678"},
                        follow_redirects=False)
        assert r.status_code == 302 and "/admin" in r.headers["Location"]

    def test_allowed_menus_only(self, client, login_as):
        email = _make_sub(client, login_as)
        login_as(email)
        # 허용 메뉴는 200
        assert client.get("/admin/cases").status_code == 200
        assert client.get("/admin/news").status_code == 200
        assert client.get("/admin/").status_code == 200  # 대시보드 공통
        # 미허용 메뉴는 403 (열람·쓰기 모두)
        for path in ("/admin/users", "/admin/banners", "/admin/community",
                     "/admin/boards", "/admin/logs", "/admin/lawyer-ads"):
            assert client.get(path).status_code == 403, path
        assert client.post("/admin/users/new", data={}).status_code == 403

    def test_sidebar_hides_forbidden(self, client, login_as):
        email = _make_sub(client, login_as)
        login_as(email)
        client.get("/admin/")  # flash 소진
        html = client.get("/admin/").get_data(as_text=True)
        assert "판례돋보기" in html and "안기모뉴스" in html
        assert "회원 관리" not in html and "배너 관리" not in html
        assert "관리자 계정" not in html  # 메인 전용 메뉴
        assert "부관리자" in html  # 역할 태그

    def test_admins_menu_super_only(self, client, login_as):
        email = _make_sub(client, login_as)
        login_as(email)
        assert client.get("/admin/admins").status_code == 403
        assert client.post("/admin/admins/new", data={}).status_code == 403
        login_as(MAIN)
        html = client.get("/admin/admins").get_data(as_text=True)
        assert email in html and "메인" in html

    def test_edit_perms(self, app, client, login_as):
        email = _make_sub(client, login_as)
        with app.app_context():
            uid = User.query.filter_by(email=email).first().id
        client.post(f"/admin/admins/{uid}/edit", data={"perm_users": "1", "perm_reports": "1"})
        with app.app_context():
            assert set(db.session.get(User, uid).admin_perms) == {"users", "reports"}
        login_as(email)
        assert client.get("/admin/users").status_code == 200
        assert client.get("/admin/cases").status_code == 403  # 회수된 권한

    def test_suspend_blocks_login(self, app, client, login_as):
        email = _make_sub(client, login_as)
        with app.app_context():
            uid = User.query.filter_by(email=email).first().id
        client.post(f"/admin/admins/{uid}/toggle")
        client.get("/logout")
        r = client.post("/admin/login", data={"email": email, "password": "sub-12345678"})
        assert "정지된 계정" in r.get_data(as_text=True)

    def test_main_admin_protected(self, app, client, login_as):
        login_as(MAIN)
        with app.app_context():
            mid = User.query.filter_by(email=MAIN).first().id
        client.post(f"/admin/admins/{mid}/toggle", follow_redirects=False)
        with app.app_context():
            assert db.session.get(User, mid).status == "active"  # 정지 불가

    def test_no_perms_rejected(self, app, client, login_as):
        login_as(MAIN)
        r = client.post("/admin/admins/new", data={
            "email": "nop@angimo.kr", "password": "sub-12345678"}, follow_redirects=True)
        assert "1개 이상 선택" in r.get_data(as_text=True)
        with app.app_context():
            assert User.query.filter_by(email="nop@angimo.kr").count() == 0

    def test_main_admin_sees_everything(self, client, login_as):
        login_as(MAIN)
        html = client.get("/admin/").get_data(as_text=True)
        assert "관리자 계정" in html and "총관리자" in html
        assert client.get("/admin/users").status_code == 200
