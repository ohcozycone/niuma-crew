"""Administrator-only management of deployment-wide work rules."""

from fastapi import APIRouter, Depends

from app.api.dependencies import ActorDependency, OrganizationRulesDependency, require_capability
from app.api.errors import SERVICE_ERROR_RESPONSES
from app.employees.schemas import OrganizationRulesRead, OrganizationRulesUpdate

router = APIRouter(
    prefix="/api/organization-rules", tags=["organization-rules"], responses=SERVICE_ERROR_RESPONSES
)


@router.get(
    "",
    response_model=OrganizationRulesRead,
    dependencies=[Depends(require_capability("organization_rules:read"))],
)
def get_rules(rules: OrganizationRulesDependency, actor: ActorDependency) -> OrganizationRulesRead:
    return rules.get(actor)


@router.put(
    "",
    response_model=OrganizationRulesRead,
    dependencies=[Depends(require_capability("organization_rules:update"))],
)
def update_rules(
    data: OrganizationRulesUpdate, rules: OrganizationRulesDependency, actor: ActorDependency
) -> OrganizationRulesRead:
    return rules.update(data, actor)
