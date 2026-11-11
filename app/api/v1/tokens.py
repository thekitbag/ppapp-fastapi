from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, Request, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session
from app.db import get_db
from app.core import settings
from app.api.v1.auth import get_current_user_dep
from app.services.tokens import TokenService

router = APIRouter()


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[Literal['read', 'write']] = Field(min_length=1, max_length=2)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Token name cannot be blank')
        return value.strip()


class TokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class TokenCreated(TokenOut):
    token: str


def check_origin(request: Request):
    """Cookie-authenticated mutations must come from an explicitly trusted origin."""
    origin = request.headers.get('origin')
    if origin and origin not in {*settings.cors_origins, settings.app_base_url.rstrip('/')}:
        raise HTTPException(403, 'Untrusted request origin')


@router.post('', response_model=TokenCreated, status_code=201, dependencies=[Depends(check_origin)])
def create_token(payload: TokenCreate, response: Response,
                 user=Depends(get_current_user_dep), db: Session = Depends(get_db)):
    token, plaintext = TokenService(db).create(user['user_id'], payload.name, payload.scopes)
    response.headers['Cache-Control'] = 'no-store'
    return {**TokenOut.model_validate(token).model_dump(), 'token': plaintext}


@router.get('', response_model=list[TokenOut])
def list_tokens(response: Response, user=Depends(get_current_user_dep), db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    return TokenService(db).list(user['user_id'])


@router.delete('/{token_id}', status_code=204, dependencies=[Depends(check_origin)])
def revoke_token(token_id: str, user=Depends(get_current_user_dep), db: Session = Depends(get_db)):
    TokenService(db).revoke(user['user_id'], token_id)
