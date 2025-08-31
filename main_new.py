from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import settings, setup_logging, get_logger
from app.exceptions import AppException, app_exception_handler, general_exception_handler
from app.api.v1 import api_router
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
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
    
    # Exception handlers
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
    
    # Include API routes
    app.include_router(api_router)
    
    # Health check endpoint
    @app.get("/")
    async def root():
        """Root endpoint for basic health check."""
        return {"status": "ok", "message": "Personal Productivity API is running"}
    
    return app


# Create the app instance
app = create_app()