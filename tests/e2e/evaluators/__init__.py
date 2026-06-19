from __future__ import annotations

from .browser import DownloadedFileEvaluator
from .calculator import CalculatorResultEvaluator
from .finder import CopiedFileEvaluator, FolderExistsEvaluator, ProtectedFileEvaluator
from .textedit import FileContainsEvaluator, TextEditContainsEvaluator

__all__ = [
    "CalculatorResultEvaluator",
    "CopiedFileEvaluator",
    "DownloadedFileEvaluator",
    "FileContainsEvaluator",
    "FolderExistsEvaluator",
    "ProtectedFileEvaluator",
    "TextEditContainsEvaluator",
]
