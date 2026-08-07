# -*- coding: utf-8 -*-
"""어드민 통합 점검 — 전 화면 접근·전 CRUD 왕복·링크 무결성·권한.

기능별 상세 검증은 test_admin.py가 담당하고, 여기서는 "관리하다가 깨지는 곳이
없는지"를 넓게 훑는다(500·깨진 url_for·리다이렉트 루프·권한 누락).
"""
import re

import pytest
from flask import url_for

from extensions import db
from models import Banner, FirmAd, LawyerAd, LegalCase, News, User

ADMIN = "admin@angimo.kr"

# GET으로 열리는 어드민 화면 전부
ADMIN_PAGES = [
    "/admin/",
    "/admin/users", "/admin/users?status=suspended", "/admin/users?q=user1",
    "/admin/lawyers", "/admin/lawyers?status=all", "/admin/lawyers?q=김",
    "/admin/consultations",
    "/admin/community",
    "/admin/boards", "/admin/boards/new",
    "/admin/posts", "/admin/posts?status=published", "/admin/posts?status=all",
    "/admin/cases", "/admin/cases/new",
    "/admin/news", "/admin/news/new",
    "/admin/banners", "/admin/banners/new",
    "/admin/firms", "/admin/firms/new",
    "/admin/lawyer-ads", "/admin/lawyer-ads/new", "/admin/lawyer-ads?slot=photocard",
    "/admin/reports",
    "/admin/firm-inquiries",
    "/admin/logs",
]


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_page_opens(client, login_as, path):
    """모든 어드민 화면이 500 없이 열린다."""
    login_as(ADMIN)
    r = client.get(path)
    assert r.status_code == 200, f"{path} → {r.status_code}"


@pytest.mark.parametrize("path", ADMIN_PAGES)
def test_admin_requires_admin(client, login_as, path):
    """비로그인은 admin 로그인으로, 일반회원은 403."""
    assert client.get(path, follow_redirects=False).status_code == 302, path
    login_as("user1@example.com")
    assert client.get(path).status_code == 403, path


def test_no_broken_links_in_admin(app, client, login_as):
    """어드민 화면 안의 내부 링크가 모두 유효한 라우트인지(404·500 없음)."""
    login_as(ADMIN)
    checked, bad = set(), []
    for page in ADMIN_PAGES:
        html = client.get(page).get_data(as_text=True)
        for href in re.findall(r'href="(/[^"#?]*)', html):
            if href in checked or href.startswith(("/uploads", "/static")):
                continue
            checked.add(href)
            code = client.get(href, follow_redirects=False).status_code
            if code >= 400:
                bad.append(f"{href} ← {page} ({code})")
    assert not bad, "깨진 링크: " + ", ".join(bad)


def test_sidebar_menu_all_reachable(client, login_as):
    """사이드바 메뉴 12개가 전부 열린다(신규 '변호사 광고 관리' 포함)."""
    login_as(ADMIN)
    html = client.get("/admin/").get_data(as_text=True)
    nav = html.split('<nav>', 1)[1].split("</nav>", 1)[0]
    links = re.findall(r'href="(/admin[^"]*)"', nav)
    assert len(links) >= 12, links
    for href in links:
        assert client.get(href).status_code == 200, href


class TestCrudRoundTrip:
    """생성 → 수정 → 삭제가 끝까지 도는지(관리 중 흔한 실사용 경로)."""

    def _admin(self, login_as):
        login_as(ADMIN)

    def test_case_crud(self, app, client, login_as):
        self._admin(login_as)
        client.post("/admin/cases/new", data={
            "title": "점검용 판례", "summary": "s", "content": "c", "case_type": "civil"})
        with app.app_context():
            item = LegalCase.query.filter_by(title="점검용 판례").first()
            assert item
            cid = item.id
        r = client.post(f"/admin/cases/{cid}/edit", data={
            "title": "점검용 판례(수정)", "summary": "s2", "content": "c2",
            "case_type": "criminal"}, follow_redirects=True)
        assert r.status_code == 200
        with app.app_context():
            assert db.session.get(LegalCase, cid).title == "점검용 판례(수정)"
        client.post(f"/admin/cases/{cid}/delete")
        with app.app_context():
            assert db.session.get(LegalCase, cid).deleted_at is not None

    def test_news_crud(self, app, client, login_as):
        self._admin(login_as)
        client.post("/admin/news/new", data={
            "title": "점검용 뉴스", "content": "c", "hashtags": "점검"})
        with app.app_context():
            nid = News.query.filter_by(title="점검용 뉴스").first().id
        client.post(f"/admin/news/{nid}/edit", data={
            "title": "점검용 뉴스(수정)", "content": "c2", "hashtags": "점검, 추가"})
        with app.app_context():
            n = db.session.get(News, nid)
            assert n.title == "점검용 뉴스(수정)" and n.hashtags == ["점검", "추가"]
        client.post(f"/admin/news/{nid}/delete")
        with app.app_context():
            assert db.session.get(News, nid).deleted_at is not None

    def test_banner_crud(self, app, client, login_as):
        self._admin(login_as)
        client.post("/admin/banners/new", data={
            "position": "main_hero", "title": "점검용 배너|포인트|서브",
            "sort_order": "5", "is_active": "1",
            "starts_at": "2026-01-01T00:00", "ends_at": "2026-12-31T23:59"})
        with app.app_context():
            b = Banner.query.filter_by(title="점검용 배너|포인트|서브").first()
            assert b and b.starts_at.year == 2026
            bid = b.id
        client.post(f"/admin/banners/{bid}/edit", data={
            "position": "main_side", "title": "점검용 배너(수정)", "is_active": "0"})
        with app.app_context():
            b = db.session.get(Banner, bid)
            assert b.position == "main_side" and b.is_active is False
            assert b.starts_at is None  # 빈 값 제출 시 해제
        client.post(f"/admin/banners/{bid}/delete")
        with app.app_context():
            assert db.session.get(Banner, bid) is None

    def test_firm_crud(self, app, client, login_as):
        self._admin(login_as)
        client.post("/admin/firms/new", data={
            "firm_name": "점검용로펌", "headline": "h", "description": "d",
            "category_id": "1", "is_active": "1", "sort_order": "0",
            "links": "홈페이지|https://a.example.com"})
        with app.app_context():
            f = FirmAd.query.filter_by(firm_name="점검용로펌").first()
            assert f and f.links[0]["label"] == "홈페이지"
            fid = f.id
        client.post(f"/admin/firms/{fid}/edit", data={
            "firm_name": "점검용로펌(수정)", "headline": "h2", "description": "d2",
            "is_active": "1", "links": ""})
        with app.app_context():
            f = db.session.get(FirmAd, fid)
            assert f.firm_name == "점검용로펌(수정)" and f.links is None
        client.post(f"/admin/firms/{fid}/delete")
        with app.app_context():
            assert db.session.get(FirmAd, fid) is None

    def test_lawyer_ad_crud(self, app, client, login_as):
        self._admin(login_as)
        with app.app_context():
            uid = User.query.filter_by(email="lawyer1@angimo.kr").first().id
        client.post("/admin/lawyer-ads/new", data={
            "lawyer_id": uid, "category_ids": ["1", "2"], "slot": "photocard",
            "is_active": "1"})
        with app.app_context():
            ad = LawyerAd.query.filter_by(lawyer_id=uid).order_by(LawyerAd.id.desc()).first()
            assert ad and ad.category_ids == [1, 2]
            aid = ad.id
        client.post(f"/admin/lawyer-ads/{aid}/edit", data={
            "lawyer_id": uid, "slot": "adlist", "is_active": "0"})
        with app.app_context():
            ad = db.session.get(LawyerAd, aid)
            assert ad.slot == "adlist" and ad.category_ids == []  # 전체 노출
            assert ad.is_active is False
        client.post(f"/admin/lawyer-ads/{aid}/delete")
        with app.app_context():
            assert db.session.get(LawyerAd, aid) is None

    def test_lawyer_ad_rejects_non_lawyer(self, app, client, login_as):
        """변호사가 아닌 사용자를 광고로 지정하면 저장되지 않는다."""
        self._admin(login_as)
        with app.app_context():
            uid = User.query.filter_by(email="user1@example.com").first().id
            before = LawyerAd.query.count()
        r = client.post("/admin/lawyer-ads/new", data={
            "lawyer_id": uid, "slot": "photocard", "is_active": "1"},
            follow_redirects=True)
        assert "변호사를 선택해주세요" in r.get_data(as_text=True)
        with app.app_context():
            assert LawyerAd.query.count() == before

    def test_missing_ids_404(self, client, login_as):
        self._admin(login_as)
        for path in ("/admin/cases/999999/edit", "/admin/news/999999/edit",
                     "/admin/banners/999999/edit", "/admin/firms/999999/edit",
                     "/admin/lawyer-ads/999999/edit", "/admin/lawyers/999999"):
            assert client.get(path).status_code == 404, path


class TestModerationFlows:
    """게시판 관리가 최근 변경(사연신청 카테고리 추가) 후에도 정상인지."""

    def test_community_notice_and_new_category(self, app, client, login_as):
        login_as(ADMIN)
        r = client.post("/admin/community",
                        data={"title": "점검 공지", "content": "내용"},
                        follow_redirects=True)
        assert "공지글이 등록되었습니다" in r.get_data(as_text=True)
        # 공지는 카테고리 칩과 무관하게 상단 고정으로 노출 (승인 회원 시점)
        with app.app_context():
            member_id = User.query.filter_by(email="user1@example.com").first().id
        c2 = app.test_client()
        with c2.session_transaction() as sess:
            sess["user_id"] = member_id
        pub = c2.get("/community/").get_data(as_text=True)
        assert "점검 공지" in pub
        assert "사연신청" in pub  # 신규 카테고리 칩

    def test_admin_community_lists_all_categories(self, app, client, login_as):
        """어드민 커뮤니티 관리에 사연신청 글도 보인다."""
        from models import CommunityPost
        with app.app_context():
            u = User.query.filter_by(email="user1@example.com").first()
            db.session.add(CommunityPost(user_id=u.id, category="사연신청",
                                         title="점검용 사연", content="c"))
            db.session.commit()
        login_as(ADMIN)
        assert "점검용 사연" in client.get("/admin/community").get_data(as_text=True)

    def test_consultation_moderation(self, app, client, login_as):
        from models import Consultation
        with app.app_context():
            cid = Consultation.query.filter_by(status="open").first().id
        login_as(ADMIN)
        client.post(f"/admin/consultations/{cid}/hide")
        with app.app_context():
            assert db.session.get(Consultation, cid).status == "hidden"
        client.post(f"/admin/consultations/{cid}/hide")  # 토글 복귀
        with app.app_context():
            assert db.session.get(Consultation, cid).status == "open"


LAWYER_PAGES = [
    "/lawyer/", "/lawyer/profile", "/lawyer/answers",
    "/lawyer/posts", "/lawyer/posts?status=pending", "/lawyer/posts?status=published",
    "/lawyer/posts/new", "/lawyer/settings",
]


@pytest.mark.parametrize("path", LAWYER_PAGES)
def test_lawyer_admin_page_opens(client, login_as, path):
    """변호사 어드민 전 화면이 500 없이 열린다."""
    login_as("lawyer1@angimo.kr")
    assert client.get(path).status_code == 200, path


@pytest.mark.parametrize("path", LAWYER_PAGES)
def test_lawyer_admin_guards(client, login_as, path):
    """비로그인 리다이렉트 / 일반회원·관리자 403(본인 스코프 전용)."""
    assert client.get(path, follow_redirects=False).status_code == 302, path
    login_as("user1@example.com")
    assert client.get(path).status_code == 403, path


def test_lawyer_admin_no_broken_links(client, login_as):
    login_as("lawyer1@angimo.kr")
    checked, bad = set(), []
    for page in LAWYER_PAGES:
        html = client.get(page).get_data(as_text=True)
        for href in re.findall(r'href="(/lawyer[^"#?]*)', html):
            if href in checked:
                continue
            checked.add(href)
            code = client.get(href, follow_redirects=False).status_code
            if code >= 400:
                bad.append(f"{href} ← {page} ({code})")
    assert not bad, "깨진 링크: " + ", ".join(bad)


def test_lawyer_post_full_cycle(app, client, login_as):
    """작성 → 관리자 반려 → 변호사 수정(재검수) → 관리자 승인 → 공개 노출."""
    from models import LawyerPost

    uid = login_as("lawyer1@angimo.kr")
    client.post("/lawyer/posts/new", data={
        "type": "case", "title": "사이클 점검 사례", "content": "본문", "category_id": "1"})
    with app.app_context():
        p = LawyerPost.query.filter_by(lawyer_id=uid, title="사이클 점검 사례").first()
        assert p.status == "pending"
        pid = p.id

    login_as(ADMIN)
    client.post(f"/admin/posts/{pid}/reject", data={"reason": "보완 필요"})
    with app.app_context():
        assert db.session.get(LawyerPost, pid).status == "rejected"

    login_as("lawyer1@angimo.kr")
    r = client.get(f"/lawyer/posts/{pid}/edit")
    assert r.status_code == 200 and "보완 필요" in r.get_data(as_text=True)
    client.post(f"/lawyer/posts/{pid}/edit", data={
        "type": "case", "title": "사이클 점검 사례(보완)", "content": "보완 본문",
        "category_id": "1"})
    with app.app_context():
        p = db.session.get(LawyerPost, pid)
        assert p.status == "pending" and p.reject_reason is None

    login_as(ADMIN)
    client.post(f"/admin/posts/{pid}/approve")
    with app.app_context():
        assert db.session.get(LawyerPost, pid).status == "published"
    assert "사이클 점검 사례(보완)" in (
        app.test_client().get("/posts?type=case").get_data(as_text=True)
    )


def test_lawyer_answer_cycle(app, client, login_as):
    """답변 등록 → 수정 → 삭제 후 피드 복귀."""
    from models import Consultation, ConsultationAnswer

    with app.app_context():
        u = User.query.filter_by(email="user1@example.com").first()
        c = Consultation(user_id=u.id, title="답변 사이클 점검", content="본문",
                         is_public=True, category_id=1)
        db.session.add(c)
        db.session.commit()
        cid = c.id

    uid = login_as("lawyer1@angimo.kr")
    client.post("/lawyer/answers", data={"consultation_id": cid, "content": "첫 답변"})
    with app.app_context():
        a = ConsultationAnswer.query.filter_by(consultation_id=cid, lawyer_id=uid).first()
        assert a and a.content == "첫 답변"
        aid = a.id
    client.post(f"/lawyer/answers/{aid}/edit", data={"content": "수정한 답변"})
    with app.app_context():
        assert db.session.get(ConsultationAnswer, aid).content == "수정한 답변"
    client.post(f"/lawyer/answers/{aid}/delete")
    with app.app_context():
        assert db.session.get(ConsultationAnswer, aid).deleted_at is not None
    # 삭제 후 같은 상담글에 다시 답변 가능
    r = client.post("/lawyer/answers",
                    data={"consultation_id": cid, "content": "다시 쓴 답변"},
                    follow_redirects=True)
    assert "답변이 등록되었습니다" in r.get_data(as_text=True)


def test_admin_actions_are_logged(app, client, login_as):
    """관리 액션이 운영 로그에 남고 로그 화면이 열린다."""
    from models import AdminLog

    login_as(ADMIN)
    client.post("/admin/cases/new", data={
        "title": "로그 점검 판례", "summary": "s", "content": "c", "case_type": "civil"})
    with app.app_context():
        assert AdminLog.query.filter_by(action="case_save").count() >= 1
    assert "case_save" in client.get("/admin/logs").get_data(as_text=True)
