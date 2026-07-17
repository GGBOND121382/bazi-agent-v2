"""Compatibility import for the professional analysis core."""

from .professional_core import (
    AnalysisPipeline,
    AnalysisPipelineError,
    AnalysisPipelineResult,
)

__all__ = ["AnalysisPipeline", "AnalysisPipelineError", "AnalysisPipelineResult"]
