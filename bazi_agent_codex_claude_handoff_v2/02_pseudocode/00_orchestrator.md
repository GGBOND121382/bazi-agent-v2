# 编排器伪代码

```text
FUNCTION run_analysis(request):
    validated_request = validate_against_schema(request)
    profile = load_immutable_profile(validated_request.calculation_profile_id)

    normalized_time = time_normalizer.normalize(validated_request, profile)
    term_window = primary_calendar.peek_solar_terms(normalized_time, profile)
    boundary_risk = boundary_analyzer.analyze(normalized_time, term_window, profile)

    candidate_times = boundary_policy.expand_candidates(normalized_time, boundary_risk)
    chart_candidates = []

    FOR candidate_time IN candidate_times:
        primary = primary_calendar.calculate(candidate_time, profile)
        secondary = secondary_calendar.calculate(candidate_time, profile)
        reconciled = reconcile(primary, secondary)

        IF reconciled.status != "passed":
            chart_candidates.append(reconciled)
            CONTINUE

        facts = rule_engine.derive(reconciled, profile.rule_version)
        qiyun = qiyun_strategy.calculate(reconciled, primary.solar_terms, profile)
        dayun = dayun_engine.generate(reconciled.month_pillar, qiyun, profile)
        temporal = temporal_engine.calculate(reconciled, dayun, request.analysis_range, profile)
        chart_candidates.append(assemble_chart(reconciled, facts, qiyun, dayun, temporal))

    IF no candidate has status passed:
        RETURN needs_review_response(chart_candidates)

    IF multiple materially different passed candidates:
        RETURN ambiguous_chart_response(chart_candidates)

    chart = single_passed_candidate
    save_chart(chart)

    retrieval_plan = retrieval_planner.plan(chart, request.user_focus, profile)
    evidence = retriever.retrieve(retrieval_plan, corpus_version="approved_current")

    draft_analysis = interpreter.analyze(chart, evidence, request.user_focus, profile)
    validation = verifier.verify(chart, evidence, draft_analysis)

    IF validation.status != "passed":
        revised = interpreter.revise(draft_analysis, validation.required_revisions)
        validation = verifier.verify(chart, evidence, revised)
        IF validation.status != "passed":
            RETURN human_review_response(validation)
        draft_analysis = revised

    report = report_writer.render(chart, evidence, draft_analysis, validation)
    RETURN report
```

编排器只决定步骤和状态，不自行给出命理结论。
