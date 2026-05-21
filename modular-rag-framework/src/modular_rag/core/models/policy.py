from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from modular_rag.core.enums import PolicyAction
from modular_rag.core.ids import new_id


class PolicyRule(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    condition: str
    action: PolicyAction
    priority: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class Policy(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    rules: list[PolicyRule] = Field(default_factory=list)
    scope: str = "*"
    enabled: bool = True
    tenant: str = "default"

    def sorted_rules(self) -> list[PolicyRule]:
        return sorted(self.rules, key=lambda r: r.priority, reverse=True)
