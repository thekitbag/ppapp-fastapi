from pydantic import BaseModel
from typing import Optional
import os


class Settings(BaseModel):
    """Application settings and configuration."""
    
    # Database
    database_url: str = "sqlite:///./app.db"
    
    # API
    api_title: str = "Personal Productivity API"
    api_version: str = "0.1.0-alpha"
    api_description: str = "A FastAPI application for personal productivity management"
    
    # CORS
    cors_origins: list[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Environment
    environment: str = "development"
    debug: bool = True
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables."""
        import os
        return cls(
            database_url=os.getenv("DATABASE_URL", "sqlite:///./app.db"),
            api_title=os.getenv("API_TITLE", "Personal Productivity API"),
            api_version=os.getenv("API_VERSION", "0.1.0-alpha"),
            api_description=os.getenv("API_DESCRIPTION", "A FastAPI application for personal productivity management"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            environment=os.getenv("ENVIRONMENT", "development"),
            debug=os.getenv("DEBUG", "true").lower() == "true",
        )


# Global settings instance
settings = Settings.from_env()