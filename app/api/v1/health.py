from fastapi import APIRouter

router = APIRouter()


@router.get("", tags=["health"])
def health():
    """Health check endpoint."""
    return {"status": "ok"}