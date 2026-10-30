"""Analytics API requests built from a case's own expectations.

Ported from ``main`` (PZB-1282), request builder, client and catalogue only:
the plain baseline (``goldset.plain``) fetches reference tables with them, so
a reply that pulled no data of its own can still have its figures checked.
``main`` also carries the GOLD ``ground_truth`` selector and prefetch, which
BENCHMARK does not use.
"""

from goldset.groundtruth.catalog import CatalogError, Dataset, datasets
from goldset.groundtruth.client import AnalyticsClient, AnalyticsError, AnalyticsResult
from goldset.groundtruth.request import AnalyticsRequest, RequestError, build_request

__all__ = [
    "AnalyticsClient",
    "AnalyticsError",
    "AnalyticsRequest",
    "AnalyticsResult",
    "CatalogError",
    "Dataset",
    "RequestError",
    "build_request",
    "datasets",
]
