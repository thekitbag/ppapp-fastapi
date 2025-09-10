"""Microsoft authentication endpoints."""
from fastapi import APIRouter, Request, Response, HTTPException, Cookie, Depends
from fastapi.responses import RedirectResponse
from typing import Optional
from pydantic import BaseModel
import secrets

from app.services.auth import AuthService
from app.core import settings, get_logger

logger = get_logger(__name__)
router = APIRouter()


class DevLoginRequest(BaseModel):
    email: str
    name: str

# Global auth service instance (initialized lazily)
auth_service = None

def get_auth_service() -> AuthService:
    """Get or create auth service instance."""
    global auth_service
    if auth_service is None:
        auth_service = AuthService()
    return auth_service


@router.get("/ms/login")
async def microsoft_login(request: Request, response: Response):
    """Initiate Microsoft OAuth login flow."""
    try:
        # Generate authorization URL with state
        auth_svc = get_auth_service()
        auth_url, state = auth_svc.get_ms_authorization_url()
        
        # Store state in secure cookie for validation
        response = RedirectResponse(url=auth_url, status_code=302)
        response.set_cookie(
            key="oauth_state",
            value=state,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=600  # 10 minutes
        )
        
        logger.info("Redirecting user to Microsoft login")
        return response
        
    except Exception as e:
        logger.error(f"Failed to initiate Microsoft login: {e}")
        raise HTTPException(status_code=500, detail="Authentication initialization failed")


@router.get("/ms/callback")
async def microsoft_callback(
    request: Request,
    response: Response,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    oauth_state: Optional[str] = Cookie(None)
):
    """Handle Microsoft OAuth callback."""
    try:
        # Check for OAuth errors
        if error:
            logger.error(f"OAuth error: {error}")
            return RedirectResponse(
                url=f"{settings.app_base_url}?error=authentication_failed",
                status_code=302
            )
        
        # Validate required parameters
        if not code or not state:
            logger.error("Missing code or state parameter")
            return RedirectResponse(
                url=f"{settings.app_base_url}?error=invalid_request",
                status_code=302
            )
        
        # Validate state parameter
        if state != oauth_state:
            logger.error(f"State mismatch: {state} != {oauth_state}")
            return RedirectResponse(
                url=f"{settings.app_base_url}?error=invalid_state",
                status_code=302
            )
        
        # Exchange code for token and user info
        auth_svc = get_auth_service()
        token_data = await auth_svc.exchange_ms_code_for_token(code, state)
        user_info = token_data["user_info"]
        
        # Validate user email against allowlist
        if not auth_svc.validate_user_email(user_info):
            logger.warning(f"User not authorized: {user_info.get('email')}")
            return RedirectResponse(
                url=f"{settings.app_base_url}?error=access_denied",
                status_code=302
            )
        
        # Create session token with database upsert
        session_token = auth_svc.create_session_token_with_db(user_info)
        
        # Set secure session cookie with environment-specific settings
        auth_svc = get_auth_service()
        cookie_settings = auth_svc.get_cookie_settings()
        
        response = RedirectResponse(url=settings.app_base_url, status_code=302)
        response.set_cookie(
            key=settings.session_cookie_name,
            value=session_token,
            **cookie_settings
        )
        
        # Clear OAuth state cookie
        response.set_cookie(
            key="oauth_state",
            value="",
            httponly=True,
            secure=True,
            samesite="none",
            max_age=0
        )
        
        logger.info(f"Successfully authenticated user: {user_info.get('email')}")
        return response
        
    except Exception as e:
        logger.error(f"Authentication callback failed: {e}")
        return RedirectResponse(
            url=f"{settings.app_base_url}?error=authentication_failed",
            status_code=302
        )


@router.get("/google/login")
async def google_login(request: Request, response: Response):
    """Initiate Google OAuth login flow."""
    try:
        # Generate authorization URL with state
        auth_svc = get_auth_service()
        auth_url, state = auth_svc.get_google_authorization_url()
        
        # Store state in secure cookie for validation
        response = RedirectResponse(url=auth_url, status_code=302)
        response.set_cookie(
            key="oauth_state",
            value=state,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=600  # 10 minutes
        )
        
        logger.info("Redirecting user to Google login")
        return response
        
    except Exception as e:
        logger.error(f"Failed to initiate Google login: {e}")
        raise HTTPException(status_code=500, detail="Authentication initialization failed")


@router.get("/google/callback")
async def google_callback(
    request: Request,
    response: Response,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    oauth_state: Optional[str] = Cookie(None)
):
    """Handle Google OAuth callback."""
    try:
        # Check for OAuth errors
        if error:
            logger.error(f"OAuth error: {error}")
            return RedirectResponse(
                url=f"{settings.app_base_url}?error=authentication_failed",
                status_code=302
            )
        
        # Validate required parameters
        if not code or not state:
            logger.error("Missing code or state parameter")
            return RedirectResponse(
                url=f"{settings.app_base_url}?error=invalid_request",
                status_code=302
            )
        
        # Validate state parameter
        if state != oauth_state:
            logger.error(f"State mismatch: {state} != {oauth_state}")
            return RedirectResponse(
                url=f"{settings.app_base_url}?error=invalid_state",
                status_code=302
            )
        
        # Exchange code for token and user info
        auth_svc = get_auth_service()
        token_data = await auth_svc.exchange_google_code_for_token(code, state)
        user_info = token_data["user_info"]
        
        # Validate user email against allowlist
        if not auth_svc.validate_user_email(user_info):
            logger.warning(f"User not authorized: {user_info.get('email')}")
            return RedirectResponse(
                url=f"{settings.app_base_url}?error=access_denied",
                status_code=302
            )
        
        # Create session token with database upsert
        session_token = auth_svc.create_session_token_with_db(user_info)
        
        # Set secure session cookie with environment-specific settings
        auth_svc = get_auth_service()
        cookie_settings = auth_svc.get_cookie_settings()
        
        response = RedirectResponse(url=settings.app_base_url, status_code=302)
        response.set_cookie(
            key=settings.session_cookie_name,
            value=session_token,
            **cookie_settings
        )
        
        # Clear OAuth state cookie
        response.set_cookie(
            key="oauth_state",
            value="",
            httponly=True,
            secure=True,
            samesite="none",
            max_age=0
        )
        
        logger.info(f"Successfully authenticated Google user: {user_info.get('email')}")
        return response
        
    except Exception as e:
        logger.error(f"Google authentication callback failed: {e}")
        return RedirectResponse(
            url=f"{settings.app_base_url}?error=authentication_failed",
            status_code=302
        )


@router.post("/logout")
@router.get("/logout")
async def logout(response: Response):
    """Logout user by clearing session cookie."""
    auth_svc = get_auth_service()
    cookie_settings = auth_svc.get_cookie_settings()
    cookie_settings["max_age"] = 0  # Clear cookie
    
    response.set_cookie(
        key=settings.session_cookie_name,
        value="",
        **cookie_settings
    )
    
    logger.info("User logged out")
    return {"status": "logged_out"}


@router.post("/dev-login")
async def dev_login(request: DevLoginRequest, response: Response):
    """Development-only login endpoint for local testing."""
    if not settings.auth_dev_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    
    try:
        auth_svc = get_auth_service()
        
        # Create session token using dev method (doesn't require MS auth to be configured)
        session_token = auth_svc.create_dev_session_token(request.email, request.name)
        
        # Get environment-appropriate cookie settings
        cookie_settings = auth_svc.get_cookie_settings()
        
        # Set session cookie
        response.set_cookie(
            key=settings.session_cookie_name,
            value=session_token,
            **cookie_settings
        )
        
        logger.info(f"Dev login successful for: {request.email}")
        return {
            "status": "success",
            "message": "Development login successful",
            "user": {"email": request.email, "name": request.name}
        }
        
    except Exception as e:
        logger.error(f"Dev login failed: {e}")
        raise HTTPException(status_code=500, detail="Development login failed")


@router.get("/me")
async def get_current_user(ppapp_session: Optional[str] = Cookie(None)):
    """Get current authenticated user information from database."""
    if not ppapp_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    auth_svc = get_auth_service()
    token_data = auth_svc.verify_session_token(ppapp_session)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    # If we have user_id in token (new format), return database info
    if "user_id" in token_data:
        from app.db import get_db_context
        from app.models import User
        
        with get_db_context() as db:
            user = db.query(User).filter(User.id == token_data["user_id"]).first()
            if user:
                return {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "provider": user.provider
                }
    
    # Fallback for old token format (during transition)
    return {
        "id": token_data.get("user_id"),  
        "email": token_data.get("email"),
        "name": token_data.get("name"),
        "provider": token_data.get("provider", "unknown")
    }


# Dependency for authenticated routes
def get_current_user_dep(ppapp_session: Optional[str] = Cookie(None)) -> dict:
    """Dependency to get current authenticated user with user_id."""
    if not ppapp_session:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    auth_svc = get_auth_service()
    token_data = auth_svc.verify_session_token(ppapp_session)
    if not token_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    # If we have user_id in token (new format), return it
    if "user_id" in token_data:
        return {
            "user_id": token_data["user_id"],
            "email": token_data["email"],
            "name": token_data["name"],
            "provider": token_data["provider"]
        }
    
    # For old token format, we may need to look up by provider info
    # This is a fallback during transition
    return token_data