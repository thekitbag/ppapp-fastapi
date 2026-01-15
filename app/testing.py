from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base


def is_test_mode() -> bool:
    return os.getenv("PPAPP_TEST_MODE") == "1"


def configure_test_overrides(app: FastAPI) -> None:
    from app.api.v1.auth import get_current_user_dep
    from app.db import get_db as real_get_db
    from app.models import ProviderEnum, User

    test_engine = create_engine(
        "sqlite:///./test.db",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def ensure_user(db, *, user_id: str, provider_sub: str, email: str, name: str) -> None:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            return
        db.add(
            User(
                id=user_id,
                provider=ProviderEnum.google,
                provider_sub=provider_sub,
                email=email,
                name=name,
            )
        )
        db.commit()

    with TestingSessionLocal() as db:
        ensure_user(
            db,
            user_id="user_test",
            provider_sub="test_sub",
            email="test@example.com",
            name="Test User",
        )
        ensure_user(
            db,
            user_id="user_other",
            provider_sub="test_other_sub",
            email="other@example.com",
            name="Other User",
        )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_current_user_dep(request: Request):
        user_id = request.headers.get("x-test-user-id") or "user_test"
        if user_id == "user_other":
            return {
                "user_id": "user_other",
                "email": "other@example.com",
                "name": "Other User",
                "provider": "google",
            }
        return {
            "user_id": "user_test",
            "email": "test@example.com",
            "name": "Test User",
            "provider": "google",
        }

    app.dependency_overrides[real_get_db] = override_get_db
    app.dependency_overrides[get_current_user_dep] = override_current_user_dep
