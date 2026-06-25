from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.database import get_session
from app.models import Tenant, User
from app.schemas import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    # For MVP: register creates a new tenant + owner user
    existing = await session.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    # Create tenant
    tenant_name = body.email.split("@")[0]
    tenant = Tenant(name=tenant_name, lnbits_admin_key="", lnbits_url="http://lnbits:5000")
    session.add(tenant)
    await session.flush()

    # Create owner user
    user = User(
        tenant_id=tenant.id,
        email=body.email,
        password_hash=hash_password(body.password),
        role="owner",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    access = create_access_token(str(user.id), str(tenant.id))
    refresh = create_refresh_token(str(user.id), str(tenant.id))
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    result = await session.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access = create_access_token(str(user.id), str(user.tenant_id))
    refresh = create_refresh_token(str(user.id), str(user.tenant_id))
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: dict,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    refresh = body.get("refresh_token")
    if not refresh:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="refresh_token required")
    try:
        payload = decode_token(refresh)
        if payload.get("type") != "refresh":
            raise HTTPException(401)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload["sub"]
    tenant_id = payload["tenant_id"]
    result = await session.execute(select(User).where(User.id == user_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access = create_access_token(user_id, tenant_id)
    new_refresh = create_refresh_token(user_id, tenant_id)
    return TokenResponse(access_token=access, refresh_token=new_refresh)
