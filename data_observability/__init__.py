"""
Data Observability Platform
A production-grade platform for data quality at scale.
"""

__version__ = "0.1.0"
__author__ = "Data Platform Team"

from data_observability.core.profiler import DataProfiler
from data_observability.core.config_parser import DatasetConfig
from data_observability.core.execution_router import ExecutionRouter

__all__ = [
    "DataProfiler",
    "DatasetConfig",
    "ExecutionRouter",
]
