# -*- coding: utf-8 -*-
"""점검(프리즈) 모드 — 어드민 토글 / 방문자 화면 비활성 / 서버 쓰기 차단."""
import pytest

from extensions import db
from models import CommunityPost, SiteSetting

ADMIN = "admin@angimo.kr"


def _set_freeze(app, on, msg=""):
    with app.app_context():
        for k, v in (("freeze_mode", "1" if on else "0"), ("freeze_message", msg)):
            row = db.session.get(SiteSetting, k)
            if row is None:
                db.session.add(SiteSetting(key=k, value=v))
            else:
                row.value = v
        db.session.commit()


class TestAdminToggle:
    def test_page_opens_and_toggles(self, app, client, login_as):
        login_as(ADMIN)
        assert client.get("/admin/settings").status_code == 200
        r = client.post("/admin/settings", data={
            "freeze_mode": "1", "freeze_message": "잠시 점검 중이에요"},
            follow_redirects=True)
        assert "점검 모드를 켰습니다" in r.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(SiteSetting, "freeze_mode").value == "1"
        r = client.post("/admin/settings", data={"freeze_mode": "0"},
                        follow_redirects=True)
        assert "해제했습니다" in r.get_data(as_text=True)

    def test_requires_admin(self, client, login_as):
        assert client.get("/admin/settings", follow_redirects=False).status_code == 302
        login_as("user1@example.com")
        assert client.get("/admin/settings").status_code == 403

    def test_action_logged(self, app, client, login_as):
        from models import AdminLog

        login_as(ADMIN)
        client.post("/admin/settings", data={"freeze_mode": "1"})
        with app.app_context():
            assert AdminLog.query.filter_by(action="site_freeze").first() is not None


class TestVisitorFrozen:
    def test_screen_disabled_and_notice(self, app, client, login_as):
        _set_freeze(app, True, "잠시 점검 중이에요")
        login_as("user1@example.com")
        html = client.get("/lawyers/").get_data(as_text=True)
        assert '<body class="frozen">' in html      # 클릭·링크 전부 무반응
        assert "잠시 점검 중이에요" in html          # 상단 안내 문구
        # base 미상속인 변호사 프로필도 동일 적용
        from models import LawyerProfile
        with app.app_context():
            uid = LawyerProfile.query.first().user_id
        detail = client.get(f"/lawyers/{uid}", follow_redirects=True).get_data(as_text=True)
        assert '<body class="frozen">' in detail

    def test_writes_blocked(self, app, client, login_as):
        """화면을 우회해 직접 POST해도 서버가 막는다."""
        _set_freeze(app, True)
        login_as("user1@example.com")
        with app.app_context():
            before = CommunityPost.query.count()
        r = client.post("/community/write", data={
            "category": "자유게시판", "title": "프리즈 중 글", "content": "본문"},
            follow_redirects=False)
        assert r.status_code == 302  # 저장되지 않고 되돌림
        with app.app_context():
            assert CommunityPost.query.count() == before
        # API도 503 + 에러 규약
        pid = 1
        r = client.post(f"/api/community/posts/{pid}/like")
        assert r.status_code == 503
        assert r.get_json()["error"]["code"] == "SERVICE_FROZEN"

    def test_reading_still_works(self, app, client, login_as):
        _set_freeze(app, True)
        login_as("user1@example.com")
        for path in ("/", "/lawyers/", "/counsel/", "/community/"):
            assert client.get(path).status_code == 200, path


class TestAdminUnaffected:
    def test_admin_can_still_use_and_unfreeze(self, app, client, login_as):
        _set_freeze(app, True)
        login_as(ADMIN)
        html = client.get("/").get_data(as_text=True)
        assert '<body class="frozen">' not in html   # 관리자는 정상 이용
        assert "점검 모드가 켜져 있습니다" in html     # 대신 안내 띠
        # 관리자 쓰기도 막히지 않음 → 여기서 해제 가능
        r = client.post("/admin/settings", data={"freeze_mode": "0"},
                        follow_redirects=True)
        assert "해제했습니다" in r.get_data(as_text=True)


class TestOffByDefault:
    def test_no_freeze_markup_when_off(self, app, client, login_as):
        _set_freeze(app, False)
        login_as("user1@example.com")
        html = client.get("/").get_data(as_text=True)
        assert "freeze-bar" not in html and 'class="frozen"' not in html
        # 쓰기도 정상
        assert client.post("/api/community/posts/999999/like").status_code == 404


class TestDoorsStayOpen:
    """점검 중에도 출입문(로그인 화면)은 살아 있어야 한다 — 특히 관리자."""

    def test_admin_login_not_frozen(self, app, client):
        _set_freeze(app, True)
        html = client.get("/admin/login").get_data(as_text=True)
        assert 'class="frozen"' not in html  # 비밀번호를 입력할 수 있어야 함

    def test_member_can_log_in_and_out(self, app, client):
        _set_freeze(app, True)
        r = client.post("/login", data={
            "email": "user1@example.com", "password": "user-1234"},
            follow_redirects=False)
        assert r.status_code == 302
        with client.session_transaction() as sess:
            assert sess.get("user_id")  # 로그인 자체는 막히지 않는다
        assert client.get("/logout", follow_redirects=False).status_code == 302
