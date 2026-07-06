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
