from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class BrainMode(str, Enum):
    CLASSIC_PYTHON = "classic_python"
    GEMMA_HELM = "gemma_helm"


class HelmMonitorResult(BaseModel):
    should_start_session: bool = False
    severity: str = "NOMINAL"
    reason: str = "No rule-level anomaly detected."
    suspected_subsystems: List[str] = Field(default_factory=list)
    operator_needed: bool = False
    source: str = "rules"


class HelmReviewResult(BaseModel):
    recommended_plan_id: Optional[str] = None
    confidence: float = 0.0
    why: str = ""
    remaining_risks: List[str] = Field(default_factory=list)
    auto_review_suggested: bool = False
    operator_question_needed: bool = True
    source: str = "rules-fallback"


class HelmOperatorQuestion(BaseModel):
    question_id: str
    mode: str
    title: str
    summary: str
    choices: List[str] = Field(default_factory=list)
    default_choice: str = "approve_recommended_plan"
    plan_id: Optional[str] = None


class HelmDialogueTurn(BaseModel):
    ts: float
    speaker: str
    choice: Optional[str] = None
    message: str = ""
    response: str = ""


class HelmSessionContext(BaseModel):
    baseline_id: str
    snapshot_seq: int
    monitor: Dict[str, Any] = Field(default_factory=dict)
    diagnosis_summary: Dict[str, Any] = Field(default_factory=dict)
    plan_summary: Dict[str, Any] = Field(default_factory=dict)
    compare_summary: Dict[str, Any] = Field(default_factory=dict)


class HelmDialogueRequest(BaseModel):
    choice: str
    message: str = ""


class HelmStatusResponse(BaseModel):
    ready: bool
    gemma_ready: bool
    fallback_enabled: bool = True
    auto_monitor_enabled: bool = False
    live_execution_enabled: bool = False
    brain_mode_default: BrainMode = BrainMode.CLASSIC_PYTHON
    detail: Dict[str, Any] = Field(default_factory=dict)
