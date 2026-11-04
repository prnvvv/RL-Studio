"""Hosted image segmentation (no local inference)."""

from .mask2former import DEFAULT_MODEL, DEFAULT_PROVIDER, Mask2FormerClient

__all__ = ["DEFAULT_MODEL", "DEFAULT_PROVIDER", "Mask2FormerClient"]
