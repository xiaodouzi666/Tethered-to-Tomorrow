from __future__ import annotations

import time
import uuid
from typing import Any, Dict

from pi_probe.helm.schemas import HelmDialogueRequest, HelmDialogueTurn, HelmOperatorQuestion, HelmReviewResult


def build_operator_question(
    *,
    review_mode: str,
    recommended_plan_id: str | None,
    helm_review: HelmReviewResult | None,
    policy_result: Any,
) -> HelmOperatorQuestion:
    blockers = getattr(policy_result, "blocking_conditions", []) or []
    choices = ["approve_recommended_plan", "request_safer_plan", "ask_for_more_explanation", "abort"]
    if blockers and "approve_recommended_plan" in choices:
        choices = ["request_safer_plan", "ask_for_more_explanation", "abort"]

    title = "E4B Helm review is ready"
    if blockers:
        title = "E4B Helm requires operator review"
    elif review_mode == "auto":
        title = "E4B Helm can proceed if policy remains clear"

    summary = helm_review.why if helm_review else "Helm produced a recommendation from Twin comparison."
    if blockers:
        summary += f" Policy blockers: {', '.join(blockers)}."

    return HelmOperatorQuestion(
        question_id=f"helm-q-{uuid.uuid4().hex[:10]}",
        mode=review_mode,
        title=title,
        summary=summary,
        choices=choices,
        default_choice=choices[0],
        plan_id=recommended_plan_id,
    )


def dialogue_turn(req: HelmDialogueRequest, response: str, speaker: str = "operator") -> HelmDialogueTurn:
    return HelmDialogueTurn(
        ts=time.time(),
        speaker=speaker,
        choice=req.choice,
        message=req.message,
        response=response,
    )


def response_for_choice(choice: str, context: Dict[str, Any]) -> str:
    recommended = context.get("recommended_plan_id") or "the recommended plan"
    if choice == "approve_recommended_plan":
        return f"Operator approved {recommended}; Python policy gate will issue an execution ticket."
    if choice == "request_safer_plan":
        return "Operator requested a safer plan; Helm will prefer the lowest-risk PASS plan without high-risk actions."
    if choice == "ask_for_more_explanation":
        return str(context.get("why") or "The recommendation is based on Twin verdict, risk score, repair trace, and policy gate blockers.")
    if choice == "abort":
        return "Operator aborted this Helm recovery session."
    return "Operator input recorded."
