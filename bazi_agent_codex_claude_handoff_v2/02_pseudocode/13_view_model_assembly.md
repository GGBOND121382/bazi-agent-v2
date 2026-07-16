# View Model 组装伪代码

```text
function toChartOverviewVM(chart):
    assert schema_version supported
    return {
      pillars: chart.pillars.map(pillar => ({
        label: localized(pillar.position),
        stem: pillar.stem,
        branch: pillar.branch,
        hiddenStems: pillar.hidden_stems,
        tenGod: pillar.ten_god,
        factIds: pillar.fact_ids
      })),
      relationships: sortByDisplayPriority(chart.relationships),
      assumptions: formatAssumptions(chart.calculation_profile),
      warnings: mapSafeWarnings(chart.boundary_risk)
    }

prohibited:
    infer tenGod from stem
    infer element from label color
    create missing relationship
    derive qiyun age
```
