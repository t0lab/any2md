"""any2md — document → markdown converter.

Public API:
  convert(source, *, options=...)   sync wrapper, safe inside or outside a loop
  aconvert(source, *, options=...)  async-native (preferred in notebooks)
  ConvertOptions, ConvertResult     configuration / output dataclasses
"""
__version__ = "0.0.1"

from .convert import aconvert, convert
from .options import ConvertOptions, ConvertResult, ModelConfig

__all__ = ["aconvert", "convert", "ConvertOptions", "ConvertResult", "ModelConfig", "__version__"]
