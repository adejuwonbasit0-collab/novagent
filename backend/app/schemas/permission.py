from pydantic import BaseModel

from app.models.permission import PermissionScope, RiskLevel


class PermissionOut(BaseModel):
    scope: PermissionScope
    granted: bool
    risk_level: RiskLevel


class PermissionUpdate(BaseModel):
    granted: bool
