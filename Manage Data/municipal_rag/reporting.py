"""Stable public import for the existing fault-isolation reports."""

from batch_reporting import atomic_replace_json, refresh_review_outputs

__all__ = ["atomic_replace_json", "refresh_review_outputs"]

