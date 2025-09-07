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
    ms_redirect_uri: str = "http://127.0.0.1:8000/auth/ms/callback"  # default for local dev
    jwt_secret: Optional[str] = None
    allowlist_emails: Optional[str] = None
    app_base_url: str = "http://localhost:3000"
    
    # Development settings
    dev_login_enabled: bool = False
    auth_dev_enabled: bool = False
    dev_login_allowed_emails: Optional[str] = None
    
    # Cookie settings
    session_cookie_name: str = "ppapp_session"
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "none"
    session_cookie_domain: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables."""
        import os
        from dotenv import load_dotenv
        
        # Load .env.local first, then .env (if they exist)
        load_dotenv(".env.local", override=True)
        load_dotenv(".env", override=False)
        cors_origins_str = os.getenv("CORS_ORIGINS", "")
        if cors_origins_str:
            cors_origins = [origin.strip() for origin in cors_origins_str.split(",")]
        else:
            # Default origins for development
            cors_origins = [
                "http://localhost:5173",
                "http://127.0.0.1:5173", 
                "http://localhost:3000",
                "http://127.0.0.1:3000"
            ]
        
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
            ms_redirect_uri=os.getenv("MS_REDIRECT_URI", "http://127.0.0.1:8000/auth/ms/callback"),
            jwt_secret=os.getenv("JWT_SECRET"),
            allowlist_emails=os.getenv("ALLOWLIST_EMAILS"),
            app_base_url=os.getenv("APP_BASE_URL", "http://localhost:3000"),
            dev_login_enabled=os.getenv("DEV_LOGIN_ENABLED", "false").lower() == "true",
            auth_dev_enabled=os.getenv("AUTH_DEV_ENABLED", "false").lower() == "true",
            dev_login_allowed_emails=os.getenv("DEV_LOGIN_ALLOWED_EMAILS"),
            session_cookie_name=os.getenv("SESSION_COOKIE_NAME", "ppapp_session"),
            session_cookie_secure=os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true",
            session_cookie_samesite=os.getenv("SESSION_COOKIE_SAMESITE", "none"),
            session_cookie_domain=os.getenv("SESSION_COOKIE_DOMAIN") or None,
        )


# Global settings instance
settings = Settings.from_env()