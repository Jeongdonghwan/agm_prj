# -*- coding: utf-8 -*-
"""총관리자 — 승인/검수/CRUD/게시판 관리/신고/운영 로그/캐시 무효화."""
from extensions import db
from models import (
    AdminLog,
    Banner,
    CommunityPost,
    Consultation,
    FirmAd,
    FirmInquiry,
    LawyerPost,
    LawyerProfile,
    LawyerVerificationFile,
    LegalCase,
    News,
    Report,
    User,
)

ADMIN = "admin@angimo.kr"


def _signup_pending_lawyer(app, client_factory, sample_file, email="applaw@example.com"):
    """가입 플로우로 pending 변호사 + 인증 서류 생성 (별도 클라이언트 사용)."""
    c = client_factory()
    c.post("/signup/lawyer", data={
        "email": email, "password": "pw-12345678", "password2": "pw-12345678",
        "phone": "010-1234-0000", "name": "지원변호사", "license_no": "2026-0001",
        "firm_name": "지원로펌", "verification_files": sample_file("doc.png"),
    }, content_type="multipart/form-data")
    with app.app_context():
        return User.query.filter_by(email=email).first().id


class TestAccess:
    def test_anon_redirects_admin_login(self, client):
        r = client.get("/admin/", follow_redirects=False)
        assert r.status_code == 302 and "/admin/login" in r.headers["Location"]

    def test_user_403(self, client, login_as):
        login_as("user1@example.com")
        assert client.get("/admin/").status_code == 403

    def test_lawyer_403(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        assert client.get("/admin/").status_code == 403


def test_dashboard(client, login_as):
    login_as(ADMIN)
    html = client.get("/admin/").get_data(as_text=True)
    assert "승인 대기" in html and "검수" in html


class TestUserManagement:
    def test_list_and_search(self, client, login_as):
        login_as(ADMIN)
        html = client.get("/admin/users").get_data(as_text=True)
        assert "user1@example.com" in html and "일반회원" in html
        html = client.get("/admin/users?q=user1").get_data(as_text=True)
        assert "user1@example.com" in html and "user2@example.com" not in html

    def test_suspend_blocks_login_then_activate(self, app, client, login_as):
        with app.app_context():
            uid = User.query.filter_by(email="user3@example.com").first().id
        login_as(ADMIN)
        r = client.post(f"/admin/users/{uid}/suspend", data={"reason": "욕설 반복"},
                        follow_redirects=True)
        assert "정지했습니다" in r.get_data(as_text=True)
        with app.app_context():
            u = db.session.get(User, uid)
            assert u.status == "suspended" and u.status_reason == "욕설 반복"
        # 정지 회원 로그인 차단
        c2 = app.test_client()
        r = c2.post("/login", data={"email": "user3@example.com", "password": "user-1234"})
        assert "정지된 계정" in r.get_data(as_text=True)
        # 해제 → 로그인 가능
        client.post(f"/admin/users/{uid}/activate")
        with app.app_context():
            u = db.session.get(User, uid)
            assert u.status == "active" and u.status_reason is None
        r = c2.post("/login", data={"email": "user3@example.com", "password": "user-1234"},
                    follow_redirects=False)
        assert r.status_code == 302 and "/login" not in (r.headers.get("Location") or "")

    def test_withdraw(self, app, client, login_as):
        with app.app_context():
            uid = User.query.filter_by(email="user4@example.com").first().id
        login_as(ADMIN)
        client.post(f"/admin/users/{uid}/withdraw")
        with app.app_context():
            u = db.session.get(User, uid)
            assert u.status == "withdrawn" and u.deleted_at is not None

    def test_lawyer_guarded_404(self, app, client, login_as):
        with app.app_context():
            lid = User.query.filter_by(email="lawyer1@angimo.kr").first().id
        login_as(ADMIN)
        assert client.post(f"/admin/users/{lid}/suspend", data={"reason": "x"}).status_code == 404

    def test_action_logged(self, app, client, login_as):
        with app.app_context():
            uid = User.query.filter_by(email="user5@example.com").first().id
        login_as(ADMIN)
        client.post(f"/admin/users/{uid}/suspend", data={"reason": "로그 검증"})
        with app.app_context():
            log = AdminLog.query.filter_by(action="user_suspend").order_by(
                AdminLog.id.desc()).first()
            assert log and log.target == f"user:{uid}"


class TestFeaturedCase:
    def _published_case(self, app, title="광고 후보 사례"):
        with app.app_context():
            from datetime import datetime
            lawyer = User.query.filter_by(email="lawyer1@angimo.kr").first()
            p = LawyerPost(lawyer_id=lawyer.id, type="case", title=title, content="본문",
                           status="published", published_at=datetime.now())
            db.session.add(p)
            db.session.commit()
            return p.id

    def test_toggle_featured(self, app, client, login_as):
        pid = self._published_case(app)
        login_as(ADMIN)
        r = client.post(f"/admin/posts/{pid}/toggle-featured", follow_redirects=True)
        assert "광고 노출 상태를 변경했습니다" in r.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(LawyerPost, pid).is_featured is True
        # 변호사 목록 상단 광고 영역 최상단에 해당 변호사 카드 + AD 뱃지
        # (카드는 사례 제목이 아닌 변호사 프로필을 노출)
        with app.app_context():
            name = db.session.get(LawyerPost, pid).lawyer.name
        c2 = app.test_client()
        html = c2.get("/lawyers/").get_data(as_text=True)
        first_card = html.split('class="sa-card"')[1]
        assert f"{name} 변호사" in first_card and "ad-tag" in first_card

    def test_pending_or_non_case_404(self, app, client, login_as):
        with app.app_context():
            lawyer = User.query.filter_by(email="lawyer1@angimo.kr").first()
            pending = LawyerPost(lawyer_id=lawyer.id, type="case", title="대기", content="c",
                                 status="pending")
            guide = LawyerPost(lawyer_id=lawyer.id, type="guide", title="가이드", content="c",
                               status="published")
            db.session.add_all([pending, guide])
            db.session.commit()
            pid1, pid2 = pending.id, guide.id
        login_as(ADMIN)
        assert client.post(f"/admin/posts/{pid1}/toggle-featured").status_code == 404
        assert client.post(f"/admin/posts/{pid2}/toggle-featured").status_code == 404

    def test_featured_tab_lists_only_ads(self, app, client, login_as):
        """광고 노출중 탭 — 지정한 글만, 미지정 게시중 글은 제외."""
        ad_id = self._published_case(app, "광고 지정된 사례")
        self._published_case(app, "광고 아닌 사례")
        login_as(ADMIN)
        client.post(f"/admin/posts/{ad_id}/toggle-featured")
        html = client.get("/admin/posts?status=featured").get_data(as_text=True)
        assert "광고 지정된 사례" in html
        assert "광고 아닌 사례" not in html

    def test_admin_posts_page_explains_ad_area(self, client, login_as):
        """광고 관리 위치 안내 — 어드민에서 광고칸 구동법을 찾을 수 있어야 함."""
        login_as(ADMIN)
        html = client.get("/admin/posts").get_data(as_text=True)
        assert "이런 고민, 이렇게 해결됩니다" in html and "광고 노출중" in html


class TestLawyerApproval:
    def test_approve(self, app, client, login_as, sample_file):
        uid = _signup_pending_lawyer(app, app.test_client, sample_file)
        login_as(ADMIN)
        r = client.post(f"/admin/lawyers/{uid}/approve", follow_redirects=True)
        assert "승인했습니다" in r.get_data(as_text=True)
        with app.app_context():
            u = db.session.get(User, uid)
            assert u.status == "active"
            assert db.session.get(LawyerProfile, uid).approved_at is not None
            log = AdminLog.query.filter_by(action="lawyer_approve").order_by(
                AdminLog.id.desc()).first()
            assert log and log.target == f"user:{uid}"
        # 승인 후 로그인 → 변호사 대시보드
        c2 = app.test_client()
        r = c2.post("/login", data={"email": "applaw@example.com", "password": "pw-12345678"},
                    follow_redirects=False)
        assert r.headers["Location"].endswith("/lawyer/")

    def test_reject_with_reason(self, app, client, login_as, sample_file):
        uid = _signup_pending_lawyer(app, app.test_client, sample_file, "rejlaw@example.com")
        login_as(ADMIN)
        client.post(f"/admin/lawyers/{uid}/reject", data={"reason": "서류 식별 불가"})
        with app.app_context():
            u = db.session.get(User, uid)
            assert u.status == "rejected" and u.status_reason == "서류 식별 불가"

    def test_toggle_visible(self, app, client, login_as):
        with app.app_context():
            uid = User.query.filter_by(email="lawyer1@angimo.kr").first().id
        login_as(ADMIN)
        client.post(f"/admin/lawyers/{uid}/toggle-visible")
        with app.app_context():
            assert db.session.get(LawyerProfile, uid).is_visible is False
        # 공개 상세도 404
        c2 = app.test_client()
        assert c2.get(f"/lawyers/{uid}", follow_redirects=True).status_code == 404

    def test_toggle_new(self, app, client, login_as):
        with app.app_context():
            uid = User.query.filter_by(email="lawyer2@angimo.kr").first().id
        login_as(ADMIN)
        client.post(f"/admin/lawyers/{uid}/toggle-new")
        with app.app_context():
            assert db.session.get(LawyerProfile, uid).show_in_new is False


class TestVerificationFiles:
    def test_admin_only_serving(self, app, client, login_as, sample_file):
        uid = _signup_pending_lawyer(app, app.test_client, sample_file, "vflaw@example.com")
        with app.app_context():
            fid = LawyerVerificationFile.query.filter_by(user_id=uid).first().id
        # 비로그인 → admin 로그인으로
        assert client.get(f"/admin/verification-files/{fid}",
                          follow_redirects=False).status_code == 302
        # 일반회원 403
        login_as("user1@example.com")
        assert client.get(f"/admin/verification-files/{fid}").status_code == 403
        # admin 200 (파일 실서빙)
        login_as(ADMIN)
        r = client.get(f"/admin/verification-files/{fid}")
        assert r.status_code == 200 and r.data.startswith(b"\x89PNG")


class TestPostReview:
    def _pending_post(self, app, title="검수용 포스트"):
        with app.app_context():
            lawyer = User.query.filter_by(email="lawyer1@angimo.kr").first()
            p = LawyerPost(lawyer_id=lawyer.id, type="case", title=title,
                           content="본문", status="pending", category_id=1)
            db.session.add(p)
            db.session.commit()
            return p.id

    def test_lawyer_written_post_shows_in_pending(self, app, client, login_as):
        """변호사 작성 플로우 → 어드민 승인 대기 탭 노출 (엔드투엔드)."""
        login_as("lawyer1@angimo.kr")
        client.post("/lawyer/posts/new", data={
            "type": "case", "title": "플로우 검증 사례", "content": "본문",
            "category_id": "1", "result_badge": "승소"})
        login_as(ADMIN)
        html = client.get("/admin/posts?status=pending").get_data(as_text=True)
        assert "플로우 검증 사례" in html
        assert "플로우 검증 사례" in client.get("/admin/").get_data(as_text=True)  # 대시보드 검수 대기

    def test_approve_publishes(self, app, client, login_as):
        pid = self._pending_post(app)
        login_as(ADMIN)
        r = client.post(f"/admin/posts/{pid}/approve", follow_redirects=True)
        assert "승인·게시했습니다" in r.get_data(as_text=True)
        with app.app_context():
            p = db.session.get(LawyerPost, pid)
            assert p.status == "published" and p.published_at is not None
        # 공개 목록 노출 + 분야 필터 매칭 (관리자 액션이 페이지 캐시도 무효화)
        c2 = app.test_client()
        assert "검수용 포스트" in c2.get("/posts?type=case").get_data(as_text=True)
        assert "검수용 포스트" in c2.get("/posts?type=case&category=1").get_data(as_text=True)
        assert "검수용 포스트" not in c2.get("/posts?type=case&category=7").get_data(as_text=True)
        # 해당 분야 변호사 목록 상단 광고 영역에 작성 변호사 카드로 매칭
        with app.app_context():
            name = db.session.get(LawyerPost, pid).lawyer.name
        ad_area = c2.get("/lawyers/?category=1").get_data(as_text=True).split(
            'class="sa-grid"', 1)[1]
        assert f"{name} 변호사" in ad_area

    def test_reject_with_reason(self, app, client, login_as):
        pid = self._pending_post(app, "반려될 포스트")
        login_as(ADMIN)
        client.post(f"/admin/posts/{pid}/reject", data={"reason": "광고성 문구"})
        with app.app_context():
            p = db.session.get(LawyerPost, pid)
            assert p.status == "rejected" and p.reject_reason == "광고성 문구"


class TestCasesCrud:
    def test_create_edit_delete(self, app, client, login_as):
        login_as(ADMIN)
        client.post("/admin/cases/new", data={
            "title": "신규 판례입니다", "summary": "요약", "content": "본문",
            "court": "대법원", "case_no": "2026도1234", "case_type": "criminal",
            "category_ids": "1",
        })
        with app.app_context():
            case = LegalCase.query.filter_by(title="신규 판례입니다").first()
            assert case and case.category_ids == [1]
            cid = case.id
        # 공개 페이지 노출 (캐시 무효화 확인)
        c2 = app.test_client()
        assert "신규 판례입니다" in c2.get("/cases").get_data(as_text=True)
        # 수정
        client.post(f"/admin/cases/{cid}/edit", data={
            "title": "수정된 판례", "summary": "s", "content": "c", "case_type": "civil"})
        with app.app_context():
            assert db.session.get(LegalCase, cid).title == "수정된 판례"
        # 삭제(soft) → 공개 404
        client.post(f"/admin/cases/{cid}/delete")
        with app.app_context():
            assert db.session.get(LegalCase, cid).deleted_at is not None
        assert c2.get(f"/cases/{cid}", follow_redirects=True).status_code == 404


class TestNewsCrud:
    def test_create_with_hashtags_thumbnail(self, app, client, login_as, sample_file):
        login_as(ADMIN)
        client.post("/admin/news/new",
                    data={"title": "신규 뉴스입니다", "content": "본문",
                          "reporter": "안기모", "hashtags": "#이혼, 상속",
                          "thumbnail": sample_file("cover.png")},
                    content_type="multipart/form-data")
        with app.app_context():
            n = News.query.filter_by(title="신규 뉴스입니다").first()
            assert n.hashtags == ["이혼", "상속"]
            assert n.thumbnail_url and n.thumbnail_url.startswith("/uploads/news/")
            nid = n.id
        c2 = app.test_client()
        assert "신규 뉴스입니다" in c2.get("/news").get_data(as_text=True)
        client.post(f"/admin/news/{nid}/delete")
        with app.app_context():
            assert db.session.get(News, nid).deleted_at is not None


class TestBannersCrud:
    def test_create_delete(self, app, client, login_as, sample_file):
        login_as(ADMIN)
        client.post("/admin/banners/new",
                    data={"position": "main_side", "title": "테스트 배너|포인트|서브",
                          "link_url": "/community/", "sort_order": "9", "is_active": "1",
                          "image": sample_file("banner.png")},
                    content_type="multipart/form-data")
        with app.app_context():
            b = Banner.query.filter_by(title="테스트 배너|포인트|서브").first()
            assert b.position == "main_side" and b.is_active
            assert b.image_url.startswith("/uploads/banners/")
            bid = b.id
        client.post(f"/admin/banners/{bid}/delete")
        with app.app_context():
            assert db.session.get(Banner, bid) is None  # 하드 삭제


class TestFirmsCrud:
    def test_create_with_links_photos(self, app, client, login_as, sample_file):
        login_as(ADMIN)
        client.post("/admin/firms/new",
                    data={"firm_name": "테스트로펌", "headline": "헤드라인",
                          "description": "소개", "category_id": "1", "is_active": "1",
                          "links": "홈페이지|https://firm.example.com\n블로그|https://blog.example.com",
                          "photos": [sample_file("p1.png"), sample_file("p2.png")]},
                    content_type="multipart/form-data")
        with app.app_context():
            f = FirmAd.query.filter_by(firm_name="테스트로펌").first()
            assert len(f.links) == 2 and f.links[0]["label"] == "홈페이지"
            assert len(f.photos) == 2
            fid = f.id
        c2 = app.test_client()
        assert "테스트로펌" in c2.get("/firms").get_data(as_text=True)
        client.post(f"/admin/firms/{fid}/delete")
        with app.app_context():
            assert db.session.get(FirmAd, fid) is None

    def test_inquiry_flow(self, app, client, login_as):
        with app.app_context():
            fid = FirmAd.query.first().id
        c2 = app.test_client()  # 비회원 문의
        r = c2.post(f"/api/firms/{fid}/inquiry",
                    json={"name": "문의자", "phone": "010-1111-0000", "content": "상담 문의"})
        assert r.status_code == 200
        login_as(ADMIN)
        html = client.get("/admin/firm-inquiries").get_data(as_text=True)
        assert "문의자" in html
        with app.app_context():
            iid = FirmInquiry.query.filter_by(name="문의자").first().id
        r = client.post(f"/admin/firm-inquiries/{iid}/process", follow_redirects=True)
        assert "처리 완료" in r.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(FirmInquiry, iid).status == "processed"


class TestBoardsModeration:
    def test_consultation_hide_toggle_delete(self, app, client, login_as):
        with app.app_context():
            cid = Consultation.query.filter_by(status="open", is_public=True).first().id
        login_as(ADMIN)
        client.post(f"/admin/consultations/{cid}/hide")
        with app.app_context():
            assert db.session.get(Consultation, cid).status == "hidden"
        c2 = app.test_client()
        assert c2.get(f"/counsel/{cid}", follow_redirects=True).status_code == 404
        # admin은 hidden 열람 가능
        assert client.get(f"/counsel/{cid}", follow_redirects=True).status_code == 200
        # 재토글 → open
        client.post(f"/admin/consultations/{cid}/hide")
        with app.app_context():
            assert db.session.get(Consultation, cid).status == "open"
        client.post(f"/admin/consultations/{cid}/delete")
        with app.app_context():
            assert db.session.get(Consultation, cid).status == "deleted"

    def test_community_notice_and_moderation(self, app, client, login_as):
        login_as(ADMIN)
        r = client.post("/admin/community",
                        data={"title": "테스트 공지", "content": "공지 내용"},
                        follow_redirects=True)
        assert "공지글이 등록되었습니다" in r.get_data(as_text=True)
        c2 = app.test_client()
        html = c2.get("/community/").get_data(as_text=True)
        assert "테스트 공지" in html
        with app.app_context():
            notice = CommunityPost.query.filter_by(title="테스트 공지").first()
            assert notice.is_notice
            pid = CommunityPost.query.filter_by(is_notice=False, status="open").first().id
        client.post(f"/admin/community/{pid}/hide")
        assert c2.get(f"/community/{pid}").status_code == 404
        client.post(f"/admin/community/{pid}/delete")
        with app.app_context():
            assert db.session.get(CommunityPost, pid).status == "deleted"


class TestReports:
    def test_report_done_flow(self, app, client, login_as):
        # user가 신고 접수
        login_as("user1@example.com")
        with app.app_context():
            pid = CommunityPost.query.filter_by(status="open", is_notice=False).first().id
        r = client.post("/api/reports", json={
            "target_type": "community_post", "target_id": pid, "reason": "관리자 검증 신고"})
        assert r.status_code == 200
        login_as(ADMIN)
        html = client.get("/admin/reports").get_data(as_text=True)
        assert "관리자 검증 신고" in html
        with app.app_context():
            rid = Report.query.filter_by(reason="관리자 검증 신고").first().id
        client.post(f"/admin/reports/{rid}/done")
        with app.app_context():
            assert db.session.get(Report, rid).status == "done"


def test_admin_logs_page(client, login_as):
    login_as(ADMIN)
    # 액션 하나 발생시켜 로그 기록
    client.post("/admin/community", data={"title": "로그용 공지", "content": "c"})
    html = client.get("/admin/logs").get_data(as_text=True)
    assert "community_notice" in html


def test_cache_invalidated_by_admin_action(app, client, login_as):
    """비로그인 캐시된 목록이 관리자 쓰기 후 즉시 갱신되는지 (_log → invalidate)."""
    anon = app.test_client()
    assert "캐시 검증 판례" not in anon.get("/cases").get_data(as_text=True)  # 캐시 적재
    login_as(ADMIN)
    client.post("/admin/cases/new", data={
        "title": "캐시 검증 판례", "summary": "s", "content": "c", "case_type": "civil"})
    assert "캐시 검증 판례" in anon.get("/cases").get_data(as_text=True)
