"""GET /api/v1/attribution/{job_id}: the Stage 4 result as Contract C (attribution_verdict.json).

The result is produced by the pipeline and stored inside the job document. This
route validates it against the schema before returning it, so the dashboard and
the report always read the same contract-checked object.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ..jobs import store as job_store
from ..schemas import Stage4Verdict

router = APIRouter()


@router.get("/api/v1/attribution/{job_id}")
def attribution_verdict(job_id: str):
    doc = job_store.load(job_id)
    if doc is None:
        raise HTTPException(404, "unknown job_id %r" % job_id)
    st = (doc.get("attribution") or {}).get("stage4")
    if not st:
        raise HTTPException(404, "this job has no Stage 4 result; run the analysis again")
    if st.get("error") or (st.get("status") == "unavailable" and "candidates" not in st):
        raise HTTPException(503, "Stage 4 did not complete for this job: %s" % st.get("error", "unavailable"))
    try:
        return Stage4Verdict.model_validate(st).model_dump(mode="json")
    except ValidationError as exc:
        raise HTTPException(500, "Stage 4 result failed contract validation: %s" % exc.errors()[:3]) from exc
