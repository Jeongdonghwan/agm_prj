from sqlalchemy import func
from sqlalchemy.dialects.mysql import ENUM

from extensions import db


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    name = db.Column(db.String(50))
    description = db.Column(db.String(150))
    sort_order = db.Column(db.Integer, default=0)

    children = db.relationship("Category", remote_side=[parent_id], viewonly=True)
    parent = db.relationship("Category", remote_side=[id])


class Region(db.Model):
    __tablename__ = "regions"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30))
    sort_order = db.Column(db.Integer)


class Banner(db.Model):
    __tablename__ = "banners"

    id = db.Column(db.Integer, primary_key=True)
    position = db.Column(ENUM("main_hero", "main_side", "popup"), default="main_hero")
    title = db.Column(db.String(100))
    image_url = db.Column(db.String(300))
    link_url = db.Column(db.String(300))
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)


class LawyerAd(db.Model):
    """변호사 목록 광고 — 어느 분야(카테고리)에 누구를 어느 슬롯으로 노출할지."""

    __tablename__ = "lawyer_ads"

    id = db.Column(db.Integer, primary_key=True)
    lawyer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # (구) 단일 분야 — category_ids로 대체, 데이터 이전 후 미사용
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    # 노출 분야 id 배열 — 비었거나 NULL이면 전체 노출
    category_ids = db.Column(db.JSON)
    slot = db.Column(ENUM("photocard", "adlist"), default="photocard")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)

    lawyer = db.relationship("User")
    category = db.relationship("Category")


class FirmAd(db.Model):
    __tablename__ = "firm_ads"

    id = db.Column(db.Integer, primary_key=True)
    firm_name = db.Column(db.String(100))
    headline = db.Column(db.String(200))
    description = db.Column(db.Text)
    links = db.Column(db.JSON)
    photos = db.Column(db.JSON)
    address = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"))
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)

    category = db.relationship("Category")


class FirmInquiry(db.Model):
    __tablename__ = "firm_inquiries"

    id = db.Column(db.Integer, primary_key=True)
    firm_ad_id = db.Column(db.Integer, db.ForeignKey("firm_ads.id"))
    name = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    content = db.Column(db.String(1000))
    status = db.Column(ENUM("new", "processed"), default="new")
    created_at = db.Column(db.DateTime, server_default=func.now())

    firm_ad = db.relationship("FirmAd")


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    target_type = db.Column(
        ENUM("community_post", "community_comment", "consultation", "answer")
    )
    target_id = db.Column(db.Integer)
    reason = db.Column(db.String(300))
    status = db.Column(ENUM("new", "done"), default="new")
    created_at = db.Column(db.DateTime, server_default=func.now())

    reporter = db.relationship("User")


class AdminLog(db.Model):
    __tablename__ = "admin_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(60))
    target = db.Column(db.String(100))
    detail = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, server_default=func.now())

    admin = db.relationship("User")
