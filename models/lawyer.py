from sqlalchemy import func

from extensions import db

lawyer_categories = db.Table(
    "lawyer_categories",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column(
        "category_id", db.Integer, db.ForeignKey("categories.id"), primary_key=True
    ),
)


class LawyerProfile(db.Model):
    __tablename__ = "lawyer_profiles"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), primary_key=True)
    license_no = db.Column(db.String(30), nullable=False)
    headline = db.Column(db.String(100))  # 프로필 대제목
    firm_name = db.Column(db.String(100))
    bar_association = db.Column(db.String(50))
    photo_url = db.Column(db.String(300))
    office_phone = db.Column(db.String(30))  # 연락 수단(카카오와 둘 중 하나 필수)
    kakao_url = db.Column(db.String(300))
    address = db.Column(db.String(200))
    intro_full = db.Column(db.Text)
    career = db.Column(db.JSON)  # [{year,text}]
    region_id = db.Column(db.Integer, db.ForeignKey("regions.id"))
    view_count = db.Column(db.Integer, default=0)
    contact_click_count = db.Column(db.Integer, default=0)  # 전화/카톡 클릭 합산
    is_visible = db.Column(db.Boolean, default=True)
    show_in_new = db.Column(db.Boolean, default=True)  # 메인 '새로 함께하는 변호사' 노출
    approved_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="lawyer_profile")
    region = db.relationship("Region")
    # 조인테이블 FK는 users.id를 가리키므로 조인 조건 명시 필요
    categories = db.relationship(
        "Category",
        secondary=lawyer_categories,
        primaryjoin="LawyerProfile.user_id == foreign(lawyer_categories.c.user_id)",
        secondaryjoin="Category.id == foreign(lawyer_categories.c.category_id)",
        viewonly=False,
    )

    @property
    def is_complete(self) -> bool:
        """필수 필드(사진·헤드라인·분야·연락처) 완성 여부 — 미완성 시 목록 미노출."""
        return bool(
            self.photo_url
            and self.headline
            and self.categories
            and (self.office_phone or self.kakao_url)
        )


class LawyerVerificationFile(db.Model):
    __tablename__ = "lawyer_verification_files"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    file_url = db.Column(db.String(300))
    file_type = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, server_default=func.now())

    user = db.relationship("User")
