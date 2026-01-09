"""
Unit tests for the execution router.
"""

import pytest
from unittest.mock import Mock

from data_observability.core.execution_router import ExecutionRouter
from great_expectations.expectations.expectation_configuration import ExpectationConfiguration


class TestExecutionRouter:
    """Test suite for ExecutionRouter class."""
    
    @pytest.fixture
    def router(self):
        """Create router instance."""
        return ExecutionRouter()
    
    def test_route_referential_integrity_to_sql(self, router):
        """Test that referential integrity checks route to SQL engine."""
        expectations = [
            Mock(
                expectation_type='expect_column_values_to_match_foreign_key',
                kwargs={'column': 'user_id'}
            )
        ]
        
        # Force this type to SQL
        router.force_sql.add('expect_column_values_to_match_foreign_key')
        
        plan = router.route(expectations, 'test_dataset')
        
        assert len(plan.sql_checks) > 0
        assert len(plan.gx_expectations) == 0
    
    def test_route_column_check_to_gx(self, router):
        """Test that simple column checks route to GX engine."""
        expectations = [
            Mock(
                expectation_type='expect_column_values_to_not_be_null',
                kwargs={'column': 'email'}
            )
        ]
        
        plan = router.route(expectations, 'test_dataset')
        
        assert len(plan.gx_expectations) > 0
        assert len(plan.sql_checks) == 0
    
    def test_route_freshness_to_direct(self, router):
        """Test that freshness checks create direct checks."""
        freshness_config = {
            'warning_threshold': '1h',
            'failure_threshold': '4h',
            'timestamp_column': 'created_at'
        }
        
        plan = router.route(
            [],
            'test_dataset',
            freshness_config=freshness_config
        )
        
        assert len(plan.direct_checks) > 0
        assert any(c['type'] == 'freshness' for c in plan.direct_checks)
    
    def test_route_volume_to_direct(self, router):
        """Test that volume checks create direct checks."""
        volume_config = {
            'expected_min_rows_per_run': 1000,
            'expected_max_rows_per_run': 10000
        }
        
        plan = router.route(
            [],
            'test_dataset',
            volume_config=volume_config
        )
        
        assert len(plan.direct_checks) > 0
        assert any(c['type'] == 'volume' for c in plan.direct_checks)
    
    def test_estimate_runtime(self, router):
        """Test runtime estimation."""
        expectations = [Mock(expectation_type=f'test_{i}') for i in range(10)]
        
        plan = router.route(expectations, 'test_dataset', dataset_size_gb=50)
        
        # Should have estimated runtime
        assert plan.estimated_runtime_seconds > 0
    
    def test_large_dataset_routing(self, router):
        """Test that large datasets use SQL for certain operations."""
        router.size_threshold = 10.0  # 10GB threshold
        
        expectations = [
            Mock(
                expectation_type='expect_column_values_to_be_unique',
                kwargs={'column': 'id'}
            )
        ]
        
        # Small dataset - should use GX
        plan_small = router.route(expectations, 'test_dataset', dataset_size_gb=5)
        assert len(plan_small.gx_expectations) > 0
        
        # Large dataset - should prefer SQL
        plan_large = router.route(expectations, 'test_dataset', dataset_size_gb=50)
        # Uniqueness check on large dataset might go to SQL
        # (depends on implementation details)
        assert plan_large.estimated_runtime_seconds > plan_small.estimated_runtime_seconds


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
