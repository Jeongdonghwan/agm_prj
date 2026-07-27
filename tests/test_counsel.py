# -*- coding: utf-8 -*-
"""상담사례 Q&A — 작성/마스킹/비공개/수정·삭제 규칙/정렬."""
from extensions import db
from models import Consultation, ConsultationAnswer, User


def _write(client, title="테스트 질문", content="본문입니다", public="1"):
    return client.post("/counsel/write", data={
        "title": title, "content": content, "category_id": "1", "is_public": public,
    }, follow_redirects=False)


def _lawyer_id(app, n=1):
    with app.app_context():
        return User.query.filter_by(email=f"lawyer{n}@angimo.kr").first().id


def _add_answer(app, consult_id, lawyer_id, content="변호사 답변"):
    with app.app_context():
        db.session.add(ConsultationAnswer(
            consultation_id=consult_id, lawyer_id=lawyer_id, content=content))
        db.session.commit()


class TestList:
    def test_200_with_sorts(self, client):
        for sort in ("recent_answer", "recent", "views"):
            assert client.get(f"/counsel/?sort={sort}").status_code == 200

    def test_recent_answer_puts_answered_first(self, client):
        html = client.get("/counsel/?sort=recent_answer").get_data(as_text=True)
        # 첫 아이템은 답변 미리보기(qa-ans)가 있어야 함 — 시드 앞 3건에 답변 존재
        first_item = html.split('class="qa-item"')[1]
        assert "qa-ans" in first_item

    def test_anon_write_redirects_login(self, client):
        r = client.get("/counsel/write", follow_redirects=False)
        assert r.status_code == 302 and "/login" in r.headers["Location"]


class TestWrite:
    def test_create_and_masking(self, app, client, login_as):
        login_as("user1@example.com")
        r = _write(client, title="질문 010-1234-5678",
                   content="주민번호 900101-1234567 전화 010-9999-8888")
        assert r.status_code == 302
        cid = int(r.headers["Location"].rstrip("/").split("/")[-1].split("-")[0])
        with app.app_context():
            c = db.session.get(Consultation, cid)
            assert c.title == "질문 010-****-5678"
            assert "900101-*******" in c.content and "010-****-8888" in c.content
            assert "1234567" not in c.content

    def test_empty_title_rejected(self, app, client, login_as):
        login_as("user1@example.com")
        r = _write(client, title="", content="본문")
        assert "제목과 내용을 입력해주세요" in r.get_data(as_text=True)


class TestPrivate:
    def _private_id(self, client, login_as):
        login_as("user1@example.com")
        r = _write(client, title="비공개 질문", public="0")
        return int(r.headers["Location"].rstrip("/").split("/")[-1].split("-")[0])

    def test_owner_can_view(self, client, login_as):
        cid = self._private_id(client, login_as)
        assert client.get(f"/counsel/{cid}", follow_redirects=True).status_code == 200

    def test_anon_403(self, client, login_as):
        cid = self._private_id(client, login_as)
        client.get("/logout")
        assert client.get(f"/counsel/{cid}", follow_redirects=True).status_code == 403

    def test_other_user_403(self, client, login_as):
        cid = self._private_id(client, login_as)
        login_as("user3@example.com")
        assert client.get(f"/counsel/{cid}", follow_redirects=True).status_code == 403

    def test_lawyer_and_admin_can_view(self, client, login_as):
        cid = self._private_id(client, login_as)
        login_as("lawyer1@angimo.kr")
        assert client.get(f"/counsel/{cid}", follow_redirects=True).status_code == 200
        login_as("admin@angimo.kr")
        assert client.get(f"/counsel/{cid}", follow_redirects=True).status_code == 200

    def test_private_not_in_list(self, client, login_as):
        self._private_id(client, login_as)
        client.get("/logout")
        assert "비공개 질문" not in client.get("/counsel/").get_data(as_text=True)


class TestEditDelete:
    def _own_id(self, client, login_as, email="user1@example.com"):
        login_as(email)
        r = _write(client, title="수정 대상 질문")
        return int(r.headers["Location"].rstrip("/").split("/")[-1].split("-")[0])

    def test_edit_before_answer(self, app, client, login_as):
        cid = self._own_id(client, login_as)
        assert client.get(f"/counsel/{cid}/edit").status_code == 200
        client.post(f"/counsel/{cid}/edit", data={
            "title": "수정된 제목", "content": "수정된 본문", "is_public": "1"})
        with app.app_context():
            assert db.session.get(Consultation, cid).title == "수정된 제목"

    def test_edit_blocked_after_answer(self, app, client, login_as):
        cid = self._own_id(client, login_as)
        _add_answer(app, cid, _lawyer_id(app))
        r = client.get(f"/counsel/{cid}/edit", follow_redirects=True)
        assert "수정할 수 없습니다" in r.get_data(as_text=True)

    def test_delete_blocked_after_answer(self, app, client, login_as):
        cid = self._own_id(client, login_as)
        _add_answer(app, cid, _lawyer_id(app))
        r = client.post(f"/counsel/{cid}/delete", follow_redirects=True)
        assert "삭제할 수 없습니다" in r.get_data(as_text=True)
        with app.app_context():
            assert db.session.get(Consultation, cid).status == "open"

    def test_delete_soft(self, app, client, login_as):
        cid = self._own_id(client, login_as)
        client.post(f"/counsel/{cid}/delete")
        with app.app_context():
            c = db.session.get(Consultation, cid)
            assert c.status == "deleted" and c.deleted_at is not None
        assert client.get(f"/counsel/{cid}", follow_redirects=True).status_code == 404

    def test_others_post_edit_404(self, client, login_as):
        cid = self._own_id(client, login_as)
        login_as("user3@example.com")
        assert client.get(f"/counsel/{cid}/edit").status_code == 404


class TestDetail:
    def test_slug_301_and_views(self, app, client):
        with app.app_context():
            c = Consultation.query.filter_by(is_public=True, status="open").first()
            cid, views0 = c.id, c.views or 0
        r = client.get(f"/counsel/{cid}", follow_redirects=False)
        assert r.status_code == 301  # 슬러그 canonical 리다이렉트
        assert client.get(r.headers["Location"]).status_code == 200
        with app.app_context():
            db.session.expire_all()
            assert db.session.get(Consultation, cid).views == views0 + 1

    def test_answers_with_lawyer_card(self, app, client):
        with app.app_context():
            aid = ConsultationAnswer.query.filter(
                ConsultationAnswer.deleted_at.is_(None)).first().consultation_id
        html = client.get(f"/counsel/{aid}", follow_redirects=True).get_data(as_text=True)
        assert "변호사 답변" in html and "ans-lawyer" in html and "프로필 보기" in html
