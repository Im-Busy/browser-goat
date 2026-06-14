"""Strategy layer: query classification, adaptive exploration, recursive decomposition. (Phase 2)"""

from browsing_meta.strategy.adaptive_explorer import AdaptiveExplorer
from browsing_meta.strategy.query_classifier import QueryClassifier
from browsing_meta.strategy.recursive_decomposer import RecursiveDecomposer

__all__ = ["AdaptiveExplorer", "QueryClassifier", "RecursiveDecomposer"]
