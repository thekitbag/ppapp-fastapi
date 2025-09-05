"""Microsoft authentication endpoints."""
from fastapi import APIRouter, Request, Response, HTTPException, Cookie, Depends
from fastapi.responses import RedirectResponse
from typing import Optional
import secrets

from app.services.auth import AuthService
from app.core import settings, get_logger

logger = get_logger(__name__)
router = APIRouter()

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
        auth_url, state = auth_svc.get_authorization_url()
        
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
        token_data = await auth_svc.exchange_code_for_token(code, state)
        user_info = token_data["user_info"]
        
        # Validate user email against allowlist
        if not auth_svc.validate_user_email(user_info):
            logger.warning(f"User not authorized: {user_info.get('email')}")
            return RedirectResponse(
                url=f"{settings.app_base_url}?error=access_denied",
                status_code=302
            )
        
        # Create session token
        session_token = auth_svc.create_session_token(user_info)
        
        # Set secure session cookie
        response = RedirectResponse(url=settings.app_base_url, status_code=302)
        response.set_cookie(
            key="ppapp_session",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=7 * 24 * 60 * 60  # 7 days
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


@router.post("/logout")
async def logout(response: Response):
    """Logout user by clearing session cookie."""
    response = Response(status_code=200, content={"status": "logged_out"})
    response.set_cookie(
        key="ppapp_session",
        value="",
        httponly=True,
        secure=True,
        samesite="none",
        max_age=0
    )
    
    logger.info("User logged out")
    return response


@router.get("/me")
async def get_current_user(ppapp_session: Optional[str] = Cookie(None)):
    """Get current authenticated user information."""
    if not ppapp_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    auth_svc = get_auth_service()
    user_data = auth_svc.verify_session_token(ppapp_session)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    return {
        "user_id": user_data.get("user_id"),
        "email": user_data.get("email"),
        "name": user_data.get("name")
    }


# Dependency for authenticated routes
def get_current_user_dep(ppapp_session: Optional[str] = Cookie(None)) -> dict:
    """Dependency to get current authenticated user."""
    if not ppapp_session:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    auth_svc = get_auth_service()
    user_data = auth_svc.verify_session_token(ppapp_session)
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    
    return user_data