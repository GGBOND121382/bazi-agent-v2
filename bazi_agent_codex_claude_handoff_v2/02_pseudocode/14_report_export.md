# 报告与 PDF 伪代码

```text
assemble_report(validation):
    assert validation.status == passed
    blocks = map approved claims to typed blocks
    return ReportDocument(blocks, citations, assumptions, limitations)

web route /reports/:id:
    fetch ReportView
    render interactive navigation, drawers and charts

print route /reports/:id/print?token=...:
    fetch same ReportView
    render deterministic print components
    expand required citations
    replace interactive charts with SVG or print tables
    wait for document.fonts.ready and chart_ready marker

pdf worker:
    open print route with one-time token
    wait for [data-print-ready=true]
    export PDF with fixed margins, header/footer and page numbers
```
