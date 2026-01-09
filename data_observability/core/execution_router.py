"""
Intelligent execution router that determines optimal backend for each test.
"""

from typing import List, Dict, Any, Literal
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    """Plan for executing a set of validations."""
    dataset_name: str
    gx_expectations: List[Any]
    sql_checks: List[Dict[str, Any]]
    direct_checks: List[Dict[str, Any]]
    estimated_runtime_seconds: float


class ExecutionRouter:
    """
    Routes validation tests to optimal execution backends based on:
    - Test type and complexity
    - Dataset size
    - Historical performance metrics
    """
    
    # Test types that should use SQL engine
    SQL_ENGINE_TESTS = {
        "referential_integrity",
        "multi_column_uniqueness",
        "cross_table_validation",
        "complex_aggregation"
    }
    
    # Test types for direct DB checks
    DIRECT_CHECK_TESTS = {
        "freshness",
        "volume",
        "row_count",
        "table_exists"
    }
    
    def __init__(
        self,
        force_sql_execution: List[str] = None,
        table_size_threshold_gb: float = 100.0,
        performance_history: Dict[str, float] = None
    ):
        """
        Initialize router.
        
        Args:
            force_sql_execution: Test types to always route to SQL
            table_size_threshold_gb: Skip expensive tests for tables above this size
            performance_history: Historical runtime data for optimization
        """
        self.force_sql = set(force_sql_execution or [])
        self.size_threshold = table_size_threshold_gb
        self.performance_history = performance_history or {}
        self.logger = logger
    
    def route(
        self,
        expectations: List[Any],
        dataset_name: str,
        dataset_size_gb: float = 0.0,
        freshness_config: Dict[str, Any] = None,
        volume_config: Dict[str, Any] = None
    ) -> ExecutionPlan:
        """
        Create execution plan by routing tests to optimal backends.
        
        Args:
            expectations: List of Great Expectations configurations
            dataset_name: Name of dataset being validated
            dataset_size_gb: Estimated size of dataset
            freshness_config: Freshness monitoring configuration
            volume_config: Volume monitoring configuration
            
        Returns:
            ExecutionPlan with tests routed to backends
        """
        self.logger.info(f"Routing {len(expectations)} expectations for {dataset_name}")
        
        gx_expectations = []
        sql_checks = []
        direct_checks = []
        
        # Add freshness and volume checks if configured
        if freshness_config:
            direct_checks.append({
                "type": "freshness",
                "config": freshness_config
            })
        
        if volume_config:
            direct_checks.append({
                "type": "volume",
                "config": volume_config
            })
        
        # Route each expectation
        for exp in expectations:
            backend = self._determine_backend(exp, dataset_size_gb)
            
            if backend == "sql":
                sql_checks.append(self._convert_to_sql_check(exp))
            elif backend == "direct":
                direct_checks.append(self._convert_to_direct_check(exp))
            else:  # gx
                gx_expectations.append(exp)
        
        # Estimate runtime
        estimated_runtime = self._estimate_runtime(
            len(gx_expectations),
            len(sql_checks),
            len(direct_checks),
            dataset_size_gb
        )
        
        plan = ExecutionPlan(
            dataset_name=dataset_name,
            gx_expectations=gx_expectations,
            sql_checks=sql_checks,
            direct_checks=direct_checks,
            estimated_runtime_seconds=estimated_runtime
        )
        
        self.logger.info(
            f"Execution plan: {len(gx_expectations)} GX, "
            f"{len(sql_checks)} SQL, {len(direct_checks)} Direct checks. "
            f"Estimated: {estimated_runtime:.1f}s"
        )
        
        return plan
    
    def _determine_backend(
        self,
        expectation: Any,
        dataset_size_gb: float
    ) -> Literal["gx", "sql", "direct"]:
        """Determine which backend should execute this expectation."""
        exp_type = getattr(expectation, 'expectation_type', '')
        
        # Check force SQL list
        if exp_type in self.force_sql or exp_type in self.SQL_ENGINE_TESTS:
            return "sql"
        
        # Check direct check list
        if exp_type in self.DIRECT_CHECK_TESTS:
            return "direct"
        
        # For very large tables, prefer SQL for certain operations
        if dataset_size_gb > self.size_threshold:
            if any(keyword in exp_type for keyword in ['aggregate', 'join', 'unique']):
                return "sql"
        
        # Default to GX for column-wise operations
        return "gx"
    
    def _convert_to_sql_check(self, expectation: Any) -> Dict[str, Any]:
        """Convert GX expectation to SQL check specification."""
        return {
            "type": "sql",
            "expectation_type": getattr(expectation, 'expectation_type', ''),
            "kwargs": getattr(expectation, 'kwargs', {}),
            "original_expectation": expectation
        }
    
    def _convert_to_direct_check(self, expectation: Any) -> Dict[str, Any]:
        """Convert expectation to direct DB check."""
        return {
            "type": "direct",
            "expectation_type": getattr(expectation, 'expectation_type', ''),
            "kwargs": getattr(expectation, 'kwargs', {})
        }
    
    def _estimate_runtime(
        self,
        gx_count: int,
        sql_count: int,
        direct_count: int,
        dataset_size_gb: float
    ) -> float:
        """
        Estimate total validation runtime.
        
        Uses simple heuristics and historical data.
        """
        # Base estimates (seconds)
        gx_base = 0.5  # Per expectation
        sql_base = 2.0  # Per SQL check
        direct_base = 0.1  # Per direct check
        
        # Size multiplier (logarithmic)
        import math
        size_multiplier = 1.0 + math.log10(max(dataset_size_gb, 0.1))
        
        estimated = (
            gx_count * gx_base * size_multiplier +
            sql_count * sql_base * size_multiplier +
            direct_count * direct_base
        )
        
        return estimated
    
    def update_performance_history(
        self,
        dataset_name: str,
        actual_runtime: float
    ) -> None:
        """Update performance history for future routing decisions."""
        self.performance_history[dataset_name] = actual_runtime
        self.logger.debug(f"Updated performance history for {dataset_name}: {actual_runtime}s")
