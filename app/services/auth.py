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
    """Service for Microsoft authentication and JWT management."""
    
    def __init__(self):
        # Check if authentication settings are configured
        self.configured = all([settings.ms_tenant_id, settings.ms_client_id, settings.ms_client_secret, settings.jwt_secret])
        
        if not self.configured:
            logger.warning("Microsoft authentication settings are not configured")
            return
        
        self.tenant_id = settings.ms_tenant_id
        self.client_id = settings.ms_client_id
        self.client_secret = settings.ms_client_secret
        self.auth_base = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.authorize_url = f"{self.auth_base}/oauth2/v2.0/authorize"
        self.token_url = f"{self.auth_base}/oauth2/v2.0/token"
        self.jwt_secret = settings.jwt_secret
        
        # Parse allowlisted emails
        self.allowlist_emails = set()
        if settings.allowlist_emails:
            self.allowlist_emails = {email.strip().lower() for email in settings.allowlist_emails.split(",")}
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Generate Microsoft authorization URL."""
        if not self.configured:
            raise ValueError("Authentication service is not configured")
        
        if not state:
            state = secrets.token_urlsafe(32)
        
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": settings.ms_redirect_uri,
            "scope": "openid profile email offline_access",
            "state": state,
            "response_mode": "query"
        }
        
        auth_url = f"{self.authorize_url}?" + urlencode(params)
        logger.info(f"Generated auth URL for state: {state}")
        return auth_url, state
    
    async def exchange_code_for_token(self, code: str, state: str) -> Dict[str, Any]:
        """Exchange authorization code for access token and user info."""
        if not self.configured:
            raise ValueError("Authentication service is not configured")
        
        token_url = self.token_url
        
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.ms_redirect_uri
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(token_url, data=data)
                response.raise_for_status()
                token_data = response.json()
                
                # Decode the ID token to get user info
                id_token = token_data.get("id_token")
                if not id_token:
                    raise ValidationError("No ID token received from Microsoft")
                
                # Verify JWT signature for production security
                user_info = await self._verify_and_decode_jwt(id_token)
                
                logger.info(f"Successfully authenticated user: {user_info.get('email', user_info.get('preferred_username'))}")
                return {
                    "access_token": token_data.get("access_token"),
                    "user_info": user_info
                }
                
            except httpx.HTTPError as e:
                logger.error(f"Failed to exchange code for token: {e}")
                raise ValidationError(f"Authentication failed: {str(e)}")
    
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
        """Create a JWT session token for the user."""
        if not self.configured:
            raise ValueError("Authentication service is not configured")
        
        payload = {
            "user_id": user_info.get("oid") or user_info.get("sub"),
            "email": user_info.get("email") or user_info.get("preferred_username"),
            "name": user_info.get("name"),
            "exp": datetime.utcnow() + timedelta(days=7)  # Token expires in 7 days
        }
        
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")
    
    def create_dev_session_token(self, email: str, name: str) -> str:
        """Create a session token for local development."""
        if not settings.jwt_secret:
            raise ValueError("JWT secret not configured")
        
        payload = {
            "user_id": f"dev-{email}",
            "email": email,
            "name": name,
            "exp": datetime.utcnow() + timedelta(days=7)
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
    
    async def _verify_and_decode_jwt(self, id_token: str) -> Dict[str, Any]:
        """Verify JWT signature using Microsoft's public keys and decode."""
        import json
        from jwt.algorithms import RSAAlgorithm
        
        try:
            # For development/testing environments, skip verification
            if settings.environment.lower() in ["development", "local"]:
                logger.warning("JWT signature verification disabled for development environment")
                return jwt.decode(id_token, options={"verify_signature": False})
            
            # Get the JWT header to find the key ID
            unverified_header = jwt.get_unverified_header(id_token)
            key_id = unverified_header.get("kid")
            
            if not key_id:
                raise ValidationError("JWT token missing key ID")
            
            # Fetch Microsoft's public keys
            jwks_url = f"https://login.microsoftonline.com/{self.tenant_id}/discovery/v2.0/keys"
            
            async with httpx.AsyncClient() as client:
                jwks_response = await client.get(jwks_url)
                jwks_response.raise_for_status()
                jwks_data = jwks_response.json()
            
            # Find the matching key
            signing_key = None
            for key in jwks_data.get("keys", []):
                if key.get("kid") == key_id:
                    signing_key = RSAAlgorithm.from_jwk(json.dumps(key))
                    break
            
            if not signing_key:
                raise ValidationError(f"Unable to find signing key with ID: {key_id}")
            
            # Verify and decode the JWT
            user_info = jwt.decode(
                id_token,
                signing_key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer=f"https://login.microsoftonline.com/{self.tenant_id}/v2.0"
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