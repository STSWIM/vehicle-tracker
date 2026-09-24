from fastapi import APIRouter, Depends

from app.access import CurrentUser, get_current_user
from app.schemas import CurrentUserOut

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("", response_model=CurrentUserOut)
def current_user(user: CurrentUser = Depends(get_current_user)):
    return CurrentUserOut(uid=user.uid, standalone=user.superuser)
