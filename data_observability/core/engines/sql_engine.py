"""
Custom SQL execution engine for complex validations.
"""

from typing import List, Dict, Any
import sqlalchemy as sa
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


class SQLEngine:
    """
    Custom SQL execution engine for validations that are more efficient as SQL.
    
    Handles:
    - Referential integrity checks
    - Multi-table validations
    - Complex aggregations
    - Cross-dataset consistency checks
    """
    
    def __init__(self, timeout_seconds: int = 300):
        """
        Initialize SQL engine.
        
        Args:
            timeout_seconds: Query timeout
        """
        self.timeout = timeout_seconds
        self.logger = logger
    
    def execute(
        self,
        checks: List[Dict[str, Any]],
        connection_string: str,
        dataset_name: str = "default"
    ) -> Dict[str, Any]:
        """
        Execute SQL-based validation checks.
        
        Args:
            checks: List of SQL check specifications
            connection_string: SQLAlchemy connection string
            dataset_name: Name for reporting
            
        Returns:
            Standardized results dictionary
        """
        self.logger.info(f"Executing {len(checks)} SQL checks on {dataset_name}")
        
        engine = sa.create_engine(connection_string)
        results = []
        passed = 0
        failed = 0
        
        try:
            with engine.connect() as conn:
                for check in checks:
                    result = self._execute_check(conn, check, dataset_name)
                    results.append(result)
                    
                    if result["success"]:
                        passed += 1
                    else:
                        failed += 1
            
            return {
                "success": failed == 0,
                "dataset_name": dataset_name,
                "total_tests": len(checks),
                "passed_tests": passed,
                "failed_tests": failed,
                "results": results,
            }
            
        except Exception as e:
            self.logger.error(f"SQL execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "dataset_name": dataset_name,
                "total_tests": len(checks),
                "passed_tests": 0,
                "failed_tests": len(checks),
            }
    
    def _execute_check(
        self,
        conn: sa.engine.Connection,
        check: Dict[str, Any],
        dataset_name: str
    ) -> Dict[str, Any]:
        """Execute a single SQL check."""
        check_type = check.get("expectation_type", "")
        
        try:
            # Route to specific check implementation
            if "referential_integrity" in check_type:
                return self._check_referential_integrity(conn, check, dataset_name)
            elif "unique" in check_type:
                return self._check_uniqueness(conn, check, dataset_name)
            elif "aggregate" in check_type:
                return self._check_aggregate(conn, check, dataset_name)
            else:
                # Generic SQL check from config
                return self._execute_custom_sql(conn, check, dataset_name)
                
        except Exception as e:
            self.logger.error(f"Check failed: {check_type} - {e}")
            return {
                "check_type": check_type,
                "success": False,
                "error": str(e)
            }
    
    def _check_referential_integrity(
        self,
        conn: sa.engine.Connection,
        check: Dict[str, Any],
        dataset_name: str
    ) -> Dict[str, Any]:
        """Check foreign key relationships."""
        kwargs = check.get("kwargs", {})
        column = kwargs.get("column")
        references = kwargs.get("references", "")  # Format: "table.column"
        
        if "." not in references:
            return {
                "check_type": "referential_integrity",
                "success": False,
                "error": "Invalid reference format. Use 'table.column'"
            }
        
        ref_table, ref_column = references.split(".", 1)
        
        # Find orphaned records
        query = text(f"""
            SELECT COUNT(*) as orphan_count
            FROM {dataset_name}
            WHERE {column} IS NOT NULL
              AND {column} NOT IN (
                  SELECT {ref_column} FROM {ref_table}
              )
        """)
        
        result = conn.execute(query).fetchone()
        orphan_count = result[0]
        
        return {
            "check_type": "referential_integrity",
            "success": orphan_count == 0,
            "column": column,
            "references": references,
            "orphan_count": orphan_count,
        }
    
    def _check_uniqueness(
        self,
        conn: sa.engine.Connection,
        check: Dict[str, Any],
        dataset_name: str
    ) -> Dict[str, Any]:
        """Check for duplicate values."""
        kwargs = check.get("kwargs", {})
        columns = kwargs.get("column_list", [kwargs.get("column")])
        
        column_str = ", ".join(columns)
        
        query = text(f"""
            SELECT COUNT(*) as duplicate_count
            FROM (
                SELECT {column_str}, COUNT(*) as cnt
                FROM {dataset_name}
                GROUP BY {column_str}
                HAVING COUNT(*) > 1
            ) duplicates
        """)
        
        result = conn.execute(query).fetchone()
        duplicate_count = result[0]
        
        return {
            "check_type": "uniqueness",
            "success": duplicate_count == 0,
            "columns": columns,
            "duplicate_count": duplicate_count,
        }
    
    def _check_aggregate(
        self,
        conn: sa.engine.Connection,
        check: Dict[str, Any],
        dataset_name: str
    ) -> Dict[str, Any]:
        """Execute aggregate validation."""
        kwargs = check.get("kwargs", {})
        query_text = kwargs.get("sql_query")
        
        if not query_text:
            return {
                "check_type": "aggregate",
                "success": False,
                "error": "No SQL query provided"
            }
        
        result = conn.execute(text(query_text)).fetchone()
        
        # Expect query to return a boolean or numeric result
        # Convention: 0 or False = success, >0 or True = failure
        passes = result[0] == 0 or result[0] is False
        
        return {
            "check_type": "aggregate",
            "success": passes,
            "observed_value": result[0],
        }
    
    def _execute_custom_sql(
        self,
        conn: sa.engine.Connection,
        check: Dict[str, Any],
        dataset_name: str
    ) -> Dict[str, Any]:
        """Execute custom SQL from configuration."""
        kwargs = check.get("kwargs", {})
        sql = kwargs.get("custom_sql")
        
        if not sql:
            return {
                "check_type": "custom_sql",
                "success": False,
                "error": "No custom SQL provided"
            }
        
        result = conn.execute(text(sql)).fetchone()
        
        return {
            "check_type": "custom_sql",
            "success": result[0] == 0,
            "observed_value": result[0],
        }
