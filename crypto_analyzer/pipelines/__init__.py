"""Pipelines: end-to-end research pipeline (validation → promotion → artifacts)."""

from __future__ import annotations

from .research_pipeline import ResearchPipelineResult, run_research_pipeline

__all__ = ["ResearchPipelineResult", "run_research_pipeline"]
