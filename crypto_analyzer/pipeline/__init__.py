"""
Stable facade: pipeline transforms (Transform) and re-exports from pipelines (run_research_pipeline, ResearchPipelineResult).
Imports pipelines (which pulls promotion); document as non-lightweight. Do not add exports without updating __all__.
"""

from __future__ import annotations

from crypto_analyzer.pipelines import ResearchPipelineResult, run_research_pipeline

from .transforms import Transform

# Do not add exports without updating __all__.
__all__ = ["ResearchPipelineResult", "Transform", "run_research_pipeline"]
