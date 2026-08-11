# -*- coding: utf-8 -*-
"""커뮤니티 — 목록/보드/글·댓글/익명/닉네임 규칙/첨부파일."""
import os
import re

from extensions import db
from models import CommunityPost, User


def _active_chips(html):
    """칩 줄에서 선택(class="on")된 칩의 라벨 목록."""
    row = html.split('class="cat-chips"', 1)[1].split("</div>", 1)[0]
    return re.findall(r'<a [^>]*class="on"[^>]*>([^<]+)</a>', row)


def _chip_labels(html):
    row = html.split('class="cat-chips"', 1)[1].split("</div>", 1)[0]
    return [m.strip() for m in re.findall(r"<a [^>]*>([^<]+)</a>", row)]


def _list_head(html):
    return html.split('class="list-head"', 1)[1].split("</div>", 1)[0]


def _set_nickname(app, email, nickname):
    with app.app_context():
        u = User.query.filter_by(email=email).first()
        u.nickname = nickname
        db.session.commit()


def _write(client, sample_file=None, files=None, **kw):
    data = {"category": "자유게시판", "title": "커뮤 글", "content": "본문", **kw}
    if files is not None:
        data["attachments"] = files
    return client.post("/community/write", data=data,
                       content_type="multipart/form-data", follow_redirects=False)


class TestList:
    def test_200_chips_notice(self, client, login_as):
        login_as("user1@example.com")
        html = client.get("/community/").get_data(as_text=True)
        assert "자유게시판" in html and "옥바라지 이야기" in html
        assert "사연신청" in html  # 신규 카테고리
        assert "공지" in html

    def test_story_category_write_and_filter(self, app, client, login_as):
        """사연신청 카테고리 — 글 작성 후 해당 칩으로 필터."""
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, category="사연신청", title="사연 신청합니다")
        assert r.status_code == 302
        html = client.get("/community/?category=사연신청").get_data(as_text=True)
        assert "사연 신청합니다" in html

    def test_category_filter(self, client, login_as):
        login_as("user1@example.com")
        assert client.get("/community/?category=옥바라지 이야기").status_code == 200

    def test_popular_sort(self, client, login_as):
        login_as("user1@example.com")
        assert client.get("/community/?sort=popular").status_code == 200


class TestChips:
    """칩은 한 축 — 전체/인기/카테고리/정보 게시판 중 항상 하나만 선택된다."""

    def test_chip_order_without_latest(self, client, login_as):
        login_as("user1@example.com")
        labels = _chip_labels(client.get("/community/").get_data(as_text=True))
        assert labels[:2] == ["전체", "인기"]
        assert "최신" not in labels
        assert labels[2:5] == ["자유게시판", "옥바라지 이야기", "사연신청"]
        assert labels[5:] == ["교정시설 정보", "수용생활 정보", "양식 자료실"]

    def test_exactly_one_active(self, client, login_as):
        login_as("user1@example.com")
        cases = {
            "/community/": "전체",
            "/community/?sort=popular": "인기",
            "/community/?category=자유게시판": "자유게시판",
            "/community/?category=사연신청": "사연신청",
            "/community/board/facility": "교정시설 정보",
            "/community/board/forms": "양식 자료실",
        }
        for path, expected in cases.items():
            active = _active_chips(client.get(path).get_data(as_text=True))
            assert active == [expected], (path, active)

    def test_category_wins_over_popular(self, client, login_as):
        """카테고리 + 인기를 같이 넘겨도 활성 칩은 카테고리 하나뿐."""
        login_as("user1@example.com")
        html = client.get("/community/?category=자유게시판&sort=popular").get_data(as_text=True)
        assert _active_chips(html) == ["자유게시판"]

    def test_new_board_page_keeps_one_active_chip(self, client, login_as):
        """메가메뉴로 추가된 게시판도 칩 줄 끝에 자기 자신이 활성으로 붙는다."""
        login_as("user1@example.com")
        for key, label in (("market", "안기모 중고세상"), ("stage", "단계별 소통게시판"),
                           ("petition", "징계청원 게시판")):
            html = client.get(f"/community/board/{key}").get_data(as_text=True)
            assert _active_chips(html) == [label], key

    def test_list_head_shows_selection(self, client, login_as):
        login_as("user1@example.com")
        for path, expected in (("/community/", "전체"),
                               ("/community/?sort=popular", "인기 글"),
                               ("/community/?category=옥바라지 이야기", "옥바라지 이야기"),
                               ("/community/board/life", "수용생활 정보")):
            head = _list_head(client.get(path).get_data(as_text=True))
            assert expected in head and "개의 글" in head, path


class TestBoard:
    def test_boards_200(self, app, client, login_as):
        login_as("user1@example.com")
        from routes.community import get_page_boards

        with app.app_context():
            keys = list(get_page_boards())
        assert len(keys) >= 19  # 정보 3종 + 메가메뉴 신규 16종
        for key in keys:
            r = client.get(f"/community/board/{key}")
            assert r.status_code == 200, key

    def test_bad_key_404(self, client, login_as):
        login_as("user1@example.com")
        assert client.get("/community/board/unknown").status_code == 404

    def test_topic_filter(self, client, login_as):
        login_as("user1@example.com")
        html = client.get("/community/board/facility?topic=영치금 계좌").get_data(as_text=True)
        assert "영치금" in html and "서울구치소 접견" not in html

    def test_topicless_board_lists_own_posts(self, app, client, login_as):
        """세부 주제가 없는 게시판은 글의 category에 보드 라벨이 저장되고 그 보드에 뜬다."""
        _set_nickname(app, "user1@example.com", "중고왕")
        login_as("user1@example.com")
        assert _write(client, category="안기모 중고세상", title="영치금 카드 나눔").status_code == 302
        html = client.get("/community/board/market").get_data(as_text=True)
        assert "영치금 카드 나눔" in html
        # 다른 게시판에는 안 뜬다
        assert "영치금 카드 나눔" not in client.get("/community/board/ask").get_data(as_text=True)

    def test_new_forms_topic_post(self, app, client, login_as):
        """양식 자료실에 추가된 세부 주제로 작성 → 해당 주제 필터에 노출."""
        _set_nickname(app, "user1@example.com", "양식러")
        login_as("user1@example.com")
        assert _write(client, category="고소취하서", title="고소취하서 양식 공유").status_code == 302
        html = client.get("/community/board/forms?topic=고소취하서").get_data(as_text=True)
        assert "고소취하서 양식 공유" in html

    def test_forms_post_detail_renders_attachments(self, app, client, login_as):
        # 시드: 양식자료실 4건에 데모 첨부 — 목록은 이미지 썸네일만, 첨부는 상세에서 렌더
        login_as("user1@example.com")
        with app.app_context():
            pid = CommunityPost.query.filter_by(category="탄원서").first().id
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert "/uploads/community/samples/" in html and "탄원서_양식.txt" in html


class TestGnb:
    """GNB — 메가메뉴는 제거(게시판 탐색은 커뮤니티 좌측 메뉴가 담당)."""

    def test_mega_menu_removed(self, client):
        for path in ("/", "/lawyers/"):
            html = client.get(path).get_data(as_text=True)
            assert 'id="mega-community"' not in html, path
            assert "mega-toggle" not in html, path

    def test_external_links_open_safely(self, client, login_as):
        """도움되는 사이트 외부 링크 — 커뮤니티 좌측 메뉴에서 새 탭."""
        import re

        login_as("user1@example.com")
        side = client.get("/community/").get_data(as_text=True) \
            .split('class="side-menu"', 1)[1].split("</aside>", 1)[0]
        for url in ("https://www.moj.go.kr/corrections/1125/subview.do",
                    "https://www.kics.go.kr/",
                    "https://koreha.or.kr/"):
            m = re.search(r'<a href="%s"[^>]*>' % re.escape(url), side)
            assert m, url
            assert 'target="_blank"' in m.group(0) and "noopener" in m.group(0), url

    def test_logo_has_plus(self, client):
        html = client.get("/").get_data(as_text=True)
        assert '<span class="plus">+</span>' in html


class TestBoardMenuPage:
    """전체 게시판 메뉴(/community/menu) — 모바일 GNB 커뮤니티의 랜딩."""

    def test_menu_page_lists_everything(self, client, login_as):
        login_as("user1@example.com")
        html = client.get("/community/menu").get_data(as_text=True)
        assert "커뮤니티' 홈" in html and 'id="bm-filter"' in html
        for label in ("자유게시판", "가석방관련 상담신청", "안기모 중고세상",
                      "양식 자료실", "도움되는 사이트", "전국 교정기관 주소"):
            assert label in html, label

    def test_menu_page_shows_recent_posts_preview(self, app, client, login_as):
        """게시판 목록 위에 최신 전체 글 미리보기 + 더보기."""
        login_as("user1@example.com")
        html = client.get("/community/menu").get_data(as_text=True)
        assert 'class="bm-recent"' in html and "더보기" in html
        with app.app_context():
            latest = (CommunityPost.query.filter_by(status="open", is_notice=False)
                      .filter(CommunityPost.deleted_at.is_(None))
                      .order_by(CommunityPost.created_at.desc()).first())
        assert latest.title in html

    def test_menu_requires_membership(self, client, login_as):
        r = client.get("/community/menu", follow_redirects=False)
        assert r.status_code == 302 and "/login" in r.headers["Location"]
        login_as("user5@example.com")  # 미승인
        r = client.get("/community/menu", follow_redirects=False)
        assert "locked" in r.headers["Location"]

    def test_gnb_has_mobile_menu_link(self, client):
        html = client.get("/").get_data(as_text=True)
        nav = html.split('<nav class="gnb', 1)[1].split("</nav>", 1)[0]
        assert 'class="pc-only' in nav and 'class="m-only' in nav
        assert "/community/menu" in nav

    def test_bottom_nav_order_and_focus(self, client, login_as):
        """모바일 하단 GNB — 홈/변호사/상담신청/커뮤니티/마이페이지 순, 현재 탭 표시."""
        html = client.get("/").get_data(as_text=True)
        bar = html.split('class="bottom-nav"', 1)[1].split("</nav>", 1)[0]
        labels = ["홈", "변호사", "상담신청", "커뮤니티", "마이페이지"]
        idx = [bar.index(lb) for lb in labels]
        assert idx == sorted(idx)  # 순서 보장
        assert "/community/menu" in bar
        # 커뮤니티 진입 시 커뮤니티 탭 활성
        login_as("user1@example.com")
        bar = client.get("/community/menu").get_data(as_text=True) \
            .split('class="bottom-nav"', 1)[1].split("</nav>", 1)[0]
        chunk = bar.split("커뮤니티", 1)[0].rsplit("<a ", 1)[1]
        assert 'class="on"' in chunk


class TestBookmarkShareCommentLike:
    """관심글 토글·마이페이지 노출·댓글 좋아요 1인 1회."""

    def _post_id(self, app):
        with app.app_context():
            return CommunityPost.query.filter_by(status="open", is_notice=False).first().id

    def test_bookmark_toggle_and_mypage(self, app, client, login_as):
        pid = self._post_id(app)
        login_as("user1@example.com")
        r = client.post(f"/community/{pid}/bookmark")
        assert r.status_code == 200 and r.get_json()["bookmarked"] is True
        # 상세에 관심글 해제 표시 + 마이페이지 관심글 목록
        assert "관심글 해제" in client.get(f"/community/{pid}").get_data(as_text=True)
        with app.app_context():
            title = db.session.get(CommunityPost, pid).title
        assert title in client.get("/mypage/").get_data(as_text=True)
        # 다시 누르면 해제
        r = client.post(f"/community/{pid}/bookmark")
        assert r.get_json()["bookmarked"] is False

    def test_share_button_present(self, app, client, login_as):
        pid = self._post_id(app)
        login_as("user1@example.com")
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert 'id="btn-share"' in html and "링크가 복사되었습니다" in html

    def test_comment_like_once(self, app, client, login_as):
        from models import CommunityComment, User

        pid = self._post_id(app)
        with app.app_context():
            uid = User.query.filter_by(email="user1@example.com").first().id
            c = CommunityComment(post_id=pid, user_id=uid, content="좋아요 대상")
            db.session.add(c)
            db.session.commit()
            cid = c.id
        login_as("user1@example.com")
        r = client.post(f"/community/comments/{cid}/like")
        assert r.status_code == 200 and r.get_json()["likes"] == 1
        assert client.post(f"/community/comments/{cid}/like").status_code == 409  # 1인 1회
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert "btn-like-cmt on" in html  # 내가 누른 댓글 표시


class TestCategoryLock:
    """카테고리 잠금 — 어드민 게시판 관리(admin_only)로 일반회원 글쓰기 차단."""

    def _lock(self, app, slug, locked=True):
        from models import CommunityBoard

        with app.app_context():
            b = CommunityBoard.query.filter_by(slug=slug).first()
            b.admin_only = locked
            db.session.commit()

    def test_locked_category_blocks_user(self, app, client, login_as):
        self._lock(app, "free", True)
        _set_nickname(app, "user1@example.com", "잠금체크")
        login_as("user1@example.com")
        # 글쓰기 폼에서 숨김
        sel = client.get("/community/write").get_data(as_text=True) \
            .split('id="board-select"', 1)[1].split("</select>", 1)[0]
        assert "자유게시판" not in sel
        # 직접 POST도 차단
        r = _write(client, category="자유게시판", title="잠긴 카테고리 글")
        assert "관리자만 작성" in r.get_data(as_text=True)
        with app.app_context():
            assert CommunityPost.query.filter_by(title="잠긴 카테고리 글").count() == 0
        # 잠금 해제하면 정상 작성
        self._lock(app, "free", False)
        assert _write(client, category="자유게시판", title="해제 후 글").status_code == 302

    def test_cats_group_editable_in_admin(self, client, login_as):
        login_as("admin@angimo.kr")
        html = client.get("/admin/boards").get_data(as_text=True)
        assert "커뮤니티 카테고리" in html and "자유게시판" in html


class TestLawyerRandomOrder:
    """일반 변호사 목록 — 방문마다 랜덤, 같은 시드로는 페이지 이어짐."""

    @staticmethod
    def _names(html):
        import re
        area = html.split("plain-label", 1)[1] if "plain-label" in html else html
        return re.findall(r"<b>([가-힣]+) 변호사</b>", area)

    def test_same_seed_is_stable_and_paginates(self, client):
        import re
        h1 = client.get("/lawyers/?seed=42").get_data(as_text=True)
        h2 = client.get("/lawyers/?seed=42").get_data(as_text=True)
        names1 = re.findall(r"([가-힣]{2,4}) 변호사", h1.split("LAWYERS", 1)[1]) if "LAWYERS" in h1 else []
        names2 = re.findall(r"([가-힣]{2,4}) 변호사", h2.split("LAWYERS", 1)[1]) if "LAWYERS" in h2 else []
        assert names1 and names1 == names2  # 같은 시드 = 같은 순서
        # 더보기 링크에 시드가 이어진다
        if "more-btn" in h1:
            assert "seed=42" in h1.split('class="more-btn"', 1)[1][:200]


class TestAdminOnlyBoards:
    """공지·FAQ 게시판은 관리자만 작성."""

    def test_user_cannot_write(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "일반유저")
        login_as("user1@example.com")
        r = _write(client, category="안기모 공지사항", title="사칭 공지")
        assert "관리자만 작성" in r.get_data(as_text=True)
        with app.app_context():
            assert CommunityPost.query.filter_by(title="사칭 공지").count() == 0

    def test_board_page_has_no_duplicate_write_button(self, app, client, login_as):
        """글쓰기 진입은 헤더 [글쓰기 ▾] 하나 — 게시판 헤드 버튼 제거."""
        _set_nickname(app, "user1@example.com", "버튼체커")
        login_as("user1@example.com")
        html = client.get("/community/board/market").get_data(as_text=True)
        head = html.split('class="page-head"', 1)[1].split("</div></div>", 1)[0]
        assert "btn-write" not in head

    def test_write_form_groups_boards(self, app, client, login_as):
        """게시판 선택은 그룹(optgroup) 구조 — 커뮤니티/메뉴 그룹별."""
        _set_nickname(app, "user1@example.com", "폼체커")
        login_as("user1@example.com")
        html = client.get("/community/write").get_data(as_text=True)
        sel = html.split('id="board-select"', 1)[1].split("</select>", 1)[0]
        for grp in ('optgroup label="커뮤니티"', 'optgroup label="양식 자료실"',
                    'optgroup label="교정시설 정보"', 'optgroup label="변호사 상담"'):
            assert grp in sel, grp
        assert "자유게시판" in sel and "안기모 중고세상" in sel

    def test_board_select_hides_admin_boards_from_user(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "일반유저2")
        login_as("user1@example.com")
        html = client.get("/community/write").get_data(as_text=True)
        sel = html.split('id="board-select"', 1)[1].split("</select>", 1)[0]
        assert "안기모 공지사항" not in sel and "자주 묻는 질문 FAQ" not in sel
        assert "안기모 중고세상" in sel

    def test_admin_can_write(self, app, client, login_as):
        login_as("admin@angimo.kr")
        assert _write(client, category="안기모 공지사항", title="정식 공지").status_code == 302
        html = client.get("/community/board/notice-angimo").get_data(as_text=True)
        assert "정식 공지" in html


class TestBoardAdmin:
    """어드민 게시판 관리 — 상위/하위 추가·수정·삭제가 화면에 반영."""

    def _group_id(self, app, label="커뮤니티"):
        from models import CommunityBoard

        with app.app_context():
            return CommunityBoard.query.filter_by(label=label, parent_id=None).first().id

    def test_admin_page_lists_tree(self, client, login_as):
        login_as("admin@angimo.kr")
        html = client.get("/admin/boards").get_data(as_text=True)
        assert "안기모 중고세상" in html and "/community/board/market" in html
        assert "도움되는 사이트" in html

    def test_add_board_appears_everywhere(self, app, client, login_as):
        login_as("admin@angimo.kr")
        gid = self._group_id(app)
        r = client.post("/admin/boards/new", data={
            "parent_id": gid, "label": "면회 후기", "slug": "visit-review",
            "topics": "", "admin_only": "0", "show_topics": "1",
            "sort_order": "99", "is_active": "1"})
        assert r.status_code == 302
        assert client.get("/community/board/visit-review").status_code == 200
        # 커뮤니티 좌측 메뉴에 반영
        side = client.get("/community/").get_data(as_text=True) \
            .split('class="side-menu"', 1)[1].split("</aside>", 1)[0]
        assert "면회 후기" in side

    def test_edit_and_deactivate(self, app, client, login_as):
        from models import CommunityBoard

        login_as("admin@angimo.kr")
        gid = self._group_id(app)
        client.post("/admin/boards/new", data={
            "parent_id": gid, "label": "임시 게시판", "slug": "temp-b",
            "topics": "주제A, 주제B", "admin_only": "0", "show_topics": "1",
            "sort_order": "0", "is_active": "1"})
        with app.app_context():
            bid = CommunityBoard.query.filter_by(slug="temp-b").first().id
        # 비활성 → 404 + 메뉴 미노출
        client.post(f"/admin/boards/{bid}/edit", data={
            "parent_id": gid, "label": "임시 게시판", "slug": "temp-b",
            "topics": "", "admin_only": "0", "show_topics": "1",
            "sort_order": "0", "is_active": "0"})
        assert client.get("/community/board/temp-b").status_code == 404
        assert "임시 게시판" not in client.get("/").get_data(as_text=True)

    def test_delete_board(self, app, client, login_as):
        from models import CommunityBoard

        login_as("admin@angimo.kr")
        gid = self._group_id(app)
        client.post("/admin/boards/new", data={
            "parent_id": gid, "label": "삭제 대상", "slug": "to-del",
            "topics": "", "admin_only": "0", "show_topics": "1",
            "sort_order": "0", "is_active": "1"})
        with app.app_context():
            bid = CommunityBoard.query.filter_by(slug="to-del").first().id
        assert client.post(f"/admin/boards/{bid}/delete").status_code == 302
        assert client.get("/community/board/to-del").status_code == 404

    def test_group_with_children_cannot_delete(self, app, client, login_as):
        login_as("admin@angimo.kr")
        gid = self._group_id(app)
        client.post(f"/admin/boards/{gid}/delete", follow_redirects=False)
        # 여전히 존재
        assert client.get("/community/board/market").status_code == 200

    def test_duplicate_slug_rejected(self, app, client, login_as):
        from models import CommunityBoard

        login_as("admin@angimo.kr")
        gid = self._group_id(app)
        client.post("/admin/boards/new", data={
            "parent_id": gid, "label": "중복 시도", "slug": "market",
            "topics": "", "admin_only": "0", "show_topics": "1",
            "sort_order": "0", "is_active": "1"})
        with app.app_context():
            assert CommunityBoard.query.filter_by(slug="market").count() == 1

    def test_non_admin_blocked(self, client, login_as):
        login_as("user1@example.com")
        assert client.get("/admin/boards").status_code == 403

    def test_topics_via_multiple_inputs(self, app, client, login_as):
        """[+ 주제 추가] 행 다중 입력 — getlist로 수집되고 주제 칩에 반영."""
        from models import CommunityBoard

        login_as("admin@angimo.kr")
        gid = self._group_id(app)
        client.post("/admin/boards/new", data={
            "parent_id": gid, "label": "주제행 게시판", "slug": "topic-rows",
            "topics": ["주제하나", "주제둘", "주제하나"],  # 다중 입력 + 중복
            "admin_only": "0", "show_topics": "1", "sort_order": "0", "is_active": "1"})
        with app.app_context():
            b = CommunityBoard.query.filter_by(slug="topic-rows").first()
            assert b.topics == ["주제하나", "주제둘"]  # 중복 제거·순서 유지
        html = client.get("/community/board/topic-rows").get_data(as_text=True)
        assert "주제하나" in html and "주제둘" in html


class TestSideMenu:
    """커뮤니티 좌측 게시판 메뉴 (PC) — 카테고리 + DB 게시판 트리."""

    def test_side_menu_on_list_and_board(self, client, login_as):
        login_as("user1@example.com")
        for path in ("/community/", "/community/board/market"):
            html = client.get(path).get_data(as_text=True)
            side = html.split('class="side-menu"', 1)[1].split("</aside>", 1)[0]
            for label in ("전체", "인기", "자유게시판", "상담소", "양식 자료실",
                          "안기모 중고세상", "도움되는 사이트",
                          # 공지사항 그룹에 통합된 3종 (안내 그룹 통합 회귀 방지)
                          "광고 및 협업 문의", "안기모 공지사항", "커뮤니티 공지사항"):
                assert label in side, (path, label)

    def test_side_menu_marks_active(self, client, login_as):
        login_as("user1@example.com")
        html = client.get("/community/board/market").get_data(as_text=True)
        side = html.split('class="side-menu"', 1)[1].split("</aside>", 1)[0]
        import re
        on = re.findall(r'class="on"[^>]*>([^<]+)', side)
        assert [t.strip() for t in on] == ["안기모 중고세상"]


class TestBoardNotice:
    """공지 등록 시 대상 게시판 선택 — 메인 전체 또는 특정 게시판 상단 고정."""

    def test_notice_to_specific_board(self, client, login_as):
        login_as("admin@angimo.kr")
        client.post("/admin/community", data={
            "board": "안기모 중고세상", "title": "중고세상 거래 규칙", "content": "내용"})
        # 해당 게시판 상단에 고정
        html = client.get("/community/board/market").get_data(as_text=True)
        assert "중고세상 거래 규칙" in html and 'class="pcat notice"' in html
        # 커뮤니티 메인·다른 게시판에는 안 뜬다
        assert "중고세상 거래 규칙" not in client.get("/community/").get_data(as_text=True)
        assert "중고세상 거래 규칙" not in client.get("/community/board/ask").get_data(as_text=True)

    def test_notice_default_goes_to_main(self, client, login_as):
        login_as("admin@angimo.kr")
        client.post("/admin/community", data={"title": "메인 전체 공지", "content": "내용"})
        assert "메인 전체 공지" in client.get("/community/").get_data(as_text=True)

    def test_admin_form_has_board_select_toggle(self, client, login_as):
        login_as("admin@angimo.kr")
        html = client.get("/admin/community").get_data(as_text=True)
        assert 'id="notice-form" hidden' in html  # 기본 접힘, 버튼으로 토글
        sel = html.split('name="board"', 1)[1].split("</select>", 1)[0]
        assert "커뮤니티 메인" in sel and "안기모 중고세상" in sel


class TestNicknameRule:
    def test_write_get_triggers_modal(self, client, login_as):
        login_as("user2@example.com")  # 시드: 닉네임 없음
        html = client.get("/community/write").get_data(as_text=True)
        assert 'data-need-nickname="1"' in html

    def test_write_post_blocked_without_nickname(self, app, client, login_as):
        login_as("user2@example.com")
        r = _write(client)
        assert "닉네임을 먼저 설정해주세요" in r.get_data(as_text=True)
        with app.app_context():
            assert CommunityPost.query.filter_by(title="커뮤 글").count() == 0

    def test_admin_writes_without_nickname(self, client, login_as):
        login_as("admin@angimo.kr")
        assert _write(client, title="관리자 글").status_code == 302


class TestWrite:
    def test_create_masking_anonymous(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, title="익명글 010-2222-3333", is_anonymous="1")
        assert r.status_code == 302
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert "010-****-3333" in html
        assert ">익명<" in html and "테스트닉넴" not in html  # 익명 글 닉네임 미노출 (§11)

    def test_lawyer_403(self, client, login_as):
        login_as("lawyer1@angimo.kr")
        assert client.get("/community/write").status_code == 403

    def test_anon_redirect(self, client):
        r = client.get("/community/write", follow_redirects=False)
        assert r.status_code == 302 and "/login" in r.headers["Location"]

    def test_bad_category_rejected(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, category="없는게시판")
        assert "게시판/제목/내용을 확인해주세요" in r.get_data(as_text=True)

    def test_topic_category_saved(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, category="탄원서", title="탄원서 팁")
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            assert db.session.get(CommunityPost, pid).category == "탄원서"
        # 양식 자료실 보드에 노출
        assert "탄원서 팁" in client.get("/community/board/forms").get_data(as_text=True)


class TestAttachments:
    def _login(self, app, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        return login_as("user1@example.com")

    def test_upload_saved(self, app, client, login_as, sample_file):
        uid = self._login(app, login_as)
        r = _write(client, title="첨부 글",
                   files=[sample_file("사진.png"), sample_file("양식.pdf", b"%PDF-1.4")])
        assert r.status_code == 302
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            atts = db.session.get(CommunityPost, pid).attachments
            assert len(atts) == 2
            assert atts[0]["name"] == "사진.png"  # 표시명은 원본 유지
            assert atts[0]["url"].startswith(f"/uploads/community/{uid}/")
            assert "사진" not in atts[0]["url"]  # 저장 파일명은 uuid
            fname = atts[0]["url"].split("/")[-1]
            assert os.path.exists(os.path.join(
                app.config["UPLOAD_FOLDER"], "community", str(uid), fname))
        # 상세: 이미지는 본문 아래 인라인 <img>, 일반 파일은 다운로드 링크
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        with app.app_context():
            img_url, pdf_name = atts[0]["url"], atts[1]["name"]
        assert f'<img src="{img_url}"' in html  # 이미지 인라인 표시
        assert pdf_name in html and "attach-list" in html  # pdf는 링크 유지
        assert client.get(img_url).status_code == 200  # 공개 서빙

    def test_bad_extension_rejected(self, app, client, login_as, sample_file):
        self._login(app, login_as)
        r = _write(client, title="악성 글", files=[sample_file("virus.exe", b"MZ")])
        assert "첨부할 수 없는 파일 형식" in r.get_data(as_text=True)
        with app.app_context():
            assert CommunityPost.query.filter_by(title="악성 글").count() == 0

    def test_max_5_attachments(self, app, client, login_as, sample_file):
        self._login(app, login_as)
        files = [sample_file(f"f{i}.png") for i in range(6)]
        r = _write(client, title="첨부 6개", files=files)
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            assert len(db.session.get(CommunityPost, pid).attachments) == 5


class TestComments:
    def _post_id(self, app, client, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, title="댓글 대상 글")
        return int(r.headers["Location"].rstrip("/").split("/")[-1])

    def test_comment_and_reply(self, app, client, login_as):
        pid = self._post_id(app, client, login_as)
        r = client.post(f"/community/{pid}/comments", data={"content": "첫 댓글"},
                        follow_redirects=True)
        assert "첫 댓글" in r.get_data(as_text=True)
        from models import CommunityComment
        with app.app_context():
            cmt = CommunityComment.query.filter_by(post_id=pid).first()
        r = client.post(f"/community/{pid}/comments",
                        data={"content": "대댓글", "parent_id": cmt.id}, follow_redirects=True)
        assert "대댓글" in r.get_data(as_text=True)
        # 대댓글의 대댓글(2-depth)은 400
        with app.app_context():
            reply = CommunityComment.query.filter_by(post_id=pid, parent_id=cmt.id).first()
        r = client.post(f"/community/{pid}/comments",
                        data={"content": "3단계", "parent_id": reply.id})
        assert r.status_code == 400

    def test_empty_comment_rejected(self, app, client, login_as):
        pid = self._post_id(app, client, login_as)
        r = client.post(f"/community/{pid}/comments", data={"content": " "},
                        follow_redirects=True)
        assert "댓글 내용을 입력해주세요" in r.get_data(as_text=True)

    def test_lawyer_comment_403(self, app, client, login_as):
        pid = self._post_id(app, client, login_as)
        login_as("lawyer1@angimo.kr")
        assert client.post(f"/community/{pid}/comments",
                           data={"content": "변호사 댓글"}).status_code == 403


class TestOwnPost:
    """내 글 수정/삭제 — 언제든 가능."""

    def _mine(self, app, client, login_as, title="수정 대상 커뮤 글"):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, title=title)
        return int(r.headers["Location"].rstrip("/").split("/")[-1])

    def test_owner_sees_actions(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert "own-actions" in html and f"/community/{pid}/edit" in html

    def test_edit(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        r = client.post(f"/community/{pid}/edit", data={
            "category": "옥바라지 이야기", "title": "수정된 제목", "content": "수정된 본문",
        }, content_type="multipart/form-data", follow_redirects=True)
        assert "글이 수정되었습니다" in r.get_data(as_text=True)
        with app.app_context():
            p = db.session.get(CommunityPost, pid)
            assert p.title == "수정된 제목" and p.category == "옥바라지 이야기"

    def test_edit_allowed_with_comments(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        client.post(f"/community/{pid}/comments", data={"content": "댓글"})
        r = client.post(f"/community/{pid}/edit", data={
            "category": "자유게시판", "title": "댓글 있어도 수정", "content": "c",
        }, content_type="multipart/form-data", follow_redirects=True)
        assert "글이 수정되었습니다" in r.get_data(as_text=True)

    def test_edit_removes_attachment(self, app, client, login_as, sample_file):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        login_as("user1@example.com")
        r = _write(client, title="첨부 수정 글",
                   files=[sample_file("a.png"), sample_file("b.pdf", b"%PDF-1.4")])
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            remove_url = db.session.get(CommunityPost, pid).attachments[0]["url"]
        client.post(f"/community/{pid}/edit", data={
            "category": "자유게시판", "title": "첨부 수정 글", "content": "c",
            "remove_attachments": remove_url,
        }, content_type="multipart/form-data")
        with app.app_context():
            atts = db.session.get(CommunityPost, pid).attachments
            assert len(atts) == 1 and atts[0]["name"] == "b.pdf"

    def test_delete_soft(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        r = client.post(f"/community/{pid}/delete", follow_redirects=True)
        assert "글이 삭제되었습니다" in r.get_data(as_text=True)
        with app.app_context():
            p = db.session.get(CommunityPost, pid)
            assert p.status == "deleted" and p.deleted_at is not None
        assert client.get(f"/community/{pid}").status_code == 404

    def test_others_cannot_edit_or_delete(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        _set_nickname(app, "user3@example.com", "다른유저닉")
        login_as("user3@example.com")
        assert client.get(f"/community/{pid}/edit").status_code == 404
        assert client.post(f"/community/{pid}/delete").status_code == 404
        # 타인 화면에는 수정/삭제 버튼 미노출
        assert "own-actions" not in client.get(f"/community/{pid}").get_data(as_text=True)

    def test_anon_redirects(self, app, client, login_as):
        pid = self._mine(app, client, login_as)
        client.get("/logout")
        assert client.get(f"/community/{pid}/edit", follow_redirects=False).status_code == 302


class TestBodyEditor:
    """본문 이미지 간이 에디터 — 업로드 API + [img] 토큰 렌더."""

    def _login(self, app, login_as):
        _set_nickname(app, "user1@example.com", "테스트닉넴")
        return login_as("user1@example.com")

    def test_upload_image(self, app, client, login_as, sample_file):
        uid = self._login(app, login_as)
        r = client.post("/community/upload-image", data={"image": sample_file("body.png")},
                        content_type="multipart/form-data")
        assert r.status_code == 200
        url = r.get_json()["url"]
        assert url.startswith(f"/uploads/community/{uid}/")
        assert client.get(url).status_code == 200  # 공개 서빙

    def test_upload_bad_ext(self, app, client, login_as, sample_file):
        self._login(app, login_as)
        r = client.post("/community/upload-image", data={"image": sample_file("x.gif", b"GIF89a")},
                        content_type="multipart/form-data")
        assert r.status_code == 400 and r.get_json()["error"]["code"] == "INVALID_TYPE"

    def test_upload_requires_login(self, client, sample_file):
        r = client.post("/community/upload-image", data={"image": sample_file()},
                        content_type="multipart/form-data", follow_redirects=False)
        assert r.status_code == 302

    def test_lawyer_403(self, client, login_as, sample_file):
        login_as("lawyer1@angimo.kr")
        r = client.post("/community/upload-image", data={"image": sample_file()},
                        content_type="multipart/form-data")
        assert r.status_code == 403

    def test_body_token_renders_img(self, app, client, login_as):
        uid = self._login(app, login_as)
        body = f"첫 줄입니다\n[img]/uploads/community/{uid}/demo.png[/img]\n마지막 줄"
        r = _write(client, title="에디터 본문 글", content=body)
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        html = client.get(f"/community/{pid}").get_data(as_text=True)
        assert f'<img class="body-img" src="/uploads/community/{uid}/demo.png"' in html
        assert "[img]" not in html.split("comm-detail")[1].split("cmt-sec")[0]

    def test_external_token_stripped(self, app, client, login_as):
        self._login(app, login_as)
        r = _write(client, title="외부 이미지 글", content="본문 [img]https://evil.com/x.png[/img] 끝")
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        with app.app_context():
            content = db.session.get(CommunityPost, pid).content
        assert "evil.com" not in content

    def test_first_image_from_body(self, app, client, login_as):
        uid = self._login(app, login_as)
        _write(client, title="본문 이미지 썸네일 글",
               content=f"글\n[img]/uploads/community/{uid}/thumb.png[/img]")
        # 목록 썸네일에 본문 이미지 사용 + 미리보기 텍스트에 토큰 미노출
        html = client.get("/community/").get_data(as_text=True)
        assert f"/uploads/community/{uid}/thumb.png" in html
        assert "[img]" not in html


class TestHidden:
    def test_hidden_post_404_except_admin(self, app, client, login_as):
        with app.app_context():
            p = CommunityPost.query.filter_by(status="open", is_notice=False).first()
            p.status = "hidden"
            db.session.commit()
            pid = p.id
        login_as("user1@example.com")
        assert client.get(f"/community/{pid}").status_code == 404
        login_as("admin@angimo.kr")
        assert client.get(f"/community/{pid}").status_code == 200
