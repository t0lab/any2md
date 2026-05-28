"""Subagent definitions for the main orchestrator."""
from .cleaner import QUALITY_CLEANER_PROMPT, quality_cleaner_subagent
from .quality_reviewer import QUALITY_REVIEWER_PROMPT, quality_reviewer_subagent

__all__ = [
    "QUALITY_CLEANER_PROMPT",
    "QUALITY_REVIEWER_PROMPT",
    "quality_cleaner_subagent",
    "quality_reviewer_subagent",
]
