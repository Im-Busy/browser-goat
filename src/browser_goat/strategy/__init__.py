"""Strategy layer: query classification, adaptive exploration, recursive decomposition. (Phase 2)"""

from browser_goat.strategy.adaptive_explorer import AdaptiveExplorer
from browser_goat.strategy.query_classifier import QueryClassifier
from browser_goat.strategy.recursive_decomposer import RecursiveDecomposer

__all__ = ["AdaptiveExplorer", "QueryClassifier", "RecursiveDecomposer"]
