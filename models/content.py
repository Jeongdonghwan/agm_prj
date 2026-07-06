from sqlalchemy import func
from sqlalchemy.dialects.mysql import ENUM, MEDIUMTEXT

from extensions import db


class LawyerPost(db.Model):
    __tablename__ = "lawyer_posts"

    id = db.Column(db.Integer, primary_key=True)
    lawyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    type = db.Column(ENUM("case", "guide", "video", "essay"))
    title = db.Column(db.String(200))
    content = db.Column(MEDIUMTEXT)
    thumbnail_url = db.Column(db.String(300))
    result_badge = db.Column(db.String(30))  # 해결사례용: 무죄/집행유예 등
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    views = db.Column(db.Integer, default=0)
    status = db.Column(
        ENUM("pending", "published", "rejected", "hidden"), default="pending"
    )
    reject_reason = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, server_default=func.now())
    published_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)

    lawyer = db.relationship("User")
    category = db.relationship("Category")


class LegalCase(db.Model):
    """판례돋보기 (관리자 직접 CRUD)."""

    __tablename__ = "legal_cases"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    summary = db.Column(db.String(500))
    content = db.Column(MEDIUMTEXT)
    court = db.Column(db.String(50))
    case_no = db.Column(db.String(60))
    case_type = db.Column(
        ENUM("criminal", "civil", "administrative", "constitutional", "patent")
    )
    category_ids = db.Column(db.JSON)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, server_default=func.now())
    deleted_at = db.Column(db.DateTime)


class News(db.Model):
    """안기모뉴스 (관리자 직접 CRUD)."""

    __tablename__ = "news"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    content = db.Column(MEDIUMTEXT)
    thumbnail_url = db.Column(db.String(300))
    hashtags = db.Column(db.JSON)
    reporter = db.Column(db.String(50))
    views = db.Column(db.Integer, default=0)
    published_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, server_default=func.now())
    deleted_at = db.Column(db.DateTime)
