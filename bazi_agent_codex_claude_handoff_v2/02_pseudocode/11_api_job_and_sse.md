# API 异步任务与 SSE 伪代码

```text
function start_analysis(chart_id, request, idempotency_key):
    chart = chart_repo.get(chart_id)
    assert chart.status == "calculated"
    assert chart.boundary_resolution_status == "resolved"

    existing = job_repo.find_by_idempotency_key(idempotency_key)
    if existing:
        return existing

    job = job_repo.create(stage="queued", progress=0)
    queue.publish("analysis", job.id)
    event_repo.append(job.id, stage="queued", progress=0)
    return job

worker process_analysis(job_id):
    transition(job, "retrieving", 20)
    evidence = retriever.retrieve(build_plan(chart, request))

    transition(job, "interpreting", 45)
    analysis = interpreter.analyze(chart, evidence, request)

    transition(job, "verifying", 70)
    validation = verifier.verify(chart, evidence, analysis)
    if validation.failed:
        if validation.revision_allowed and attempts < limit:
            transition(job, "revision_pending", 72)
            analysis = interpreter.revise(validation.required_revisions)
            repeat verify
        else:
            fail(job, error_code="ANALYSIS_VALIDATION_FAILED")
            return

    transition(job, "report_building", 88)
    report = report_assembler.assemble(validation.approved_claims)
    complete(job, result_ref=report.id)

SSE stream(job_id, last_event_id):
    emit persisted events after last_event_id
    while job not terminal:
        wait for new event or heartbeat timeout
        emit new event or heartbeat
```
