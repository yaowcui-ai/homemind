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
    candidates = {candidate["id"]: candidate for candidate in forecast["candidates"]}
    allowed = {"goal"} | {"candidate:" + candidate_id for candidate_id in candidates}
    if output["role"] != role or not set(output["evidence_refs"]) <= allowed:
        return False
    if output["outcome"] == "recommend":
        candidate_id = output["preferred_candidate_id"]
        return (
            candidate_id in candidates
            and candidates[candidate_id]["deadline_met"]
            and "candidate:" + candidate_id in output["evidence_refs"]
        )
    return output["preferred_candidate_id"] is None
