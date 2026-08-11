# -*- coding: utf-8 -*-
"""경량 /api — 연락 클릭, 로펌 문의, 닉네임, 추천, 신고 + 에러 규약."""
from extensions import db
from models import CommunityPost, FirmAd, LawyerProfile, User


def _err(r):
    body = r.get_json()
    assert "error" in body and "code" in body["error"] and "message" in body["error"]
    return body["error"]["code"]


def _post_id(app):
    with app.app_context():
        return CommunityPost.query.filter_by(status="open", is_notice=False).first().id


class TestContactClick:
    def test_anonymous_ok_and_counted(self, app, client):
        with app.app_context():
            prof = LawyerProfile.query.first()
            uid, before = prof.user_id, prof.contact_click_count or 0
        r = client.post(f"/api/lawyers/{uid}/contact-click", json={"type": "phone"})
        assert r.status_code == 200 and r.get_json()["ok"] is True
        client.post(f"/api/lawyers/{uid}/contact-click", json={"type": "kakao"})
        with app.app_context():
            db.session.expire_all()
            assert db.session.get(LawyerProfile, uid).contact_click_count == before + 2

    def test_invalid_type_400(self, app, client):
        with app.app_context():
            uid = LawyerProfile.query.first().user_id
        r = client.post(f"/api/lawyers/{uid}/contact-click", json={"type": "email"})
        assert r.status_code == 400 and _err(r) == "INVALID_TYPE"

    def test_missing_profile_404(self, client):
        r = client.post("/api/lawyers/999999/contact-click", json={"type": "phone"})
        assert r.status_code == 404 and _err(r) == "NOT_FOUND"


class TestFirmInquiry:
    def test_missing_phone_400(self, app, client):
        with app.app_context():
            fid = FirmAd.query.first().id
        r = client.post(f"/api/firms/{fid}/inquiry", json={"agree": True})
        assert r.status_code == 400 and _err(r) == "MISSING_FIELDS"

    def test_consent_required_400(self, app, client):
        """YK식 — 개인정보 동의 없이는 접수 불가."""
        with app.app_context():
            fid = FirmAd.query.first().id
        r = client.post(f"/api/firms/{fid}/inquiry", json={"phone": "010-1234-5678"})
        assert r.status_code == 400 and _err(r) == "CONSENT_REQUIRED"

    def test_phone_only_accepted(self, app, client):
        """휴대폰 + 동의만으로 접수 — 이름 없이 저장."""
        from models import FirmInquiry

        with app.app_context():
            fid = FirmAd.query.first().id
        r = client.post(f"/api/firms/{fid}/inquiry",
                        json={"phone": "010-7777-8888", "agree": True})
        assert r.status_code == 200
        with app.app_context():
            i = FirmInquiry.query.filter_by(phone="010-7777-8888").first()
            assert i is not None and i.name is None

    def test_missing_firm_404(self, client):
        r = client.post("/api/firms/999999/inquiry",
                        json={"phone": "p", "agree": True})
        assert r.status_code == 404


class TestNickname:
    def test_check_banned_and_duplicate(self, app, client):
        r = client.get("/api/me/nickname/check?value=관리자짱")
        assert r.get_json()["available"] is False
        with app.app_context():
            taken = User.query.filter(User.nickname.isnot(None)).first().nickname
        r = client.get(f"/api/me/nickname/check?value={taken}")
        assert r.get_json()["available"] is False
        r = client.get("/api/me/nickname/check?value=완전새닉네임")
        assert r.get_json()["available"] is True

    def test_set_requires_login(self, client):
        r = client.put("/api/me/nickname", json={"value": "새닉네임"})
        assert r.status_code == 401 and _err(r) == "UNAUTHORIZED"

    def test_set_invalid_400(self, client, login_as):
        login_as("user2@example.com")
        r = client.put("/api/me/nickname", json={"value": "!"})
        assert r.status_code == 400 and _err(r) == "INVALID_NICKNAME"

    def test_set_duplicate_409(self, app, client, login_as):
        login_as("user2@example.com")
        with app.app_context():
            taken = User.query.filter(User.nickname.isnot(None)).first().nickname
        r = client.put("/api/me/nickname", json={"value": taken})
        assert r.status_code == 409 and _err(r) == "DUPLICATED"

    def test_set_then_30day_limit(self, app, client, login_as):
        login_as("user2@example.com")  # 시드: 닉네임 없음 → 최초 설정은 허용
        r = client.put("/api/me/nickname", json={"value": "첫닉네임"})
        assert r.status_code == 200 and r.get_json()["nickname"] == "첫닉네임"
        r = client.put("/api/me/nickname", json={"value": "바꾼닉네임"})
        assert r.status_code == 429 and _err(r) == "TOO_SOON"


class TestLike:
    def test_requires_login(self, app, client):
        r = client.post(f"/api/community/posts/{_post_id(app)}/like")
        assert r.status_code == 401

    def test_lawyer_forbidden(self, app, client, login_as):
        login_as("lawyer1@angimo.kr")
        r = client.post(f"/api/community/posts/{_post_id(app)}/like")
        assert r.status_code == 403 and _err(r) == "FORBIDDEN"

    def test_like_once(self, app, client, login_as):
        # 시드가 기존 글에 user1 추천을 넣어두므로 새 글로 검증
        with app.app_context():
            u2 = User.query.filter_by(email="user2@example.com").first()
            p = CommunityPost(user_id=u2.id, category="자유게시판",
                              title="추천 대상 글", content="c")
            db.session.add(p)
            db.session.commit()
            pid, before = p.id, 0
        login_as("user1@example.com")
        r = client.post(f"/api/community/posts/{pid}/like")
        assert r.status_code == 200 and r.get_json()["likes"] == before + 1
        r = client.post(f"/api/community/posts/{pid}/like")
        assert r.status_code == 409 and _err(r) == "ALREADY_LIKED"

    def test_missing_post_404(self, client, login_as):
        login_as("user1@example.com")
        assert client.post("/api/community/posts/999999/like").status_code == 404


class TestReports:
    def test_requires_login(self, client):
        assert client.post("/api/reports", json={}).status_code == 401

    def test_invalid_target_400(self, client, login_as):
        login_as("user1@example.com")
        r = client.post("/api/reports", json={"target_type": "bad", "target_id": 1, "reason": "r"})
        assert r.status_code == 400 and _err(r) == "INVALID_TARGET"

    def test_missing_reason_400(self, app, client, login_as):
        login_as("user1@example.com")
        r = client.post("/api/reports",
                        json={"target_type": "community_post", "target_id": _post_id(app)})
        assert r.status_code == 400 and _err(r) == "MISSING_FIELDS"

    def test_ok(self, app, client, login_as):
        login_as("user1@example.com")
        r = client.post("/api/reports", json={
            "target_type": "consultation", "target_id": 1, "reason": "API 검증 신고"})
        assert r.status_code == 200 and r.get_json()["ok"] is True
