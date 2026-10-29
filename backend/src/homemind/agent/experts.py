"""Validate only bounded public expert evidence; never retain rejected output."""

ROLES = ("coordinator_goal", "comfort", "energy", "coordinator_plan")


def skipped_role(role):
    return dict(
        role=role,
        status="skipped",
        model_calls=0,
        tool_calls=0,
        usage=None,
        actual_model=None,
        elapsed_ms=0,
        failure_code=None,
        advice=None,
    )


def validate_advice(output, role, forecast):
    return advice_failure(output, role, forecast) is None


def advice_failure(output, role, forecast):
    candidates = {candidate["id"]: candidate for candidate in forecast["candidates"]}
    allowed = {"goal"} | {"candidate:" + candidate_id for candidate_id in candidates}
    if output["role"] != role:
        return "$.role", "role_mismatch"
    if not set(output["evidence_refs"]) <= allowed:
        return "$.evidence_refs", "unknown_evidence"
    if output["outcome"] == "recommend":
        candidate_id = output["preferred_candidate_id"]
        if candidate_id not in candidates:
            return "$.preferred_candidate_id", "unknown_candidate"
        if not candidates[candidate_id]["deadline_met"]:
            return "$.preferred_candidate_id", "infeasible_candidate"
        if "candidate:" + candidate_id not in output["evidence_refs"]:
            return "$.evidence_refs", "missing_candidate_evidence"
    elif output["preferred_candidate_id"] is not None:
        return "$.preferred_candidate_id", "unexpected_candidate"
    return None
