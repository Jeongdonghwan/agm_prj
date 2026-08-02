# -*- coding: utf-8 -*-
"""변호사 어드민 — 권한/대시보드/프로필/답변/포스트/설정."""
import os

from extensions import db
from models import Consultation, LawyerPost, LawyerProfile, User


def _lawyer(app, n=1):
    with app.app_context():
        return User.query.filter_by(email=f"lawyer{n}@angimo.kr").first().id


def _make_pending_lawyer(app, email="pending-law@example.com"):
    with app.app_context():
        u = User(email=email, name="대기변호사", phone="010-0000-0000",
                 role="lawyer", status="pending")
        u.set_password("pw-12345678")
        db.session.add(u)
        db.session.flush()
        db.session.add(LawyerProfile(user_id=u.id, license_no="P-1"))
        db.session.commit()
        return u.id


def _new_consultation(app, title="답변용 질문"):
    with app.app_context():
        u1 = User.query.filter_by(email="user1@example.com").first()
        c = Consultation(user_id=u1.id, title=title, content="본문", is_public=True)
        db.session.add(c)
        db.session.commit()
        return c.id


class TestAccess:
    def test_anon_redirects_login(self, client):
        r = client.get("/lawyer/", follow_redirects=False)
        assert r.status_code == 302 and "/login" in r.headers["Location"]

    def test_user_403(self, client, login_as):
        login_as("user1@example.com")
        assert client.get("/lawyer/").status_code == 403

    def test_pending_lawyer_redirected(self, app, client):
        uid = _make_pending_lawyer(app)
        with client.session_transaction() as sess:
            sess["user_id"] = uid
        r = client.get("/lawyer/", follow_redirects=False)
        assert r.status_code == 302 and "/auth/pending" in r.headers["Location"]


def test_dashboard_stats(client, login_as):
    login_as("lawyer1@angimo.kr")
    html = client.get("/lawyer/").get_data(as_text=True)
    assert "프로필 조회수" in html or "조회수" in html
    assert "답변" in html and "포스트" in html


class TestProfile:
    def test_save_reflects_public_page(self, app, client, login_as):
        uid = login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/profile", data={
            "headline": "테스트 헤드라인입니다",
            "office_phone": "02-555-0000",
            "firm_name": "테스트펌",
        }, follow_redirects=True)
        assert "프로필이 저장되었습니다" in r.get_data(as_text=True)
        html = client.get(f"/lawyers/{uid}", follow_redirects=True).get_data(as_text=True)
        assert "테스트 헤드라인입니다" in html

    def test_contact_required(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/profile", data={"headline": "h", "office_phone": "", "kakao_url": ""})
        assert "하나는 반드시 입력" in r.get_data(as_text=True)

    def test_kakao_url_scheme(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/profile", data={"kakao_url": "pf.kakao.com/xyz"})
        assert "http(s)://로 시작" in r.get_data(as_text=True)

    def test_max_7_categories(self, app, client, login_as):
        login_as("lawyer1@angimo.kr")
        from models import Category
        with app.app_context():
            ids = [str(c.id) for c in Category.query.limit(8)]
        r = client.post("/lawyer/profile", data={"office_phone": "02-1", "categories": ids})
        assert "최대 7개" in r.get_data(as_text=True)

    def test_photo_upload(self, app, client, login_as, sample_file):
        uid = login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/profile",
                        data={"office_phone": "02-555-0000", "photo": sample_file("me.png")},
                        content_type="multipart/form-data", follow_redirects=True)
        assert "프로필이 저장되었습니다" in r.get_data(as_text=True)
        with app.app_context():
            prof = db.session.get(LawyerProfile, uid)
            assert prof.photo_url.startswith(f"/uploads/profiles/{uid}/")
            fname = prof.photo_url.split("/")[-1]
            assert os.path.exists(os.path.join(
                app.config["UPLOAD_FOLDER"], "profiles", str(uid), fname))

    def test_photo_remove(self, app, client, login_as, sample_file):
        """사진 제거 — 잘못 올린 사진을 기본 이미지로 되돌린다."""
        uid = login_as("lawyer1@angimo.kr")
        client.post("/lawyer/profile",
                    data={"office_phone": "02-555-0000", "photo": sample_file("x.png")},
                    content_type="multipart/form-data")
        with app.app_context():
            assert db.session.get(LawyerProfile, uid).photo_url is not None
        client.post("/lawyer/profile",
                    data={"office_phone": "02-555-0000", "remove_photo": "1"},
                    content_type="multipart/form-data")
        with app.app_context():
            assert db.session.get(LawyerProfile, uid).photo_url is None

    def test_photo_bad_ext(self, client, login_as, sample_file):
        login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/profile",
                        data={"office_phone": "02-1", "photo": sample_file("x.gif", b"GIF89a")},
                        content_type="multipart/form-data")
        assert "jpg, jpeg, png만" in r.get_data(as_text=True)


class TestVisibility:
    def test_incomplete_profile_hidden_from_list(self, app, client):
        with app.app_context():
            prof = db.session.get(LawyerProfile, _lawyer(app, 1))
            name = prof.user.name
            prof.photo_url = None  # 필수 필드 제거
            db.session.commit()
        # 상단 해결사례 광고 영역(관리자 지정 노출)은 제외하고 변호사 목록 섹션만 검사
        html = client.get("/lawyers/").get_data(as_text=True)
        list_section = html.split('sec-title">변호사')[1]
        assert name not in list_section

    def test_invisible_detail_404(self, app, client):
        uid = _lawyer(app, 1)
        with app.app_context():
            db.session.get(LawyerProfile, uid).is_visible = False
            db.session.commit()
        assert client.get(f"/lawyers/{uid}", follow_redirects=True).status_code == 404


class TestAnswers:
    def test_feed_page(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        html = client.get("/lawyer/answers").get_data(as_text=True)
        assert "답변 대기" in html

    def test_answer_flow(self, app, client, login_as):
        cid = _new_consultation(app)
        login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/answers",
                        data={"consultation_id": cid, "content": "성실한 답변입니다."},
                        follow_redirects=True)
        assert "답변이 등록되었습니다" in r.get_data(as_text=True)
        # 1인 1답변
        r = client.post("/lawyer/answers",
                        data={"consultation_id": cid, "content": "중복"}, follow_redirects=True)
        assert "이미 이 상담글에 답변했습니다" in r.get_data(as_text=True)
        # 다른 변호사는 가능
        login_as("lawyer2@angimo.kr")
        r = client.post("/lawyer/answers",
                        data={"consultation_id": cid, "content": "두 번째 답변"},
                        follow_redirects=True)
        assert "답변이 등록되었습니다" in r.get_data(as_text=True)
        # 공개 상세에 두 답변 노출
        client.get("/logout")
        html = client.get(f"/counsel/{cid}", follow_redirects=True).get_data(as_text=True)
        assert "성실한 답변입니다" in html and "두 번째 답변" in html

    def test_empty_content(self, app, client, login_as):
        cid = _new_consultation(app)
        login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/answers", data={"consultation_id": cid, "content": " "},
                        follow_redirects=True)
        assert "답변 내용을 입력해주세요" in r.get_data(as_text=True)

    def test_missing_consultation(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/answers", data={"consultation_id": 999999, "content": "x"},
                        follow_redirects=True)
        assert "상담글을 찾을 수 없습니다" in r.get_data(as_text=True)


class TestPosts:
    def test_create_pending_not_public(self, app, client, login_as):
        uid = login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/posts/new", data={
            "type": "case", "title": "검수 대기 사례", "content": "본문",
            "result_badge": "무죄", "category_id": "1",
        }, follow_redirects=True)
        assert "관리자 검수 후 게시됩니다" in r.get_data(as_text=True)
        with app.app_context():
            p = LawyerPost.query.filter_by(lawyer_id=uid, title="검수 대기 사례").first()
            assert p.status == "pending" and p.result_badge == "무죄"
        client.get("/logout")
        assert "검수 대기 사례" not in client.get("/posts?type=case").get_data(as_text=True)

    def test_thumbnail_upload(self, app, client, login_as, sample_file):
        uid = login_as("lawyer1@angimo.kr")
        client.post("/lawyer/posts/new",
                    data={"type": "guide", "title": "썸네일 가이드", "content": "본문",
                          "category_id": "1", "thumbnail": sample_file("thumb.png")},
                    content_type="multipart/form-data")
        with app.app_context():
            p = LawyerPost.query.filter_by(lawyer_id=uid, title="썸네일 가이드").first()
            assert p.thumbnail_url.startswith(f"/uploads/posts/{uid}/")

    def test_thumbnail_bad_ext(self, client, login_as, sample_file):
        login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/posts/new",
                        data={"type": "guide", "title": "t", "content": "c",
                              "category_id": "1", "thumbnail": sample_file("bad.webp", b"RIFF")},
                        content_type="multipart/form-data")
        assert "jpg, jpeg, png만" in r.get_data(as_text=True)

    def test_validation_errors(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        r = client.post("/lawyer/posts/new", data={"type": "bad", "title": "", "content": ""})
        html = r.get_data(as_text=True)
        assert "타입" in html and "제목" in html and "본문" in html
        assert "분야를 선택해주세요" in html  # 분야 필수 — 필터/광고 매칭 기준

    def test_delete_own_soft(self, app, client, login_as):
        uid = login_as("lawyer1@angimo.kr")
        client.post("/lawyer/posts/new", data={"type": "essay", "title": "삭제될 글", "content": "c", "category_id": "1"})
        with app.app_context():
            pid = LawyerPost.query.filter_by(lawyer_id=uid, title="삭제될 글").first().id
        client.post(f"/lawyer/posts/{pid}/delete")
        with app.app_context():
            assert db.session.get(LawyerPost, pid).deleted_at is not None

    def test_cannot_delete_others_post(self, app, client, login_as):
        uid = login_as("lawyer1@angimo.kr")
        client.post("/lawyer/posts/new", data={"type": "essay", "title": "남의 글", "content": "c", "category_id": "1"})
        with app.app_context():
            pid = LawyerPost.query.filter_by(lawyer_id=uid, title="남의 글").first().id
        login_as("lawyer2@angimo.kr")
        r = client.post(f"/lawyer/posts/{pid}/delete", follow_redirects=True)
        assert "찾을 수 없습니다" in r.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(LawyerPost, pid).deleted_at is None


class TestSettings:
    def test_password_change(self, client, login_as):
        login_as("lawyer3@angimo.kr")
        r = client.post("/lawyer/settings", data={
            "action": "password", "current_password": "lawyer-1234",
            "new_password": "new-lawyer-pw1"}, follow_redirects=True)
        assert "비밀번호가 변경되었습니다" in r.get_data(as_text=True)
        client.get("/logout")
        r = client.post("/login", data={"email": "lawyer3@angimo.kr", "password": "new-lawyer-pw1"},
                        follow_redirects=False)
        assert r.headers["Location"].endswith("/lawyer/")

    def test_firm_change(self, app, client, login_as):
        uid = login_as("lawyer3@angimo.kr")
        r = client.post("/lawyer/settings", data={"action": "firm", "firm_name": "새로운 로펌"},
                        follow_redirects=True)
        assert "소속이 변경되었습니다" in r.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(LawyerProfile, uid).firm_name == "새로운 로펌"
