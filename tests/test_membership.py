# -*- coding: utf-8 -*-
"""커뮤니티 승인제 — 접견예약확인 인증, 게이트, 어드민 승인/반려, 새 회원 추가."""
from extensions import db
from models import User


MOJ_URL = "https://minwon.moj.go.kr/minwon/1999/subview.do"


def _fresh_user(app, email="fresh@example.com"):
    with app.app_context():
        u = User(email=email, phone="010-1", role="user", status="active")
        u.set_password("user-1234")
        db.session.add(u)
        db.session.commit()
        return u.id


class TestGate:
    def test_anonymous_redirected_to_login(self, client):
        for path in ("/community/", "/community/board/facility"):
            r = client.get(path, follow_redirects=False)
            assert r.status_code == 302 and "/login" in r.headers["Location"], path

    def test_unapproved_user_sees_locked(self, client, login_as):
        login_as("user5@example.com")  # 시드: 미승인
        r = client.get("/community/", follow_redirects=False)
        assert r.status_code == 302 and "/community/locked" in r.headers["Location"]
        html = client.get("/community/locked").get_data(as_text=True)
        assert "인증이 필요해요" in html and MOJ_URL in html
        assert "visit-proof-sample.png" in html  # 참고 캡처 예시

    def test_unapproved_cannot_write_or_comment(self, app, client, login_as):
        from models import CommunityPost

        login_as("user5@example.com")
        assert client.get("/community/write", follow_redirects=False).status_code == 302
        with app.app_context():
            pid = CommunityPost.query.filter_by(status="open").first().id
        r = client.post(f"/community/{pid}/comments", data={"content": "x"},
                        follow_redirects=False)
        assert r.status_code == 302 and "locked" in r.headers["Location"]
        r = client.post(f"/api/community/posts/{pid}/like")
        assert r.status_code == 403

    def test_approved_user_passes(self, client, login_as):
        login_as("user1@example.com")  # 시드: 승인됨
        assert client.get("/community/").status_code == 200

    def test_lawyer_and_admin_pass(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        assert client.get("/community/").status_code == 200
        login_as("admin@angimo.kr")
        assert client.get("/community/").status_code == 200

    def test_sitemap_excludes_community(self, client):
        xml = client.get("/sitemap.xml").get_data(as_text=True)
        assert "/community" not in xml


class TestProofSubmit:
    def test_signup_page_has_guide(self, client):
        html = client.get("/signup").get_data(as_text=True)
        assert MOJ_URL in html and "visit-proof-sample.png" in html
        assert 'name="visit_proof"' in html

    def test_signup_with_proof_starts_pending(self, app, client, sample_file):
        r = client.post("/signup", data={
            "email": "newfam@example.com", "password": "pw-123456",
            "password2": "pw-123456", "phone": "010-2222-3333",
            "visit_proof": sample_file("proof.png"),
        }, content_type="multipart/form-data", follow_redirects=False)
        assert r.status_code == 302
        with app.app_context():
            u = User.query.filter_by(email="newfam@example.com").first()
            assert u.visit_proof_at is not None and u.approved_at is None
            assert u.visit_proof_url.startswith(f"visit-proof/{u.id}/")

    def test_signup_without_proof_ok(self, app, client):
        r = client.post("/signup", data={
            "email": "later@example.com", "password": "pw-123456",
            "password2": "pw-123456", "phone": "010-3333-4444",
        }, follow_redirects=False)
        assert r.status_code == 302
        with app.app_context():
            u = User.query.filter_by(email="later@example.com").first()
            assert u.visit_proof_at is None and u.approved_at is None

    def test_submit_from_locked_page(self, app, client, login_as, sample_file):
        login_as("user5@example.com")
        r = client.post("/mypage/visit-proof", data={
            "visit_proof": sample_file("proof.jpg"), "next": "/community/locked",
        }, content_type="multipart/form-data", follow_redirects=True)
        assert "접수되었습니다" in r.get_data(as_text=True)
        # 제출 후 locked 페이지는 승인 대기 안내로 전환
        html = client.get("/community/locked").get_data(as_text=True)
        assert "승인을 기다리고" in html

    def test_bad_extension_rejected(self, app, client, login_as, sample_file):
        login_as("user5@example.com")
        r = client.post("/mypage/visit-proof", data={
            "visit_proof": sample_file("x.gif", b"GIF89a"),
        }, content_type="multipart/form-data", follow_redirects=True)
        assert "jpg, png" in r.get_data(as_text=True)


class TestAdminApproval:
    def _submit(self, app, client, login_as, sample_file, email="user5@example.com"):
        uid = login_as(email)
        client.post("/mypage/visit-proof", data={"visit_proof": sample_file("p.png")},
                    content_type="multipart/form-data")
        return uid

    def test_pending_tab_and_approve(self, app, client, login_as, sample_file):
        uid = self._submit(app, client, login_as, sample_file)
        login_as("admin@angimo.kr")
        html = client.get("/admin/users?status=approval").get_data(as_text=True)
        assert "user5@example.com" in html and f"/admin/visit-proof/{uid}" in html
        client.post(f"/admin/users/{uid}/approve")
        with app.app_context():
            assert db.session.get(User, uid).approved_at is not None
        # 승인 후 회원이 커뮤니티 접근 가능
        login_as("user5@example.com")
        assert client.get("/community/").status_code == 200

    def test_reject_shows_reason(self, app, client, login_as, sample_file):
        uid = self._submit(app, client, login_as, sample_file)
        login_as("admin@angimo.kr")
        client.post(f"/admin/users/{uid}/reject-approval", data={"reason": "화면이 잘렸습니다"})
        login_as("user5@example.com")
        html = client.get("/community/locked").get_data(as_text=True)
        assert "반려" in html and "화면이 잘렸습니다" in html

    def test_proof_file_admin_only(self, app, client, login_as, sample_file):
        uid = self._submit(app, client, login_as, sample_file)
        # 본인/비회원도 접근 불가 (admin 전용 서빙)
        assert client.get(f"/admin/visit-proof/{uid}").status_code == 403
        client.get("/logout")
        assert client.get(f"/admin/visit-proof/{uid}", follow_redirects=False).status_code == 302
        login_as("admin@angimo.kr")
        assert client.get(f"/admin/visit-proof/{uid}").status_code == 200


class TestAdminUserCreate:
    def test_create_with_instant_approval(self, app, client, login_as):
        login_as("admin@angimo.kr")
        r = client.post("/admin/users/new", data={
            "email": "made@example.com", "password": "pw-123456",
            "name": "수기등록", "nickname": "수기닉", "phone": "010-9999-0000",
            "approve_now": "1"})
        assert r.status_code == 302
        with app.app_context():
            u = User.query.filter_by(email="made@example.com").first()
            assert u.status == "active" and u.approved_at is not None
        # 생성 계정으로 즉시 커뮤니티 이용 가능
        login_as("made@example.com")
        assert client.get("/community/").status_code == 200

    def test_create_without_approval(self, app, client, login_as):
        login_as("admin@angimo.kr")
        client.post("/admin/users/new", data={
            "email": "made2@example.com", "password": "pw-123456", "approve_now": "0"})
        with app.app_context():
            u = User.query.filter_by(email="made2@example.com").first()
            assert u is not None and u.approved_at is None

    def test_duplicate_email_rejected(self, app, client, login_as):
        login_as("admin@angimo.kr")
        r = client.post("/admin/users/new", data={
            "email": "user1@example.com", "password": "pw-123456", "approve_now": "1"},
            follow_redirects=True)
        assert "이미 가입된 이메일" in r.get_data(as_text=True)

    def test_non_admin_blocked(self, client, login_as):
        login_as("user1@example.com")
        assert client.get("/admin/users/new").status_code == 403
