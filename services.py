"""메인 페이지 섹션 데이터 — 하나의 서비스 함수로 일괄 조회 (§2-2)."""

from datetime import datetime, timedelta

from sqlalchemy.orm import joinedload

from extensions import db
from models import (
    Banner,
    Category,
    CommunityPost,
    Consultation,
    ConsultationAnswer,
    LawyerPost,
    LawyerProfile,
    LegalCase,
    Region,
    User,
)

# 분야 그리드 아이콘 매핑 (대분류 14종 — 이름은 seed CATEGORIES와 일치)
CATEGORY_ICONS = [
    ("형사일반", "criminal", "#EFE9FF"),
    ("성범죄", "sex-crime", "#FFE9EE"),
    ("폭행/협박/모욕", "assault", "#FFEDE3"),
    ("절도/사기", "etc-criminal", "#F0F1F5"),
    ("교통", "traffic", "#E4EEFF"),
    ("민사일반", "etc-civil", "#EDF1FF"),
    ("금전/손해배상", "contract", "#FFF8D9"),
    ("부동산/임대차", "realestate", "#E2F5FF"),
    ("이혼/가족", "family", "#FFE8F3"),
    ("기업/노동", "company", "#E7EFFE"),
    ("의료", "medical", "#E4FAF7"),
    ("세금/행정", "civil", "#E7FBF2"),
    ("금융/보험", "property", "#FFF3DF"),
    ("IT/지적재산", "it", "#F3E9FF"),
]


def _parse_banner(b):
    """배너 title 규칙: '메인카피|포인트카피(파란 줄)|서브카피' — 배너관리에서 그대로 입력."""
    parts = (b.title or "").split("|")
    return {
        "main": parts[0].strip() if parts else "",
        "point": parts[1].strip() if len(parts) > 1 else "",
        "sub": parts[2].strip() if len(parts) > 2 else "",
        "image": b.image_url,
        "link": b.link_url,
    }


def get_home_data():
    now = datetime.now()

    # 메인 사이드 롤링 배너 (B안 우측 EVENT 슬롯)
    side_banners = [
        _parse_banner(b)
        for b in Banner.query.filter(
            Banner.position == "main_side",
            Banner.is_active.is_(True),
            db.or_(Banner.starts_at.is_(None), Banner.starts_at <= now),
            db.or_(Banner.ends_at.is_(None), Banner.ends_at >= now),
        )
        .order_by(Banner.sort_order)
        .limit(4)
        .all()
    ]

    # 히어로 롤링 배너 (배너 관리 연동, sort_order 순)
    hero_banners = [
        _parse_banner(b)
        for b in Banner.query.filter(
            Banner.position == "main_hero",
            Banner.is_active.is_(True),
            db.or_(Banner.starts_at.is_(None), Banner.starts_at <= now),
            db.or_(Banner.ends_at.is_(None), Banner.ends_at >= now),
        )
        .order_by(Banner.sort_order)
        .limit(6)
        .all()
    ]

    # 탭1: 커뮤니티 인기글 6 (조회+추천×3)
    hot_community = (
        CommunityPost.query.filter_by(status="open", is_notice=False)
        .filter(CommunityPost.deleted_at.is_(None))
        .options(joinedload(CommunityPost.comments))
        .order_by((CommunityPost.views + CommunityPost.likes * 3).desc())
        .limit(6)
        .all()
    )

    # 탭2: 판례돋보기 4
    recent_cases = (
        LegalCase.query.filter(LegalCase.deleted_at.is_(None))
        .order_by(LegalCase.created_at.desc())
        .limit(4)
        .all()
    )
    cat_names = {c.id: c.name for c in Category.query.all()}

    # 탭3: 최신 상담글 4 (공개, 답변 변호사 이니셜)
    recent_consults = (
        Consultation.query.filter_by(status="open", is_public=True)
        .filter(Consultation.deleted_at.is_(None))
        .options(joinedload(Consultation.category), joinedload(Consultation.answers))
        .order_by(Consultation.created_at.desc())
        .limit(4)
        .all()
    )
    answer_lawyer_ids = {
        a.lawyer_id for c in recent_consults for a in c.answers if not a.deleted_at
    }
    lawyer_initials = {
        u.id: (u.name[0] if u.name else "변")
        for u in User.query.filter(User.id.in_(answer_lawyer_ids or [0]))
    }

    # 탭4: 변호사 해결사례 4
    solve_posts = (
        LawyerPost.query.filter_by(type="case", status="published")
        .filter(LawyerPost.deleted_at.is_(None))
        .options(joinedload(LawyerPost.lawyer))
        .order_by(LawyerPost.published_at.desc())
        .limit(4)
        .all()
    )

    # 분야 그리드: 이름 → Category id 매핑
    parent_ids = {
        c.name: c.id for c in Category.query.filter_by(parent_id=None).all()
    }
    categories = [
        {"name": name, "icon": icon, "bg": bg, "id": parent_ids.get(name)}
        for name, icon, bg in CATEGORY_ICONS
    ]

    regions = Region.query.order_by(Region.sort_order).all()

    # 지금 법률전문가와 상담하기 — 최근 30일 답변수 상위 (가로 슬라이더)
    since = datetime.now() - timedelta(days=30)
    active_rows = (
        db.session.query(
            ConsultationAnswer.lawyer_id,
            db.func.count(ConsultationAnswer.id).label("cnt"),
        )
        .filter(ConsultationAnswer.created_at >= since, ConsultationAnswer.deleted_at.is_(None))
        .group_by(ConsultationAnswer.lawyer_id)
        .order_by(db.text("cnt DESC"))
        .limit(10)
        .all()
    )
    profiles_by_id = {
        p.user_id: p
        for p in LawyerProfile.query.options(
            joinedload(LawyerProfile.user), joinedload(LawyerProfile.categories)
        ).filter(LawyerProfile.user_id.in_([r[0] for r in active_rows] or [0]))
    }
    active_lawyers = [
        {"profile": profiles_by_id[lid], "answers": cnt}
        for lid, cnt in active_rows
        if lid in profiles_by_id
    ]

    # 새로 함께하는 변호사 — 최근 승인 순, 관리자 노출 설정(show_in_new) 반영 (가로 슬라이더)
    new_lawyers = (
        LawyerProfile.query.join(User, LawyerProfile.user_id == User.id)
        .filter(
            User.status == "active",
            LawyerProfile.is_visible.is_(True),
            LawyerProfile.show_in_new.is_(True),
        )
        .options(joinedload(LawyerProfile.user), joinedload(LawyerProfile.categories))
        .order_by(LawyerProfile.approved_at.desc())
        .limit(12)
        .all()
    )

    return {
        "hero_banners": hero_banners,
        "side_banners": side_banners,
        "hot_community": hot_community,
        "recent_cases": recent_cases,
        "cat_names": cat_names,
        "recent_consults": recent_consults,
        "lawyer_initials": lawyer_initials,
        "solve_posts": solve_posts,
        "categories": categories,
        "regions": regions,
        "active_lawyers": active_lawyers,
        "new_lawyers": new_lawyers,
    }
