# -*- coding: utf-8 -*-
"""변호사 프로필 폼 처리 공용 헬퍼.

변호사 본인(/lawyer/profile)과 관리자 강제 수정(/admin/lawyers/<id>)이
같은 필드·같은 검증 규칙을 쓰므로 한 곳에서 관리한다. (CLAUDE.md §4-3-1)
"""
import os
import uuid

from flask import current_app, url_for

from models import Category

MAX_CATEGORIES = 7  # §4-3-1: 분야 최대 7개
PHOTO_EXTENSIONS = {"jpg", "jpeg", "png"}


def _save_photo(photo, owner_id):
    """프로필 사진 저장 → (url, error). 확장자 불일치 시 (None, 메시지)."""
    ext = photo.filename.rsplit(".", 1)[-1].lower() if "." in photo.filename else ""
    if ext not in PHOTO_EXTENSIONS:
        return None, "프로필 사진은 jpg, jpeg, png만 업로드할 수 있습니다."
    photo_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], "profiles", str(owner_id))
    os.makedirs(photo_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    photo.save(os.path.join(photo_dir, fname))
    return url_for("main.uploads", filename=f"profiles/{owner_id}/{fname}"), None


def apply_profile_form(prof, form, files, owner_id):
    """폼 값을 검증해 프로필에 반영. 오류 메시지 리스트를 반환(비면 성공).

    오류가 있으면 prof를 건드리지 않는다(호출측에서 rollback/재렌더).
    """
    errors = []

    office_phone = form.get("office_phone", "").strip()
    kakao_url = form.get("kakao_url", "").strip()
    if kakao_url and not kakao_url.startswith(("http://", "https://")):
        errors.append("카카오톡 채널 URL은 http(s)://로 시작해야 합니다.")
    if not office_phone and not kakao_url:
        errors.append("사무실 전화와 카카오톡 채널 중 하나는 반드시 입력해야 합니다.")

    category_ids = [int(v) for v in form.getlist("categories") if v.isdigit()]
    if len(category_ids) > MAX_CATEGORIES:
        errors.append(f"분야는 최대 {MAX_CATEGORIES}개까지 선택할 수 있습니다.")

    # 경력: career_year[] + career_text[] 쌍
    career = []
    for year, text in zip(form.getlist("career_year"), form.getlist("career_text")):
        year, text = year.strip(), text.strip()
        if year or text:
            career.append({"year": year, "text": text})

    photo = files.get("photo") if files else None
    photo_url = prof.photo_url
    if photo and photo.filename:
        saved, err = _save_photo(photo, owner_id)
        if err:
            errors.append(err)
        else:
            photo_url = saved

    if errors:
        return errors

    prof.headline = form.get("headline", "").strip() or None
    prof.firm_name = form.get("firm_name", "").strip() or None
    prof.bar_association = form.get("bar_association", "").strip() or None
    prof.office_phone = office_phone or None
    prof.kakao_url = kakao_url or None
    prof.address = form.get("address", "").strip() or None
    prof.intro_full = form.get("intro_full", "").strip() or None
    prof.career = career or None
    prof.region_id = form.get("region_id", type=int) or None
    prof.photo_url = photo_url
    prof.categories = (
        Category.query.filter(Category.id.in_(category_ids)).all() if category_ids else []
    )
    return []


def profile_form_context(prof):
    """분야/지역 선택지 등 폼 렌더에 필요한 공통 컨텍스트."""
    from models import Region

    parents = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    children_by_parent = {}
    for c in Category.query.filter(Category.parent_id.isnot(None)).order_by(
        Category.sort_order
    ):
        children_by_parent.setdefault(c.parent_id, []).append(c)
    return {
        "parents": parents,
        "children_by_parent": children_by_parent,
        "regions": Region.query.order_by(Region.sort_order).all(),
        "selected_ids": {c.id for c in prof.categories} if prof.categories else set(),
        "max_categories": MAX_CATEGORIES,
    }
