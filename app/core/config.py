from pydantic import BaseModel
from typing import Optional, List
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
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Environment
    environment: str = "development"
    debug: bool = True
    
    # Authentication
    ms_tenant_id: Optional[str] = None
    ms_client_id: Optional[str] = None
    ms_client_secret: Optional[str] = None
    jwt_secret: Optional[str] = None
    allowlist_emails: Optional[str] = None
    app_base_url: str = "http://localhost:3000"
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables."""
        import os
        cors_origins_str = os.getenv("CORS_ORIGINS", "*")
        cors_origins = cors_origins_str.split(",") if cors_origins_str != "*" else ["*"]
        
        return cls(
            database_url=os.getenv("DATABASE_URL", "sqlite:///./app.db"),
            api_title=os.getenv("API_TITLE", "Personal Productivity API"),
            api_version=os.getenv("API_VERSION", "0.1.0-alpha"),
            api_description=os.getenv("API_DESCRIPTION", "A FastAPI application for personal productivity management"),
            cors_origins=cors_origins,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            environment=os.getenv("ENVIRONMENT", "development"),
            debug=os.getenv("DEBUG", "true").lower() == "true",
            ms_tenant_id=os.getenv("MS_TENANT_ID"),
            ms_client_id=os.getenv("MS_CLIENT_ID"),
            ms_client_secret=os.getenv("MS_CLIENT_SECRET"),
            jwt_secret=os.getenv("JWT_SECRET"),
            allowlist_emails=os.getenv("ALLOWLIST_EMAILS"),
            app_base_url=os.getenv("APP_BASE_URL", "http://localhost:3000"),
        )


# Global settings instance
settings = Settings.from_env()