"""
Dynamic data profiler that generates baseline expectations automatically.
"""

import pandas as pd
import sqlalchemy as sa
from typing import Dict, List, Any, Optional
from great_expectations.core.batch import RuntimeBatchRequest
from great_expectations.data_context import DataContext
from great_expectations.data_context.types.base import DataContextConfig
from great_expectations.expectations.expectation_configuration import (
    ExpectationConfiguration,
)
import logging

from data_observability.core.config_parser import DatasetConfig, ColumnConfig

logger = logging.getLogger(__name__)


class DataProfiler:
    """
    Automatically generates Great Expectations test suites based on data analysis.
    
    Uses statistical profiling and pattern detection to create baseline validations
    that cover ~80% of common data quality issues without manual specification.
    """
    
    def __init__(
        self,
        sample_size: int = 10000,
        enable_advanced_profiling: bool = True
    ):
        """
        Initialize profiler.
        
        Args:
            sample_size: Number of rows to sample for profiling
            enable_advanced_profiling: Whether to generate distribution/pattern tests
        """
        self.sample_size = sample_size
        self.enable_advanced_profiling = enable_advanced_profiling
        self.logger = logger
    
    def profile_dataset(
        self,
        dataset_config: DatasetConfig,
        connection_string: str
    ) -> List[ExpectationConfiguration]:
        """
        Profile a dataset and generate expectations.
        
        Args:
            dataset_config: Dataset configuration
            connection_string: SQLAlchemy connection string
            
        Returns:
            List of generated expectations
        """
        self.logger.info(f"Profiling dataset: {dataset_config.name}")
        
        # Load sample data
        df = self._load_sample(dataset_config, connection_string)
        
        # Generate expectations
        expectations = []
        
        # Table-level expectations
        expectations.extend(self._generate_table_expectations(df, dataset_config))
        
        # Column-level expectations
        for column_config in dataset_config.columns:
            expectations.extend(
                self._generate_column_expectations(df, column_config)
            )
        
        # Auto-discover additional columns if not in config
        configured_columns = {col.name for col in dataset_config.columns}
        for column in df.columns:
            if column not in configured_columns:
                expectations.extend(
                    self._auto_profile_column(df, column)
                )
        
        self.logger.info(f"Generated {len(expectations)} expectations")
        return expectations
    
    def _load_sample(
        self,
        dataset_config: DatasetConfig,
        connection_string: str
    ) -> pd.DataFrame:
        """Load sample data for profiling."""
        engine = sa.create_engine(connection_string)
        
        if dataset_config.source.table:
            query = f"""
                SELECT * FROM {dataset_config.source.table}
                LIMIT {self.sample_size}
            """
        else:
            query = f"""
                SELECT * FROM ({dataset_config.source.query}) as subquery
                LIMIT {self.sample_size}
            """
        
        return pd.read_sql(query, engine)
    
    def _generate_table_expectations(
        self,
        df: pd.DataFrame,
        dataset_config: DatasetConfig
    ) -> List[ExpectationConfiguration]:
        """Generate table-level expectations."""
        expectations = []
        
        # Table must have columns
        expectations.append(
            ExpectationConfiguration(
                expectation_type="expect_table_columns_to_match_ordered_list",
                kwargs={"column_list": df.columns.tolist()}
            )
        )
        
        # Row count expectations from volume config
        if dataset_config.volume:
            if dataset_config.volume.expected_min_rows_per_run:
                expectations.append(
                    ExpectationConfiguration(
                        expectation_type="expect_table_row_count_to_be_between",
                        kwargs={
                            "min_value": dataset_config.volume.expected_min_rows_per_run,
                            "max_value": dataset_config.volume.expected_max_rows_per_run
                        }
                    )
                )
        
        return expectations
    
    def _generate_column_expectations(
        self,
        df: pd.DataFrame,
        column_config: ColumnConfig
    ) -> List[ExpectationConfiguration]:
        """Generate expectations for a configured column."""
        expectations = []
        column = column_config.name
        
        if column not in df.columns:
            self.logger.warning(f"Column {column} not found in dataset")
            return expectations
        
        # Process declared tests
        for test in column_config.tests:
            if test == "not_null":
                expectations.append(
                    ExpectationConfiguration(
                        expectation_type="expect_column_values_to_not_be_null",
                        kwargs={"column": column}
                    )
                )
            elif test == "unique":
                expectations.append(
                    ExpectationConfiguration(
                        expectation_type="expect_column_values_to_be_unique",
                        kwargs={"column": column}
                    )
                )
            elif test == "positive":
                expectations.append(
                    ExpectationConfiguration(
                        expectation_type="expect_column_values_to_be_between",
                        kwargs={"column": column, "min_value": 0}
                    )
                )
        
        # Valid range
        if column_config.valid_range:
            expectations.append(
                ExpectationConfiguration(
                    expectation_type="expect_column_values_to_be_between",
                    kwargs={
                        "column": column,
                        "min_value": column_config.valid_range[0],
                        "max_value": column_config.valid_range[1]
                    }
                )
            )
        
        # Valid values (set membership)
        if column_config.valid_values:
            expectations.append(
                ExpectationConfiguration(
                    expectation_type="expect_column_values_to_be_in_set",
                    kwargs={
                        "column": column,
                        "value_set": column_config.valid_values
                    }
                )
            )
        
        # Regex pattern
        if column_config.regex_pattern:
            expectations.append(
                ExpectationConfiguration(
                    expectation_type="expect_column_values_to_match_regex",
                    kwargs={
                        "column": column,
                        "regex": column_config.regex_pattern
                    }
                )
            )
        
        return expectations
    
    def _auto_profile_column(
        self,
        df: pd.DataFrame,
        column: str
    ) -> List[ExpectationConfiguration]:
        """
        Auto-generate expectations for a column based on data analysis.
        
        This is where the "magic" happens - automatically detecting patterns.
        """
        expectations = []
        series = df[column]
        
        # Null rate check - if < 5% nulls, enforce not null
        null_rate = series.isnull().sum() / len(series)
        if null_rate < 0.05:
            expectations.append(
                ExpectationConfiguration(
                    expectation_type="expect_column_values_to_not_be_null",
                    kwargs={"column": column}
                )
            )
        
        # Data type expectations
        if pd.api.types.is_numeric_dtype(series):
            # Check if all values are positive
            if series.min() >= 0:
                expectations.append(
                    ExpectationConfiguration(
                        expectation_type="expect_column_values_to_be_between",
                        kwargs={"column": column, "min_value": 0}
                    )
                )
            
            # If low cardinality numeric, might be categorical
            if series.nunique() < 20:
                expectations.append(
                    ExpectationConfiguration(
                        expectation_type="expect_column_values_to_be_in_set",
                        kwargs={
                            "column": column,
                            "value_set": series.dropna().unique().tolist()
                        }
                    )
                )
        
        elif pd.api.types.is_string_dtype(series):
            # Email pattern detection
            if series.str.contains(r'@', na=False).sum() > len(series) * 0.8:
                expectations.append(
                    ExpectationConfiguration(
                        expectation_type="expect_column_values_to_match_regex",
                        kwargs={
                            "column": column,
                            "regex": r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                        }
                    )
                )
            
            # Low cardinality strings - likely categorical
            if series.nunique() < 50:
                expectations.append(
                    ExpectationConfiguration(
                        expectation_type="expect_column_values_to_be_in_set",
                        kwargs={
                            "column": column,
                            "value_set": series.dropna().unique().tolist()
                        }
                    )
                )
        
        return expectations
    
    def generate_suite_file(
        self,
        expectations: List[ExpectationConfiguration],
        suite_name: str,
        output_path: str
    ) -> None:
        """
        Generate a Great Expectations suite JSON file.
        
        Args:
            expectations: List of expectations
            suite_name: Name of the suite
            output_path: Path to write suite JSON
        """
        import json
        
        suite = {
            "expectation_suite_name": suite_name,
            "expectations": [exp.to_json_dict() for exp in expectations],
            "data_asset_type": "Dataset",
            "meta": {
                "great_expectations_version": "0.16.8",
                "generated_by": "DataProfiler"
            }
        }
        
        with open(output_path, 'w') as f:
            json.dump(suite, f, indent=2)
        
        self.logger.info(f"Suite written to {output_path}")
