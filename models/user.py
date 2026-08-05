import bcrypt
from sqlalchemy import func
from sqlalchemy.dialects.mysql import ENUM

from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(50))
    nickname = db.Column(db.String(50), unique=True)  # NULL 허용, 커뮤니티 작성 시 필수
    nickname_changed_at = db.Column(db.DateTime)  # 변경 30일 제한용
    phone = db.Column(db.String(20))
    role = db.Column(ENUM("user", "lawyer", "admin"), default="user", nullable=False)
    status = db.Column(
        ENUM("active", "pending", "rejected", "suspended", "withdrawn"),
        default="active",
        nullable=False,
    )
    status_reason = db.Column(db.String(300))
    # 관리자 2단계: 메인관리자(전권)와 부관리자(admin_perms의 메뉴만)
    is_super_admin = db.Column(db.Boolean, default=False)
    admin_perms = db.Column(db.JSON)  # 부관리자 허용 메뉴 키 배열
    # 커뮤니티 승인제 (§가족 인증): 접견예약확인 캡처 제출 → 관리자 승인
    approved_at = db.Column(db.DateTime)              # NULL이면 커뮤니티 이용 불가
    visit_proof_url = db.Column(db.String(300))       # 비공개 저장 경로(admin 전용 서빙)
    visit_proof_at = db.Column(db.DateTime)           # 제출 시각
    approve_reject_reason = db.Column(db.String(300))  # 반려 사유
    created_at = db.Column(db.DateTime, server_default=func.now())
    last_login_at = db.Column(db.DateTime)
    deleted_at = db.Column(db.DateTime)

    lawyer_profile = db.relationship(
        "LawyerProfile", back_populates="user", uselist=False
    )

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"), self.password_hash.encode("utf-8")
            )
        except ValueError:
            return False

    @property
    def display_name(self) -> str:
        return self.nickname or self.name or self.email.split("@")[0]

    @property
    def community_approved(self) -> bool:
        """커뮤니티 이용 가능 여부 — 일반회원은 관리자 승인 필요, 그 외 역할은 통과."""
        return self.role != "user" or self.approved_at is not None
