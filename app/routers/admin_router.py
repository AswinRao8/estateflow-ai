from fastapi import APIRouter
from app.models.base import APIResponse

router = APIRouter(prefix="/admin", tags=["Admin"])

# Future — Multi-Tenant and Platform Administration
# Endpoints to implement (V2+):
#   GET  /admin/tenants           — list registered agencies
#   POST /admin/tenants           — register new agency
#   GET  /admin/config            — platform-level configuration
#
# V1 note: single-tenant deployment has no tenant management UI.
# These stubs exist to reserve the prefix and document the future surface.


@router.get("/config", response_model=APIResponse, summary="Platform config [V2]")
def get_config():
    return APIResponse(success=False, message="Not yet implemented — V2 multi-tenant")
