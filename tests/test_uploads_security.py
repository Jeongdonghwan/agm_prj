# -*- coding: utf-8 -*-
"""업로드 서빙 보안 — 인증 서류 차단, 경로 탈출, 용량 제한."""
import io

from extensions import db
from models import LawyerVerificationFile, User


def _signup_lawyer_with_file(app, client, sample_file, email="seclaw@example.com"):
    client.post("/signup/lawyer", data={
        "email": email, "password": "pw-12345678", "password2": "pw-12345678",
        "phone": "010-0000-1111", "name": "보안변", "license_no": "S-1",
        "firm_name": "보안펌", "verification_files": sample_file("secret.png"),
    }, content_type="multipart/form-data")
    client.get("/logout")
    with app.app_context():
        uid = User.query.filter_by(email=email).first().id
        vf = LawyerVerificationFile.query.filter_by(user_id=uid).first()
        return uid, vf.id, vf.file_url


class TestVerificationServing:
    def test_public_route_403(self, app, client, sample_file):
        _, _, file_url = _signup_lawyer_with_file(app, client, sample_file)
        # /uploads/verification/... 은 무조건 403 (§11)
        assert client.get(f"/uploads/{file_url}").status_code == 403
        # 백슬래시 우회도 차단
        assert client.get(f"/uploads/{file_url.replace('/', '%5C')}").status_code == 403

    def test_admin_route_serves(self, app, client, login_as, sample_file):
        _, fid, _ = _signup_lawyer_with_file(app, client, sample_file, "seclaw2@example.com")
        login_as("admin@angimo.kr")
        r = client.get(f"/admin/verification-files/{fid}")
        assert r.status_code == 200 and r.data.startswith(b"\x89PNG")

    def test_admin_route_blocked_for_others(self, app, client, login_as, sample_file):
        _, fid, _ = _signup_lawyer_with_file(app, client, sample_file, "seclaw3@example.com")
        assert client.get(f"/admin/verification-files/{fid}",
                          follow_redirects=False).status_code == 302
        login_as("user1@example.com")
        assert client.get(f"/admin/verification-files/{fid}").status_code == 403
        login_as("lawyer1@angimo.kr")
        assert client.get(f"/admin/verification-files/{fid}").status_code == 403

    def test_missing_file_404(self, client, login_as):
        login_as("admin@angimo.kr")
        assert client.get("/admin/verification-files/999999").status_code == 404


class TestPathTraversal:
    def test_dotdot_blocked(self, client):
        # UPLOAD_FOLDER 밖(config.py 등) 접근 시도 → 404 (safe_join)
        for path in (
            "/uploads/%2e%2e/config.py",
            "/uploads/..%2fconfig.py",
            "/uploads/community/%2e%2e/%2e%2e/config.py",
        ):
            r = client.get(path)
            assert r.status_code in (403, 404), path
            assert b"SECRET_KEY" not in r.data

    def test_missing_upload_404(self, client):
        assert client.get("/uploads/profiles/1/none.png").status_code == 404


class TestUploadLimits:
    def test_max_content_length_413(self, app, client, login_as):
        with app.app_context():
            u = User.query.filter_by(email="user1@example.com").first()
            u.nickname = u.nickname or "용량테스터"
            db.session.commit()
        login_as("user1@example.com")
        big = (io.BytesIO(b"0" * (11 * 1024 * 1024)), "big.png")  # 11MB > 10MB 제한
        r = client.post("/community/write",
                        data={"category": "자유게시판", "title": "t", "content": "c",
                              "attachments": big},
                        content_type="multipart/form-data")
        assert r.status_code == 413
