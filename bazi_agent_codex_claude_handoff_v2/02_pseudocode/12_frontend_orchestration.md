# 前端编排伪代码

```text
BirthWizard submit:
    validate client format only
    POST /charts with Idempotency-Key
    if response.status == needs_user_resolution:
        route to /charts/:id/resolve
    else:
        route to /charts/:id/overview

StartAnalysis:
    POST /charts/:id/analyses
    store job_id in route, not hidden global state
    route to /jobs/:job_id

JobProgressPage:
    fetch current job snapshot
    subscribe SSE(last_event_id)
    map stage to safe localized label
    update TanStack Query cache
    on completed -> route to report
    on retryable failure -> show retry action
    on non-retryable failure -> show input/help action

Page refresh:
    derive resource IDs from route
    refetch server state
    reconnect SSE
```
