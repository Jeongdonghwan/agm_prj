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
    LawyerAd,
    LawyerPost,
    LawyerProfile,
    LawyerVerificationFile,
    LegalCase,
    News,
    Report,
    User,
)
from utils import invalidate_page_cache

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
    assert "Phase" not in html  # 스캐폴딩 스텁 문구 잔존 금지


def test_dashboard_recent_reports(app, client, login_as):
    """최근 신고 패널 — 실데이터 렌더 + 신고 처리로 링크."""
    from models import Report, User

    with app.app_context():
        uid = User.query.filter_by(email="user1@example.com").first().id
        db.session.add(Report(reporter_id=uid, target_type="community_post",
                              target_id=1, reason="대시보드 확인용 신고"))
        db.session.commit()
    login_as(ADMIN)
    html = client.get("/admin/").get_data(as_text=True)
    panel = html.split("최근 신고", 1)[1]
    assert "대시보드 확인용 신고" in panel and "커뮤니티 글" in panel
    assert 'href="/admin/reports"' in panel


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


class TestLawyerSearchAndDetail:
    """변호사 검색 + 상세/강제 수정 (§4-4)."""

    def test_search_by_name_email_firm(self, app, client, login_as):
        login_as(ADMIN)
        with app.app_context():
            u = User.query.filter_by(email="lawyer1@angimo.kr").first()
            name, firm = u.name, u.lawyer_profile.firm_name
            other = User.query.filter_by(email="lawyer5@angimo.kr").first().name
        for kw in (name, "lawyer1@angimo.kr", firm):
            html = client.get(f"/admin/lawyers?status=all&q={kw}").get_data(as_text=True)
            assert name in html, kw
        html = client.get(f"/admin/lawyers?status=all&q={name}").get_data(as_text=True)
        assert other not in html  # 검색어와 무관한 변호사는 제외

    def test_detail_shows_profile_info(self, app, client, login_as):
        login_as(ADMIN)
        with app.app_context():
            p = LawyerProfile.query.filter(LawyerProfile.intro_full.isnot(None)).first()
            uid, headline, intro = p.user_id, p.headline, p.intro_full[:20]
            firm, cat = p.firm_name, p.categories[0].name
        html = client.get(f"/admin/lawyers/{uid}").get_data(as_text=True)
        for frag in (headline, intro, firm, cat, "프로필 강제 수정", "공개 프로필 보기"):
            assert frag in html, frag

    def test_detail_force_edit_reflects_public(self, app, client, login_as):
        login_as(ADMIN)
        with app.app_context():
            uid = LawyerProfile.query.first().user_id
        r = client.post(f"/admin/lawyers/{uid}", data={
            "headline": "관리자가 수정한 헤드라인", "office_phone": "02-1234-5678",
            "firm_name": "수정된 법무법인", "categories": "1",
        }, follow_redirects=True)
        assert "프로필을 수정했습니다" in r.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(LawyerProfile, uid).headline == "관리자가 수정한 헤드라인"
            log = AdminLog.query.filter_by(action="lawyer_profile_edit").first()
            assert log is not None
        html = app.test_client().get(f"/lawyers/{uid}", follow_redirects=True).get_data(as_text=True)
        assert "관리자가 수정한 헤드라인" in html

    def test_detail_validation(self, app, client, login_as):
        login_as(ADMIN)
        with app.app_context():
            uid = LawyerProfile.query.first().user_id
        r = client.post(f"/admin/lawyers/{uid}",
                        data={"headline": "h", "office_phone": "", "kakao_url": ""})
        assert "하나는 반드시 입력" in r.get_data(as_text=True)

    def test_detail_guards(self, app, client, login_as):
        login_as(ADMIN)
        assert client.get("/admin/lawyers/999999").status_code == 404
        with app.app_context():
            uid = User.query.filter_by(email="user1@example.com").first().id
        assert client.get(f"/admin/lawyers/{uid}").status_code == 404  # 변호사 아님
        login_as("user1@example.com")
        assert client.get("/admin/lawyers/2").status_code == 403


class TestLawyerAds:
    """변호사 광고 — 광고/운영 메뉴에서 분야별로 지정."""

    def _clear(self, app):
        with app.app_context():
            LawyerAd.query.delete()
            db.session.commit()
            invalidate_page_cache()

    def _lawyer(self, app, email="lawyer1@angimo.kr"):
        with app.app_context():
            u = User.query.filter_by(email=email).first()
            return u.id, u.name

    def _add_ad(self, app, client, lawyer_id, slot="photocard", category_id="", **kw):
        data = {"lawyer_id": lawyer_id, "slot": slot, "category_id": category_id,
                "is_active": "1", "sort_order": "0", **kw}
        return client.post("/admin/lawyer-ads/new", data=data, follow_redirects=True)

    def test_category_specific_ad(self, app, client, login_as):
        """분야 지정 광고는 그 분야에서만 노출."""
        self._clear(app)
        uid, name = self._lawyer(app)
        login_as(ADMIN)
        r = self._add_ad(app, client, uid, category_id="1")
        assert "변호사 광고가 저장되었습니다" in r.get_data(as_text=True)
        c2 = app.test_client()
        # 지정 분야에는 노출
        html = c2.get("/lawyers/?category=1").get_data(as_text=True)
        assert 'class="sa-grid"' in html and f"{name} 변호사" in html
        # 다른 분야에는 미노출
        assert 'class="sa-grid"' not in c2.get("/lawyers/?category=7").get_data(as_text=True)

    def test_global_ad_shows_everywhere(self, app, client, login_as):
        """전체 노출(카테고리 미지정) 광고는 모든 분야 화면에 노출."""
        self._clear(app)
        uid, name = self._lawyer(app)
        login_as(ADMIN)
        self._add_ad(app, client, uid, category_id="")
        c2 = app.test_client()
        for path in ("/lawyers/", "/lawyers/?category=1", "/lawyers/?category=7"):
            assert f"{name} 변호사" in c2.get(path).get_data(as_text=True), path

    def test_slots_are_independent(self, app, client, login_as):
        """포토카드와 AD LAWYERS는 별개 상품 — 한쪽만 지정하면 한쪽만 노출."""
        self._clear(app)
        uid, name = self._lawyer(app)
        login_as(ADMIN)
        self._add_ad(app, client, uid, slot="photocard")
        c2 = app.test_client()
        html = c2.get("/lawyers/").get_data(as_text=True)
        assert 'class="sa-grid"' in html and "AD LAWYERS" not in html
        # AD리스트도 추가하면 둘 다
        self._add_ad(app, client, uid, slot="adlist")
        html = c2.get("/lawyers/").get_data(as_text=True)
        assert 'class="sa-grid"' in html and "AD LAWYERS" in html

    def test_inactive_and_expired_not_shown(self, app, client, login_as):
        self._clear(app)
        uid, name = self._lawyer(app)
        login_as(ADMIN)
        self._add_ad(app, client, uid, is_active="0")  # 중지
        c2 = app.test_client()
        assert 'class="sa-grid"' not in c2.get("/lawyers/").get_data(as_text=True)
        self._clear(app)
        self._add_ad(app, client, uid, ends_at="2020-01-01T00:00")  # 기간 만료
        assert 'class="sa-grid"' not in c2.get("/lawyers/").get_data(as_text=True)

    def test_adlist_has_no_headcount_limit(self, app, client, login_as):
        """AD LAWYERS는 인원 제한 없이 지정한 만큼 전부 노출."""
        self._clear(app)
        login_as(ADMIN)
        names = []
        with app.app_context():
            profs = LawyerProfile.query.limit(5).all()
            ids = [(p.user_id, p.user.name) for p in profs]
        for uid, name in ids:
            names.append(name)
            self._add_ad(app, client, uid, slot="adlist")
        html = app.test_client().get("/lawyers/").get_data(as_text=True)
        ad_area = html.split("AD LAWYERS", 1)[1].split("plain-label", 1)[0]
        for name in names:
            assert f"{name} 변호사" in ad_area, name

    def test_only_designated_lawyers_shown(self, app, client, login_as):
        self._clear(app)
        uid, name = self._lawyer(app)
        _, other = self._lawyer(app, "lawyer2@angimo.kr")
        login_as(ADMIN)
        self._add_ad(app, client, uid)
        ad_area = app.test_client().get("/lawyers/").get_data(as_text=True) \
            .split('class="sa-grid"', 1)[1].split("sec-title", 1)[0]
        assert f"{name} 변호사" in ad_area and f"{other} 변호사" not in ad_area

    def test_admin_list_groups_by_category(self, app, client, login_as):
        self._clear(app)
        uid, name = self._lawyer(app)
        login_as(ADMIN)
        self._add_ad(app, client, uid, category_id="1")
        self._add_ad(app, client, uid, slot="adlist", category_id="")
        html = client.get("/admin/lawyer-ads").get_data(as_text=True)
        assert "전체 노출" in html and name in html
        assert "최상단 포토카드" in html and "AD LAWYERS" in html

    def test_delete_ad(self, app, client, login_as):
        self._clear(app)
        uid, name = self._lawyer(app)
        login_as(ADMIN)
        self._add_ad(app, client, uid)
        with app.app_context():
            ad_id = LawyerAd.query.first().id
        client.post(f"/admin/lawyer-ads/{ad_id}/delete")
        with app.app_context():
            assert LawyerAd.query.count() == 0
        assert 'class="sa-grid"' not in app.test_client().get("/lawyers/").get_data(as_text=True)

    def test_menu_is_under_ad_group(self, client, login_as):
        login_as(ADMIN)
        html = client.get("/admin/lawyer-ads").get_data(as_text=True)
        assert "변호사 광고 관리" in html  # 사이드바 메뉴 노출

    def test_post_review_has_no_ad_controls(self, client, login_as):
        """포스트 검수에서는 광고 기능이 제거됨."""
        login_as(ADMIN)
        html = client.get("/admin/posts").get_data(as_text=True)
        assert "광고 노출중" not in html and "toggle-featured" not in html


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
        # 커뮤니티는 승인 회원 전용 — 일반 회원 시점으로 확인
        with app.app_context():
            member_id = User.query.filter_by(email="user1@example.com").first().id
        c2 = app.test_client()
        with c2.session_transaction() as sess:
            sess["user_id"] = member_id
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
