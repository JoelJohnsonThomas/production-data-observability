"""
Integration test for end-to-end validation pipeline.
"""

import pytest
from pathlib import Path
import tempfile
import os

from data_observability.core.config_parser import ConfigParser, DatasetConfig
from data_observability.core.profiler import DataProfiler
from data_observability.core.execution_router import ExecutionRouter
from data_observability.models.database import DatabaseManager
from data_observability.models.results import Dataset, ValidationRun


@pytest.mark.integration
class TestEndToEndValidation:
    """Integration tests for complete validation pipeline."""
    
    @pytest.fixture(scope='class')
    def test_database(self):
        """Set up test database."""
        # Use in-memory SQLite for testing
        os.environ['WAREHOUSE_CONNECTION_STRING'] = 'sqlite:///:memory:'
        
        db_manager = DatabaseManager()
        db_manager.create_all_tables()
        
        yield db_manager
        
        # Cleanup would happen here
    
    @pytest.fixture
    def sample_config(self):
        """Create sample dataset configuration."""
        config_dict = {
            'dataset': {
                'name': 'test_transactions',
                'criticality': 'p2',
                'source': {
                    'type': 'postgresql',
                    'connection': 'test_db',
                    'table': 'transactions'
                },
                'freshness': {
                    'warning_threshold': '1h',
                    'failure_threshold': '4h',
                    'timestamp_column': 'created_at'
                },
                'volume': {
                    'expected_min_rows_per_run': 100,
                    'expected_max_rows_per_run': 10000
                },
                'columns': [
                    {
                        'name': 'id',
                        'tests': ['unique', 'not_null']
                    },
                    {
                        'name': 'amount',
                        'tests': ['not_null', 'positive'],
                        'valid_range': [0.01, 10000.00]
                    }
                ]
            }
        }
        
        return ConfigParser.load_from_dict(config_dict)
    
    def test_config_parsing(self, sample_config):
        """Test configuration parsing."""
        assert sample_config.name == 'test_transactions'
        assert sample_config.criticality.value == 'p2'
        assert len(sample_config.columns) == 2
        assert sample_config.freshness is not None
        assert sample_config.volume is not None
    
    def test_dataset_creation_in_warehouse(self, test_database, sample_config):
        """Test creating dataset record in warehouse."""
        with test_database.session_scope() as session:
            dataset = Dataset(
                name=sample_config.name,
                description=sample_config.description,
                criticality=sample_config.criticality,
                source_type=sample_config.source.type,
                source_table=sample_config.source.table
            )
            session.add(dataset)
            session.flush()
            
            assert dataset.id is not None
            assert dataset.name == 'test_transactions'
    
    def test_validation_run_creation(self, test_database, sample_config):
        """Test creating validation run record."""
        with test_database.session_scope() as session:
            # Create dataset first
            dataset = Dataset(
                name=sample_config.name,
                criticality=sample_config.criticality,
                source_type=sample_config.source.type,
                source_table=sample_config.source.table
            )
            session.add(dataset)
            session.flush()
            
            # Create validation run
            run = ValidationRun(
                dataset_id=dataset.id,
                execution_backend='gx',
                total_tests=10,
                passed_tests=8,
                failed_tests=2,
                success=False
            )
            session.add(run)
            session.flush()
            
            assert run.id is not None
            assert run.success is False
            assert run.failed_tests == 2
    
    def test_execution_router_planning(self, sample_config):
        """Test execution plan creation."""
        router = ExecutionRouter()
        
        # Create mock expectations
        from unittest.mock import Mock
        expectations = [
            Mock(expectation_type='expect_column_values_to_not_be_null'),
            Mock(expectation_type='expect_column_values_to_be_unique'),
        ]
        
        plan = router.route(
            expectations=expectations,
            dataset_name=sample_config.name,
            freshness_config=sample_config.freshness.dict() if sample_config.freshness else None,
            volume_config=sample_config.volume.dict() if sample_config.volume else None
        )
        
        # Should have routed checks
        assert plan.dataset_name == sample_config.name
        assert plan.estimated_runtime_seconds > 0
        
        # Should have direct checks for freshness and volume
        assert len(plan.direct_checks) >= 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
