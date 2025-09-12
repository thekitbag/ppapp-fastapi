"""Microsoft Authentication Service."""
import jwt
import httpx
import secrets
from typing import Optional, Dict, Any
from urllib.parse import urlencode, quote
from datetime import datetime, timedelta

from app.core import settings, get_logger
from app.exceptions import ValidationError

logger = get_logger(__name__)


class AuthService:
    """Service for OAuth authentication (Microsoft & Google) and JWT management."""
    
    def __init__(self):
        # Check if authentication settings are configured
        self.ms_configured = all([settings.ms_tenant_id, settings.ms_client_id, settings.ms_client_secret, settings.jwt_secret])
        self.google_configured = all([settings.google_client_id, settings.google_client_secret, settings.jwt_secret])
        self.configured = self.ms_configured or self.google_configured
        
        if not self.configured:
            logger.warning("OAuth authentication settings are not configured")
            return
        
        # Microsoft configuration
        if self.ms_configured:
            self.ms_tenant_id = settings.ms_tenant_id
            self.ms_client_id = settings.ms_client_id
            self.ms_client_secret = settings.ms_client_secret
            self.ms_auth_base = f"https://login.microsoftonline.com/{self.ms_tenant_id}"
            self.ms_authorize_url = f"{self.ms_auth_base}/oauth2/v2.0/authorize"
            self.ms_token_url = f"{self.ms_auth_base}/oauth2/v2.0/token"
        
        # Google configuration
        if self.google_configured:
            self.google_client_id = settings.google_client_id
            self.google_client_secret = settings.google_client_secret
            self.google_authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
            self.google_token_url = "https://oauth2.googleapis.com/token"
            self.google_userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        
        self.jwt_secret = settings.jwt_secret
        
        # Parse allowlisted emails
        self.allowlist_emails = set()
        if settings.allowlist_emails:
            self.allowlist_emails = {email.strip().lower() for email in settings.allowlist_emails.split(",")}
    
    def get_ms_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        """Generate Microsoft authorization URL."""
        if not self.ms_configured:
            raise ValueError("Microsoft authentication is not configured")
        
        if not state:
            state = secrets.token_urlsafe(32)
        
        params = {
            "client_id": self.ms_client_id,
            "response_type": "code",
            "redirect_uri": settings.ms_redirect_uri,
            "scope": "openid profile email offline_access",
            "state": state,
            "response_mode": "query"
        }
        
        auth_url = f"{self.ms_authorize_url}?" + urlencode(params)
        logger.info(f"Generated Microsoft auth URL for state: {state}")
        return auth_url, state
    
    def get_google_authorization_url(self, state: Optional[str] = None) -> tuple[str, str]:
        """Generate Google authorization URL."""
        if not self.google_configured:
            raise ValueError("Google authentication is not configured")
        
        if not state:
            state = secrets.token_urlsafe(32)
        
        params = {
            "client_id": self.google_client_id,
            "response_type": "code",
            "redirect_uri": settings.google_redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "access_type": "offline"
        }
        
        auth_url = f"{self.google_authorize_url}?" + urlencode(params)
        logger.info(f"Generated Google auth URL for state: {state}")
        return auth_url, state
    
    async def exchange_ms_code_for_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange Microsoft authorization code for access token and user info."""
        if not self.ms_configured:
            raise ValueError("Microsoft authentication is not configured")
        
        data = {
            "client_id": self.ms_client_id,
            "client_secret": self.ms_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.ms_redirect_uri
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.ms_token_url, data=data)
                response.raise_for_status()
                token_data = response.json()
                
                # Decode the ID token to get user info
                id_token = token_data.get("id_token")
                if not id_token:
                    raise ValidationError("No ID token received from Microsoft")
                
                # Verify JWT signature for production security
                user_info = await self._verify_and_decode_ms_jwt(id_token)
                
                # Normalize user info format
                normalized_user = {
                    "provider": "microsoft",
                    "provider_sub": user_info.get("oid") or user_info.get("sub"),
                    "email": user_info.get("email") or user_info.get("preferred_username"),
                    "name": user_info.get("name")
                }
                
                logger.info(f"Successfully authenticated Microsoft user: {normalized_user['email']}")
                return {
                    "access_token": token_data.get("access_token"),
                    "user_info": normalized_user
                }
                
            except httpx.HTTPError as e:
                logger.error(f"Failed to exchange Microsoft code for token: {e}")
                raise ValidationError(f"Microsoft authentication failed: {str(e)}")
    
    async def exchange_google_code_for_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange Google authorization code for access token and user info."""
        if not self.google_configured:
            raise ValueError("Google authentication is not configured")
        
        data = {
            "client_id": self.google_client_id,
            "client_secret": self.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_redirect_uri
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.google_token_url, data=data)
                response.raise_for_status()
                token_data = response.json()
                
                access_token = token_data.get("access_token")
                if not access_token:
                    raise ValidationError("No access token received from Google")
                
                # Get user info using the access token
                userinfo_response = await client.get(
                    self.google_userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                userinfo_response.raise_for_status()
                user_info = userinfo_response.json()
                
                # Normalize user info format
                normalized_user = {
                    "provider": "google",
                    "provider_sub": user_info.get("id"),
                    "email": user_info.get("email"),
                    "name": user_info.get("name")
                }
                
                logger.info(f"Successfully authenticated Google user: {normalized_user['email']}")
                return {
                    "access_token": access_token,
                    "user_info": normalized_user
                }
                
            except httpx.HTTPError as e:
                logger.error(f"Failed to exchange Google code for token: {e}")
                raise ValidationError(f"Google authentication failed: {str(e)}")
    
    def validate_user_email(self, user_info: Dict[str, Any]) -> bool:
        """Validate user email against allowlist."""
        email = user_info.get("email") or user_info.get("preferred_username") or user_info.get("upn")
        if not email:
            logger.warning("No email found in user info")
            return False
        
        email = email.lower().strip()
        
        if not self.allowlist_emails:
            logger.warning("No allowlist configured - allowing all users")
            return True
        
        is_allowed = email in self.allowlist_emails
        if not is_allowed:
            logger.warning(f"User email {email} not in allowlist")
        
        return is_allowed
    
    def create_session_token(self, user_info: Dict[str, Any]) -> str:
        """Create a JWT session token for the user with normalized format."""
        if not self.configured:
            raise ValueError("Authentication service is not configured")
        
        # user_info should already be normalized with provider, provider_sub, email, name
        payload = {
            "provider": user_info["provider"],
            "provider_sub": user_info["provider_sub"], 
            "email": user_info["email"],
            "name": user_info["name"],
            "exp": datetime.utcnow() + timedelta(days=7)  # Token expires in 7 days
        }
        
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
    
    def upsert_user_from_token(self, user_info: Dict[str, Any]) -> str:
        """Upsert user in database and return user_id for session token."""
        from sqlalchemy.orm import Session
        from app.db import get_db_context
        from app.models import User, ProviderEnum
        import uuid
        
        with get_db_context() as db:
            # Look for existing user by (provider, provider_sub)
            existing_user = db.query(User).filter(
                User.provider == ProviderEnum(user_info["provider"]),
                User.provider_sub == user_info["provider_sub"]
            ).first()
            
            if existing_user:
                # Update email and name in case they changed
                existing_user.email = user_info["email"]
                existing_user.name = user_info["name"]
                db.commit()
                logger.info(f"Updated existing user: {existing_user.id}")
                return existing_user.id
            else:
                # Create new user
                new_user = User(
                    id=str(uuid.uuid4()),
                    provider=ProviderEnum(user_info["provider"]),
                    provider_sub=user_info["provider_sub"],
                    email=user_info["email"],
                    name=user_info["name"]
                )
                db.add(new_user)
                db.commit()
                logger.info(f"Created new user: {new_user.id}")
                return new_user.id
    
    def create_session_token_with_db(self, user_info: Dict[str, Any]) -> str:
        """Create session token with database user_id lookup/creation."""
        if not self.configured:
            raise ValueError("Authentication service is not configured")
        
        # Upsert user in database
        user_id = self.upsert_user_from_token(user_info)
        
        payload = {
            "user_id": user_id,
            "provider": user_info["provider"],
            "provider_sub": user_info["provider_sub"], 
            "email": user_info["email"],
            "name": user_info["name"],
            "exp": datetime.utcnow() + timedelta(days=7)
        }
        
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
    
    def create_dev_session_token(self, email: str, name: str) -> str:
        """Create a session token for local development."""
        if not settings.jwt_secret:
            raise ValueError("JWT secret not configured")
        
        # Create normalized user info for dev login
        dev_user_info = {
            "provider": "microsoft",  # use a valid ProviderEnum value
            "provider_sub": f"dev-{email}",
            "email": email,
            "name": name,
        }
        
        # Upsert user in DB without requiring full OAuth configuration
        user_id = self.upsert_user_from_token(dev_user_info)
        
        # Encode a JWT containing user_id (same shape as create_session_token_with_db)
        payload = {
            "user_id": user_id,
            "provider": dev_user_info["provider"],
            "provider_sub": dev_user_info["provider_sub"],
            "email": dev_user_info["email"],
            "name": dev_user_info["name"],
            "exp": datetime.utcnow() + timedelta(days=7),
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    
    def get_cookie_settings(self) -> Dict[str, Any]:
        """Get cookie settings appropriate for the current environment."""
        # Determine if we're in local development
        is_local = settings.environment.lower() in ["development", "local"]
        
        cookie_settings = {
            "httponly": True,
            "max_age": 7 * 24 * 60 * 60,  # 7 days
            "path": "/"
        }
        
        if is_local:
            # Local development over HTTP - DO NOT use Secure or SameSite=None
            cookie_settings["samesite"] = "lax"
            cookie_settings["secure"] = False
            # No domain = host-only cookie
        else:
            # Production over HTTPS
            cookie_settings["samesite"] = "none"
            cookie_settings["secure"] = True
            # Add domain if configured
            if settings.session_cookie_domain:
                cookie_settings["domain"] = settings.session_cookie_domain
            
        return cookie_settings
    
    def verify_session_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a session token."""
        # For JWT verification, we only need the JWT secret, not full MS auth config
        if not settings.jwt_secret:
            return None
        
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Session token expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid session token")
            return None
    
    async def _verify_and_decode_ms_jwt(self, id_token: str) -> Dict[str, Any]:
        """Verify JWT signature using Microsoft's public keys and decode."""
        from jwt import PyJWKClient
        
        try:
            # For development/testing environments, skip verification
            if settings.environment.lower() in ["development", "local"]:
                logger.warning("JWT signature verification disabled for development environment")
                return jwt.decode(id_token, options={"verify_signature": False})
            
            # Get OIDC discovery info
            oidc_discovery_url = f"https://login.microsoftonline.com/{self.ms_tenant_id}/v2.0/.well-known/openid-configuration"
            
            async with httpx.AsyncClient() as client:
                cfg_response = await client.get(oidc_discovery_url, timeout=5)
                cfg_response.raise_for_status()
                cfg = cfg_response.json()
            
            jwks_uri = cfg["jwks_uri"]
            issuer = cfg["issuer"]
            
            # Use PyJWKClient to fetch the appropriate signing key
            jwk_client = PyJWKClient(jwks_uri)
            signing_key = jwk_client.get_signing_key_from_jwt(id_token)
            
            # Verify and decode the JWT
            user_info = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.ms_client_id,
                issuer=issuer,
                options={"require": ["exp", "iat"], "leeway": 60}  # small clock skew
            )
            
            return user_info
            
        except jwt.ExpiredSignatureError:
            raise ValidationError("JWT token has expired")
        except jwt.InvalidAudienceError:
            raise ValidationError("JWT token has invalid audience")
        except jwt.InvalidIssuerError:
            raise ValidationError("JWT token has invalid issuer")
        except jwt.InvalidSignatureError:
            raise ValidationError("JWT token signature verification failed")
        except Exception as e:
            logger.error(f"JWT verification failed: {str(e)}")
            raise ValidationError(f"JWT token verification failed: {str(e)}")
