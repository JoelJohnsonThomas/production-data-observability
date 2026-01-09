"""
Direct database check engine for metadata and lightweight validations.
"""

from typing import Dict, Any, List
import sqlalchemy as sa
from sqlalchemy import text
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class DirectCheckEngine:
    """
    Lightweight engine for direct database metadata checks.
    
    Handles:
    - Freshness monitoring (timestamp checks)
    - Volume thresholds (row counts)
    - Table existence
    - Schema validation
    """
    
    def __init__(self):
        """Initialize direct check engine."""
        self.logger = logger
    
    def execute(
        self,
        checks: List[Dict[str, Any]],
        connection_string: str,
        table_name: str,
        dataset_name: str = "default"
    ) -> Dict[str, Any]:
        """
        Execute direct database checks.
        
        Args:
            checks: List of check specifications
            connection_string: SQLAlchemy connection string
            table_name: Table to check
            dataset_name: Name for reporting
            
        Returns:
            Standardized results dictionary
        """
        self.logger.info(f"Executing {len(checks)} direct checks on {dataset_name}")
        
        engine = sa.create_engine(connection_string)
        results = []
        passed = 0
        failed = 0
        
        try:
            with engine.connect() as conn:
                for check in checks:
                    result = self._execute_check(conn, check, table_name, dataset_name)
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
            self.logger.error(f"Direct check execution failed: {e}", exc_info=True)
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
        table_name: str,
        dataset_name: str
    ) -> Dict[str, Any]:
        """Execute a single direct check."""
        check_type = check.get("type")
        
        try:
            if check_type == "freshness":
                return self._check_freshness(conn, check, table_name)
            elif check_type == "volume":
                return self._check_volume(conn, check, table_name)
            elif check_type == "table_exists":
                return self._check_table_exists(conn, table_name)
            else:
                return {
                    "check_type": check_type,
                    "success": False,
                    "error": f"Unknown check type: {check_type}"
                }
                
        except Exception as e:
            return {
                "check_type": check_type,
                "success": False,
                "error": str(e)
            }
    
    def _check_freshness(
        self,
        conn: sa.engine.Connection,
        check: Dict[str, Any],
        table_name: str
    ) -> Dict[str, Any]:
        """Check data freshness based on timestamp column."""
        config = check.get("config", {})
        timestamp_column = config.get("timestamp_column", "updated_at")
        failure_threshold = config.get("failure_threshold", "4h")
        
        # Parse threshold
        threshold_seconds = self._parse_time_threshold(failure_threshold)
        threshold_time = datetime.utcnow() - timedelta(seconds=threshold_seconds)
        
        # Get latest timestamp
        query = text(f"""
            SELECT MAX({timestamp_column}) as latest_timestamp
            FROM {table_name}
        """)
        
        result = conn.execute(query).fetchone()
        latest_timestamp = result[0]
        
        if latest_timestamp is None:
            return {
                "check_type": "freshness",
                "success": False,
                "error": "No timestamp found",
                "latest_timestamp": None,
            }
        
        # Convert to datetime if needed
        if isinstance(latest_timestamp, str):
            latest_timestamp = datetime.fromisoformat(latest_timestamp)
        
        is_fresh = latest_timestamp >= threshold_time
        staleness_seconds = (datetime.utcnow() - latest_timestamp).total_seconds()
        
        return {
            "check_type": "freshness",
            "success": is_fresh,
            "latest_timestamp": latest_timestamp.isoformat(),
            "staleness_seconds": staleness_seconds,
            "threshold_seconds": threshold_seconds,
        }
    
    def _check_volume(
        self,
        conn: sa.engine.Connection,
        check: Dict[str, Any],
        table_name: str
    ) -> Dict[str, Any]:
        """Check row count against expected thresholds."""
        config = check.get("config", {})
        min_rows = config.get("expected_min_rows_per_run")
        max_rows = config.get("expected_max_rows_per_run")
        
        # Get current row count
        query = text(f"SELECT COUNT(*) as row_count FROM {table_name}")
        result = conn.execute(query).fetchone()
        row_count = result[0]
        
        success = True
        violations = []
        
        if min_rows is not None and row_count < min_rows:
            success = False
            violations.append(f"Row count {row_count} below minimum {min_rows}")
        
        if max_rows is not None and row_count > max_rows:
            success = False
            violations.append(f"Row count {row_count} above maximum {max_rows}")
        
        return {
            "check_type": "volume",
            "success": success,
            "row_count": row_count,
            "expected_min": min_rows,
            "expected_max": max_rows,
            "violations": violations,
        }
    
    def _check_table_exists(
        self,
        conn: sa.engine.Connection,
        table_name: str
    ) -> Dict[str, Any]:
        """Verify table exists."""
        inspector = sa.inspect(conn)
        tables = inspector.get_table_names()
        
        exists = table_name in tables
        
        return {
            "check_type": "table_exists",
            "success": exists,
            "table_name": table_name,
        }
    
    def _parse_time_threshold(self, threshold: str) -> int:
        """Convert time threshold string to seconds."""
        units = {
            's': 1,
            'm': 60,
            'h': 3600,
            'd': 86400
        }
        
        value = int(threshold[:-1])
        unit = threshold[-1]
        
        if unit not in units:
            raise ValueError(f"Invalid time unit: {unit}")
        
        return value * units[unit]
