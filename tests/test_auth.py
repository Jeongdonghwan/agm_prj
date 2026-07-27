# -*- coding: utf-8 -*-
"""인증 — 가입 2종, 로그인/잠금, 역할별 리다이렉트, 로그아웃."""
import os

from extensions import cache, db
from models import LawyerProfile, LawyerVerificationFile, User

USER_PW = "user-1234"


def _make_user(app, email, password="pw-12345678", **kw):
    with app.app_context():
        u = User(email=email, phone="010-0000-0000", role=kw.pop("role", "user"),
                 status=kw.pop("status", "active"), **kw)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u.id


# ─────────────────────────── 일반 가입 ───────────────────────────
class TestSignup:
    def test_success_active_and_autologin(self, app, client):
        r = client.post("/signup", data={
            "email": "newbie@example.com", "password": "pw-12345678",
            "password2": "pw-12345678", "phone": "010-1111-2222",
        }, follow_redirects=False)
        assert r.status_code == 302
        with app.app_context():
            u = User.query.filter_by(email="newbie@example.com").first()
            assert u.role == "user" and u.status == "active"
        # 가입 직후 자동 로그인 상태
        assert client.get("/mypage/").status_code == 200

    def test_duplicate_email(self, client):
        r = client.post("/signup", data={
            "email": "user1@example.com", "password": "pw-12345678",
            "password2": "pw-12345678", "phone": "010-1111-2222",
        })
        assert "이미 가입된 이메일" in r.get_data(as_text=True)

    def test_short_password(self, client):
        r = client.post("/signup", data={
            "email": "pw@example.com", "password": "short", "password2": "short",
            "phone": "010-1111-2222",
        })
        assert "8자 이상" in r.get_data(as_text=True)

    def test_password_mismatch(self, client):
        r = client.post("/signup", data={
            "email": "pw2@example.com", "password": "pw-12345678",
            "password2": "pw-different", "phone": "010-1111-2222",
        })
        assert "일치하지 않습니다" in r.get_data(as_text=True)

    def test_phone_required(self, client):
        r = client.post("/signup", data={
            "email": "nophone@example.com", "password": "pw-12345678",
            "password2": "pw-12345678",
        })
        assert "휴대폰" in r.get_data(as_text=True)

    def test_duplicate_nickname(self, app, client):
        with app.app_context():
            taken = User.query.filter(User.nickname.isnot(None)).first().nickname
        r = client.post("/signup", data={
            "email": "nick@example.com", "password": "pw-12345678",
            "password2": "pw-12345678", "phone": "010-1111-2222", "nickname": taken,
        })
        assert "이미 사용 중인 닉네임" in r.get_data(as_text=True)


# ─────────────────────────── 변호사 가입 ───────────────────────────
class TestLawyerSignup:
    DATA = {
        "email": "newlawyer@example.com", "password": "pw-12345678",
        "password2": "pw-12345678", "phone": "010-3333-4444", "name": "신입변",
        "license_no": "2026-9999", "firm_name": "테스트 법률사무소",
    }

    def test_success_pending(self, app, client, sample_file):
        r = client.post("/signup/lawyer",
                        data={**self.DATA, "verification_files": sample_file("license.png")},
                        content_type="multipart/form-data", follow_redirects=False)
        assert r.status_code == 302 and "/auth/pending" in r.headers["Location"]
        with app.app_context():
            u = User.query.filter_by(email=self.DATA["email"]).first()
            assert u.role == "lawyer" and u.status == "pending"
            prof = db.session.get(LawyerProfile, u.id)
            assert prof.license_no == "2026-9999"
            vf = LawyerVerificationFile.query.filter_by(user_id=u.id).all()
            assert len(vf) == 1
            assert vf[0].file_url.startswith(f"verification/{u.id}/")
            assert "license" not in vf[0].file_url  # 원본 파일명 미사용(uuid)
            # 실제 파일 저장 확인 (static 밖 UPLOAD_FOLDER)
            saved = os.path.join(app.config["UPLOAD_FOLDER"], vf[0].file_url)
            assert os.path.exists(saved)
        # pending 안내 페이지 접근 가능
        assert client.get("/auth/pending").status_code == 200

    def test_files_required(self, client):
        r = client.post("/signup/lawyer", data=self.DATA,
                        content_type="multipart/form-data")
        assert "인증 서류를 1개 이상" in r.get_data(as_text=True)

    def test_bad_extension(self, client, sample_file):
        r = client.post("/signup/lawyer",
                        data={**self.DATA, "verification_files": sample_file("malware.exe", b"MZ")},
                        content_type="multipart/form-data")
        assert "jpg, jpeg, png, pdf" in r.get_data(as_text=True)

    def test_license_and_firm_required(self, client, sample_file):
        data = {**self.DATA, "license_no": "", "firm_name": "",
                "verification_files": sample_file()}
        r = client.post("/signup/lawyer", data=data, content_type="multipart/form-data")
        html = r.get_data(as_text=True)
        assert "등록번호" in html and "소속" in html


# ─────────────────────────── 로그인 ───────────────────────────
class TestLogin:
    def test_user_success_redirect_main(self, client):
        r = client.post("/login", data={"email": "user1@example.com", "password": USER_PW},
                        follow_redirects=False)
        assert r.status_code == 302 and r.headers["Location"] in ("/", "http://localhost/")

    def test_next_redirect(self, client):
        r = client.post("/login?next=/counsel/",
                        data={"email": "user1@example.com", "password": USER_PW},
                        follow_redirects=False)
        assert r.headers["Location"].endswith("/counsel/")

    def test_open_redirect_blocked(self, client):
        r = client.post("/login?next=//evil.com",
                        data={"email": "user1@example.com", "password": USER_PW},
                        follow_redirects=False)
        assert "evil.com" not in r.headers["Location"]

    def test_wrong_password(self, client):
        r = client.post("/login", data={"email": "user1@example.com", "password": "wrong"})
        assert "이메일 또는 비밀번호가 올바르지 않습니다" in r.get_data(as_text=True)

    def test_lock_after_5_fails(self, app, client):
        for _ in range(5):
            client.post("/login", data={"email": "user1@example.com", "password": "wrong"})
        with app.app_context():
            assert cache.get("login_fail:user1@example.com") == 5
        # 6회째는 올바른 비밀번호여도 잠금
        r = client.post("/login", data={"email": "user1@example.com", "password": USER_PW})
        assert "잠금되었습니다" in r.get_data(as_text=True)

    def test_success_clears_counter(self, app, client):
        for _ in range(3):
            client.post("/login", data={"email": "user1@example.com", "password": "wrong"})
        client.post("/login", data={"email": "user1@example.com", "password": USER_PW})
        with app.app_context():
            assert not cache.get("login_fail:user1@example.com")

    def test_unknown_email_counts(self, app, client):
        client.post("/login", data={"email": "ghost@example.com", "password": "wrong"})
        with app.app_context():
            assert cache.get("login_fail:ghost@example.com") == 1

    def test_suspended_no_counter(self, app, client):
        _make_user(app, "susp@example.com", status="suspended", status_reason="테스트 정지")
        r = client.post("/login", data={"email": "susp@example.com", "password": "pw-12345678"})
        assert "정지된 계정" in r.get_data(as_text=True)
        with app.app_context():
            assert not cache.get("login_fail:susp@example.com")

    def test_withdrawn_blocked(self, app, client):
        _make_user(app, "gone@example.com", status="withdrawn")
        r = client.post("/login", data={"email": "gone@example.com", "password": "pw-12345678"})
        assert "올바르지 않습니다" in r.get_data(as_text=True)

    def test_admin_rejected_on_user_login(self, client):
        r = client.post("/login", data={"email": "admin@angimo.kr", "password": "angimo-admin-1234"})
        assert "관리자 로그인 페이지를 이용해주세요" in r.get_data(as_text=True)
        # 세션 미생성 — 보호 페이지 접근 불가
        assert client.get("/mypage/", follow_redirects=False).status_code == 302

    def test_lawyer_redirects_to_dashboard(self, client):
        r = client.post("/login", data={"email": "lawyer1@angimo.kr", "password": "lawyer-1234"},
                        follow_redirects=False)
        assert r.headers["Location"].endswith("/lawyer/")

    def test_pending_lawyer_redirects_to_pending(self, app, client):
        _make_user(app, "plaw@example.com", role="lawyer", status="pending", name="대기변")
        r = client.post("/login", data={"email": "plaw@example.com", "password": "pw-12345678"},
                        follow_redirects=False)
        assert r.headers["Location"].endswith("/auth/pending")


class TestAdminLogin:
    def test_admin_success(self, client):
        r = client.post("/admin/login",
                        data={"email": "admin@angimo.kr", "password": "angimo-admin-1234"},
                        follow_redirects=False)
        assert r.headers["Location"].endswith("/admin/")

    def test_non_admin_rejected_and_counted(self, app, client):
        r = client.post("/admin/login", data={"email": "user1@example.com", "password": USER_PW})
        assert "관리자 계정이 아닙니다" in r.get_data(as_text=True)
        with app.app_context():
            assert cache.get("login_fail:user1@example.com") == 1


def test_logout(client, login_as):
    login_as("user1@example.com")
    assert client.get("/mypage/").status_code == 200
    client.get("/logout")
    assert client.get("/mypage/", follow_redirects=False).status_code == 302
