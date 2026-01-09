"""
Unit tests for the data profiler.
"""

import pytest
from unittest.mock import Mock, patch
import pandas as pd

from data_observability.core.profiler import DataProfiler
from data_observability.core.config_parser import DatasetConfig, ColumnConfig


class TestDataProfiler:
    """Test suite for DataProfiler class."""
    
    @pytest.fixture
    def sample_dataframe(self):
        """Create a sample dataframe for testing."""
        return pd.DataFrame({
            'user_id': [1, 2, 3, 4, 5],
            'email': ['test1@example.com', 'test2@example.com', 'test3@example.com', 
                      'test4@example.com', 'test5@example.com'],
            'age': [25, 30, 35, None, 45],
            'status': ['active', 'active', 'inactive', 'active', 'active'],
            'amount': [100.50, 200.75, 150.25, 300.00, 175.50]
        })
    
    @pytest.fixture
    def profiler(self):
        """Create a profiler instance."""
        return DataProfiler(sample_size=1000)
    
    def test_auto_profile_column_not_null(self, profiler, sample_dataframe):
        """Test that columns with low null rate generate not_null expectation."""
        expectations = profiler._auto_profile_column(sample_dataframe, 'user_id')
        
        # Should generate not_null expectation since user_id has no nulls
        exp_types = [exp.expectation_type for exp in expectations]
        assert 'expect_column_values_to_not_be_null' in exp_types
    
    def test_auto_profile_column_email_pattern(self, profiler, sample_dataframe):
        """Test that email columns are detected and get regex expectation."""
        expectations = profiler._auto_profile_column(sample_dataframe, 'email')
        
        exp_types = [exp.expectation_type for exp in expectations]
        assert 'expect_column_values_to_match_regex' in exp_types
    
    def test_auto_profile_column_categorical(self, profiler, sample_dataframe):
        """Test that low-cardinality columns get value set expectation."""
        expectations = profiler._auto_profile_column(sample_dataframe, 'status')
        
        # Status has only 2 unique values - should be treated as categorical
        exp_types = [exp.expectation_type for exp in expectations]
        assert 'expect_column_values_to_be_in_set' in exp_types
    
    def test_auto_profile_column_positive_numeric(self, profiler, sample_dataframe):
        """Test that positive numeric columns get min_value expectation."""
        expectations = profiler._auto_profile_column(sample_dataframe, 'amount')
        
        # Amount column is all positive
        exp_types = [exp.expectation_type for exp in expectations]
        assert 'expect_column_values_to_be_between' in exp_types
        
        # Find the expectation and check min_value is 0
        for exp in expectations:
            if exp.expectation_type == 'expect_column_values_to_be_between':
                assert exp.kwargs.get('min_value') == 0
    
    @patch('data_observability.core.profiler.pd.read_sql')
    def test_profile_dataset(self, mock_read_sql, profiler, sample_dataframe):
        """Test complete dataset profiling."""
        mock_read_sql.return_value = sample_dataframe
        
        # Create mock config
        config = Mock(spec=DatasetConfig)
        config.name = "test_dataset"
        config.source = Mock()
        config.source.table = "test_table"
        config.columns = [
            Mock(spec=ColumnConfig, name='user_id', tests=['unique', 'not_null'])
        ]
        
        expectations = profiler.profile_dataset(config, "postgresql://test")
        
        # Should generate expectations
        assert len(expectations) > 0
        
        # Should include table-level expectations
        table_exps = [e for e in expectations 
                      if 'table' in e.expectation_type]
        assert len(table_exps) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
