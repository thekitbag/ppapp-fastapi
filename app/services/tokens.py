"""Personal token lifecycle and authentication, independent of browser sessions."""
import hashlib
import secrets
from datetime import datetime, timezone
from fastapi import HTTPException
from app.models import ApiToken, User
from app.exceptions import NotFoundError
from app.services.base import BaseService


class TokenService(BaseService):
    def create(self, user_id, name, scopes):
        plaintext = 'et_pat_' + secrets.token_urlsafe(32)
        token = ApiToken(user_id=user_id, name=name,
                         token_hash=hashlib.sha256(plaintext.encode()).hexdigest(),
                         prefix=plaintext[:8], scopes=sorted(set(scopes)))
        self.db.add(token)
        self.commit()
        self.db.refresh(token)
        return token, plaintext

    def list(self, user_id):
        return self.db.query(ApiToken).filter(ApiToken.user_id == user_id).order_by(
            ApiToken.created_at.desc(), ApiToken.id).all()

    def revoke(self, user_id, token_id):
        token = self.db.query(ApiToken).filter(
            ApiToken.id == token_id, ApiToken.user_id == user_id).first()
        if token is None:
            raise NotFoundError('Token', token_id)
        if token.revoked_at is None:
            token.revoked_at = datetime.now(timezone.utc)
            self.commit()

    def authenticate(self, authorization):
        scheme, _, plaintext = (authorization or '').partition(' ')
        if scheme.lower() != 'bearer' or not plaintext.startswith('et_pat_') or len(plaintext) > 256:
            raise HTTPException(401, 'A personal access token is required', headers={'WWW-Authenticate': 'Bearer'})
        token = self.db.query(ApiToken).filter(
            ApiToken.token_hash == hashlib.sha256(plaintext.encode()).hexdigest(),
            ApiToken.revoked_at.is_(None),
        ).first()
        user = self.db.get(User, token.user_id) if token else None
        if user is None:
            raise HTTPException(401, 'Invalid or revoked personal access token', headers={'WWW-Authenticate': 'Bearer'})
        token.last_used_at = datetime.now(timezone.utc)
        identity = {'user_id': user.id, 'email': user.email, 'name': user.name,
                    'provider': user.provider.value, 'token_id': token.id,
                    'scopes': tuple(token.scopes)}
        self.commit()
        return identity


def require_scope(identity, scope):
    if scope not in identity['scopes']:
        raise HTTPException(403, f"Token requires '{scope}' scope")
