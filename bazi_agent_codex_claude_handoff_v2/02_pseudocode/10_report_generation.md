# 报告生成伪代码

```text
FUNCTION build_report(chart, validated_analysis, evidence, profile):
    REQUIRE validated_analysis.validation_status == passed

    report = {
        metadata: versions and generated_at,
        calculation_assumptions: profile + warnings,
        birth_information: minimally necessary fields,
        calendar_and_pillars: chart deterministic facts,
        qiyun_and_dayun: chart luck data,
        natal_analysis: approved claims by topic,
        temporal_analysis: approved claims grouped by level,
        shensha: deterministic matches with auxiliary label,
        evidence: citation list,
        limitations: fixed disclaimer and uncertainty,
        audit: trace ids, not secret prompts
    }

    validate report against report schema
    html = render_jinja_template(report)
    optionally pdf = chromium_print_to_pdf(html)
    RETURN report JSON, html, pdf
```

报告模板不能访问模型原始草稿；只能访问验证后的结构化数据。
