from typing import Literal, Any
from pydantic import BaseModel, Field

Verdict = Literal['ALLOW', 'ASK_USER', 'BLOCK']

class Observation(BaseModel):
    url: str = ''
    title: str = ''
    target: dict[str, Any] = Field(default_factory=dict)
    page_excerpt: str = ''
    screenshot: str | None = None
    captured_at: float = 0
    fingerprint: str = ''

class Action(BaseModel):
    proposal_id: str
    task_id: str
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    description: str = ''
    observation: Observation = Field(default_factory=Observation)
    recent_actions: list[dict] = Field(default_factory=list)
    payload_class: Literal['ordinary', 'secret', 'unknown'] = 'ordinary'

class Assessment(BaseModel):
    effect: Literal['read', 'navigate', 'input', 'write', 'send', 'purchase', 'delete', 'auth', 'unknown']
    alignment: Literal['aligned', 'conflicts', 'unrelated', 'unknown']
    injection_suspected: bool = False
    evidence: str = ''
    explanation: str
    uncertain: bool = False

class Decision(BaseModel):
    decision_id: str
    proposal_id: str
    verdict: Verdict
    reason: str
    rule_ids: list[str]
    assessment: Assessment | None = None
    model_skipped: bool = True
    latency_ms: float = 0
    policy_version: int = 1
    expires_at: float | None = None

class TaskInput(BaseModel):
    request_id: str | None = Field(default=None, max_length=100)
    goal: str = Field(min_length=5, max_length=12000)
    agent_id: str = 'browser-use-local'
    mode: Literal['hybrid', 'symbolic', 'neural', 'off'] = 'hybrid'
    max_steps: int = Field(default=20, ge=1, le=60)

class UserRule(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=160)
    field: Literal['tool', 'origin', 'effect']
    value: str = Field(min_length=1, max_length=500)
    verdict: Literal['BLOCK', 'ASK_USER'] = 'BLOCK'
    enabled: bool = True
