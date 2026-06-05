from fastapi import APIRouter

router = APIRouter(prefix="/api/iam", tags=["IAM"])

@router.post("/test-provisioning")
async def test_provisioning():
    """Trigger an IAM user provisioning test"""
    return {"status": "initiated", "test": "provisioning"}

@router.post("/test-sso")
async def test_sso():
    """Trigger an IAM SSO login flow test"""
    return {"status": "initiated", "test": "sso"}
