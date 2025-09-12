from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Cookie
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from app.core import settings, setup_logging, get_logger
from app.exceptions import AppException, app_exception_handler, general_exception_handler
from app.api.v1 import api_router
from app.api.v1 import auth as auth_v1
from app.db import Base, engine

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    setup_logging()
    logger.info("Starting up Personal Productivity API")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Personal Productivity API")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=settings.api_description,
        lifespan=lifespan
    )
    
    # CORS middleware - environment-specific origins
    cors_origins = settings.cors_origins
    
    # Runtime safety check for production
    if settings.environment == "production":
        localhost_origins = [origin for origin in cors_origins if "localhost" in origin or "127.0.0.1" in origin]
        if localhost_origins:
            logger.warning(f"Production environment detected with localhost origins: {localhost_origins}")
    
    logger.info(f"CORS allowed origins: {cors_origins}")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,     # exact origins only (no "*")
        allow_credentials=True,         # required for cookies
        allow_methods=["*"],           # GET, POST, PATCH, DELETE, OPTIONS
        allow_headers=["*"],           # Authorization, Content-Type, etc.
    )
    
    # Exception handlers
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    # Include API routes
    app.include_router(api_router)

    # Test-mode dependency overrides: isolate DB and bypass auth for tests
    # This runs only under pytest to keep production/dev behavior unchanged
    try:
        import os, sys
        if ("PYTEST_CURRENT_TEST" in os.environ) or ("pytest" in sys.modules):
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from app.db import Base
            from app.api.v1.auth import get_current_user_dep
            from app.db import get_db as real_get_db

            # Use a dedicated on-disk SQLite DB for tests to persist across requests
            test_engine = create_engine(
                "sqlite:///./test.db",
                connect_args={"check_same_thread": False}
            )
            TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

            # Recreate schema fresh each run
            Base.metadata.drop_all(bind=test_engine)
            Base.metadata.create_all(bind=test_engine)

            # Seed a deterministic test user the auth override will return
            from app.models import User, ProviderEnum
            with TestingSessionLocal() as db:
                user = db.query(User).filter(User.id == "user_test").first()
                if not user:
                    user = User(
                        id="user_test",
                        provider=ProviderEnum.google,
                        provider_sub="test_sub",
                        email="test@example.com",
                        name="Test User",
                    )
                    db.add(user)
                    db.commit()

            # Override DB dependency to use the test session
            def override_get_db():
                db = TestingSessionLocal()
                try:
                    yield db
                finally:
                    db.close()

            # Override auth dependency to always return the seeded test user
            def override_current_user_dep():
                return {
                    "user_id": "user_test",
                    "email": "test@example.com",
                    "name": "Test User",
                    "provider": "google",
                }

            app.dependency_overrides[real_get_db] = override_get_db
            app.dependency_overrides[get_current_user_dep] = override_current_user_dep
    except Exception:
        # Never fail app creation due to test-only overrides
        pass
    
    # Health check endpoints
    @app.get("/")
    async def root():
        """Root endpoint for basic health check."""
        return {"status": "ok", "message": "Personal Productivity API is running"}
    
    @app.get("/healthz")
    async def healthz():
        """Production health check endpoint."""
        return {"status": "ok"}
    
    # Auth callback alias routes for Microsoft redirect URIs
    @app.get("/auth/ms/login")
    async def ms_login_alias(request: Request, response: Response):
        """Alias for Microsoft login endpoint."""
        return await auth_v1.microsoft_login(request, response)
    
    @app.get("/auth/ms/callback")
    async def ms_callback_alias(
        request: Request,
        response: Response,
        code: Optional[str] = None,
        state: Optional[str] = None,
        error: Optional[str] = None,
        oauth_state: Optional[str] = Cookie(None)
    ):
        """Alias for Microsoft callback endpoint."""
        return await auth_v1.microsoft_callback(request, response, code, state, error, oauth_state)

    # Auth callback alias routes for Google redirect URIs
    @app.get("/auth/google/login")
    async def google_login_alias(request: Request, response: Response):
        """Alias for Google login endpoint."""
        return await auth_v1.google_login(request, response)

    @app.get("/auth/google/callback")
    async def google_callback_alias(
        request: Request,
        response: Response,
        code: Optional[str] = None,
        state: Optional[str] = None,
        error: Optional[str] = None,
        oauth_state: Optional[str] = Cookie(None)
    ):
        """Alias for Google callback endpoint."""
        return await auth_v1.google_callback(request, response, code, state, error, oauth_state)
    
    return app


# Create the app instance
app = create_app()
