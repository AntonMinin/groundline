from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.service import AuthError, decode_token
from app.config import settings
from app.db.models import User
from app.db.session import get_session

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "groundline"

Session = Annotated[AsyncSession, Depends(get_session)]


def require_csrf(request: Request) -> None:
    if request.method not in SAFE_METHODS and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing {CSRF_HEADER} header")


async def current_user(request: Request, session: Session) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise unauthorized
    try:
        user_id = decode_token(token)
    except AuthError:
        raise unauthorized
    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(current_user)]
