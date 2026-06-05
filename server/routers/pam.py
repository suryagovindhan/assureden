from fastapi import APIRouter

router = APIRouter(prefix="/api/pam", tags=["PAM"])

@router.post("/test-vaulting")
async def test_vaulting():
    """Trigger a PAM Vaulting test"""
    return {"status": "initiated", "test": "vaulting"}

@router.post("/test-checkout")
async def test_checkout():
    """Trigger a PAM Credential Checkout test"""
    return {"status": "initiated", "test": "checkout"}
