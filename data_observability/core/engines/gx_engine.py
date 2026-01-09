"""
Great Expectations execution engine with optimizations.
"""

from typing import List, Dict, Any
import pandas as pd
import sqlalchemy as sa
from great_expectations.data_context import DataContext
from great_expectations.core.batch import RuntimeBatchRequest
from great_expectations.checkpoint import SimpleCheckpoint
import logging

logger = logging.getLogger(__name__)


class GXEngine:
    """
    Wrapper around Great Expectations with performance optimizations.
    
    Features:
    - Smart sampling for large datasets
    - Batch execution
    - Result standardization
    """
    
    def __init__(
        self,
        sample_size: int = 100000,
        enable_sampling: bool = True
    ):
        """
        Initialize GX engine.
        
        Args:
            sample_size: Number of rows to sample for validation
            enable_sampling: Whether to use sampling for large datasets
        """
        self.sample_size = sample_size
        self.enable_sampling = enable_sampling
        self.logger = logger
    
    def execute(
        self,
        expectations: List[Any],
        connection_string: str,
        table_name: str = None,
        query: str = None,
        dataset_name: str = "default"
    ) -> Dict[str, Any]:
        """
        Execute Great Expectations validations.
        
        Args:
            expectations: List of ExpectationConfiguration objects
            connection_string: SQLAlchemy connection string
            table_name: Table to validate
            query: Custom query to validate
            dataset_name: Name for reporting
            
        Returns:
            Standardized results dictionary
        """
        self.logger.info(f"Executing {len(expectations)} GX expectations on {dataset_name}")
        
        try:
            # Create in-memory data context
            context = self._create_context()
            
            # Add datasource
            datasource_config = {
                "name": "validation_datasource",
                "class_name": "Datasource",
                "execution_engine": {
                    "class_name": "SqlAlchemyExecutionEngine",
                    "connection_string": connection_string,
                },
                "data_connectors": {
                    "default_runtime_data_connector": {
                        "class_name": "RuntimeDataConnector",
                        "batch_identifiers": ["default_identifier"],
                    }
                },
            }
            
            # Get or create datasource
            try:
                context.add_datasource(**datasource_config)
            except Exception as e:
                self.logger.debug(f"Datasource may already exist: {e}")
            
            # Create batch request
            if table_name:
                batch_request = RuntimeBatchRequest(
                    datasource_name="validation_datasource",
                    data_connector_name="default_runtime_data_connector",
                    data_asset_name=table_name,
                    runtime_parameters={
                        "query": f"SELECT * FROM {table_name} LIMIT {self.sample_size}"
                    } if self.enable_sampling else {"query": f"SELECT * FROM {table_name}"},
                    batch_identifiers={"default_identifier": dataset_name},
                )
            else:
                batch_request = RuntimeBatchRequest(
                    datasource_name="validation_datasource",
                    data_connector_name="default_runtime_data_connector",
                    data_asset_name="custom_query",
                    runtime_parameters={"query": query},
                    batch_identifiers={"default_identifier": dataset_name},
                )
            
            # Create expectation suite
            suite_name = f"{dataset_name}_validation_suite"
            context.create_expectation_suite(
                expectation_suite_name=suite_name,
                overwrite_existing=True
            )
            suite = context.get_expectation_suite(suite_name)
            
            # Add expectations to suite
            for exp in expectations:
                suite.add_expectation(exp)
            
            # Save suite
            context.save_expectation_suite(suite)
            
            # Create and run checkpoint
            checkpoint_config = {
                "name": f"{dataset_name}_checkpoint",
                "config_version": 1.0,
                "class_name": "SimpleCheckpoint",
                "validations": [
                    {
                        "batch_request": batch_request,
                        "expectation_suite_name": suite_name,
                    }
                ],
            }
            
            results = context.run_checkpoint(
                checkpoint_name=f"{dataset_name}_checkpoint",
                checkpoint_config=checkpoint_config,
            )
            
            # Standardize results
            standardized = self._standardize_results(results, dataset_name)
            
            self.logger.info(
                f"GX validation complete. Success: {standardized['success']}, "
                f"Tests: {standardized['total_tests']}"
            )
            
            return standardized
            
        except Exception as e:
            self.logger.error(f"GX execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "dataset_name": dataset_name,
                "total_tests": len(expectations),
                "passed_tests": 0,
                "failed_tests": len(expectations),
            }
    
    def _create_context(self) -> DataContext:
        """Create an ephemeral in-memory DataContext."""
        from great_expectations.data_context.types.base import (
            DataContextConfig,
            InMemoryStoreBackendDefaults,
        )
        
        context_config = DataContextConfig(
            store_backend_defaults=InMemoryStoreBackendDefaults(),
            checkpoint_store_name="checkpoint_store",
        )
        
        return DataContext(context_config)
    
    def _standardize_results(
        self,
        gx_results: Any,
        dataset_name: str
    ) -> Dict[str, Any]:
        """Convert GX results to standardized format."""
        validation_results = gx_results.list_validation_results()
        
        if not validation_results:
            return {
                "success": False,
                "dataset_name": dataset_name,
                "total_tests": 0,
                "passed_tests": 0,
                "failed_tests": 0,
                "results": []
            }
        
        result = validation_results[0]
        
        total = result.get("statistics", {}).get("evaluated_expectations", 0)
        successful = result.get("statistics", {}).get("successful_expectations", 0)
        failed = total - successful
        
        test_results = []
        for exp_result in result.get("results", []):
            test_results.append({
                "expectation_type": exp_result.get("expectation_config", {}).get("expectation_type"),
                "success": exp_result.get("success"),
                "column": exp_result.get("expectation_config", {}).get("kwargs", {}).get("column"),
                "observed_value": exp_result.get("result", {}).get("observed_value"),
            })
        
        return {
            "success": result.get("success", False),
            "dataset_name": dataset_name,
            "total_tests": total,
            "passed_tests": successful,
            "failed_tests": failed,
            "results": test_results,
            "execution_time": result.get("meta", {}).get("run_time"),
        }
