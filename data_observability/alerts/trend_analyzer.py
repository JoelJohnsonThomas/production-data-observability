"""
Trend analysis engine for intelligent alert filtering.

Reduces false positives by analyzing failure patterns over time.
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import and_
import numpy as np
import logging

from data_observability.models.database import DatabaseManager
from data_observability.models.results import (
    ValidationRun, TestResult, Dataset, TestStatus
)

logger = logging.getLogger(__name__)


class TrendAnalyzer:
    """
    Analyzes validation trends to distinguish one-time glitches from systemic issues.
    
    Uses statistical methods to:
    - Detect sustained failure patterns
    - Filter transient errors
    - Calculate failure probability
    - Identify degradation trends
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager = None,
        lookback_hours: int = 24,
        failure_threshold: float = 0.3,  # 30% failure rate triggers alert
        consecutive_failures_threshold: int = 3
    ):
        """
        Initialize trend analyzer.
        
        Args:
            db_manager: Database manager for querying historical data
            lookback_hours: Hours of history to analyze
            failure_threshold: Failure rate threshold for alerting
            consecutive_failures_threshold: Consecutive failures to trigger
        """
        self.db_manager = db_manager or DatabaseManager()
        self.lookback_hours = lookback_hours
        self.failure_threshold = failure_threshold
        self.consecutive_threshold = consecutive_failures_threshold
        self.logger = logger
    
    def should_alert(
        self,
        dataset_name: str,
        test_type: str,
        current_failure: bool
    ) -> Dict[str, Any]:
        """
        Determine if an alert should be triggered based on trend analysis.
        
        Args:
            dataset_name: Name of dataset
            test_type: Type of test that failed
            current_failure: Whether current run failed
            
        Returns:
            Dictionary with alert decision and analysis
        """
        if not current_failure:
            return {
                "should_alert": False,
                "reason": "Current test passed"
            }
        
        self.logger.info(f"Analyzing trends for {dataset_name} - {test_type}")
        
        # Get historical results
        history = self._get_test_history(dataset_name, test_type)
        
        if not history:
            # No history - alert on first failure
            return {
                "should_alert": True,
                "reason": "First failure - no historical data",
                "confidence": "low"
            }
        
        # Analyze failure pattern
        failure_rate = self._calculate_failure_rate(history)
        consecutive_failures = self._count_consecutive_failures(history)
        trend_direction = self._analyze_trend_direction(history)
        
        # Decision logic
        should_alert = False
        reason = ""
        confidence = "medium"
        
        if consecutive_failures >= self.consecutive_threshold:
            should_alert = True
            reason = f"{consecutive_failures} consecutive failures detected"
            confidence = "high"
        elif failure_rate >= self.failure_threshold:
            should_alert = True
            reason = f"Failure rate {failure_rate:.1%} exceeds threshold {self.failure_threshold:.1%}"
            confidence = "high"
        elif trend_direction == "degrading":
            should_alert = True
            reason = "Degrading trend detected"
            confidence = "medium"
        else:
            should_alert = False
            reason = f"Transient failure. Rate: {failure_rate:.1%}, Consecutive: {consecutive_failures}"
            confidence = "high"
        
        return {
            "should_alert": should_alert,
            "reason": reason,
            "confidence": confidence,
            "failure_rate": failure_rate,
            "consecutive_failures": consecutive_failures,
            "trend_direction": trend_direction,
            "history_count": len(history)
        }
    
    def _get_test_history(
        self,
        dataset_name: str,
        test_type: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get historical test results."""
        cutoff_time = datetime.utcnow() - timedelta(hours=self.lookback_hours)
        
        with self.db_manager.session_scope() as session:
            query = (
                session.query(TestResult, ValidationRun)
                .join(ValidationRun)
                .join(Dataset)
                .filter(
                    and_(
                        Dataset.name == dataset_name,
                        TestResult.test.has(test_type=test_type),
                        ValidationRun.run_timestamp >= cutoff_time
                    )
                )
                .order_by(ValidationRun.run_timestamp.desc())
                .limit(limit)
            )
            
            results = query.all()
            
            return [
                {
                    "timestamp": run.run_timestamp,
                    "status": result.status,
                    "passed": result.status == TestStatus.PASSED
                }
                for result, run in results
            ]
    
    def _calculate_failure_rate(self, history: List[Dict[str, Any]]) -> float:
        """Calculate failure rate from history."""
        if not history:
            return 0.0
        
        failures = sum(1 for h in history if not h["passed"])
        return failures / len(history)
    
    def _count_consecutive_failures(self, history: List[Dict[str, Any]]) -> int:
        """Count consecutive failures from most recent."""
        if not history:
            return 0
        
        count = 0
        for h in history:
            if not h["passed"]:
                count += 1
            else:
                break
        
        return count
    
    def _analyze_trend_direction(
        self,
        history: List[Dict[str, Any]]
    ) -> str:
        """
        Analyze trend direction using moving averages.
        
        Returns:
            'improving', 'stable', or 'degrading'
        """
        if len(history) < 10:
            return "insufficient_data"
        
        # Convert to numeric (1 = pass, 0 = fail)
        values = np.array([1 if h["passed"] else 0 for h in reversed(history)])
        
        # Calculate moving averages
        window_size = min(5, len(values) // 2)
        recent_avg = np.mean(values[-window_size:])
        earlier_avg = np.mean(values[:window_size])
        
        diff = recent_avg - earlier_avg
        
        if diff > 0.2:
            return "improving"
        elif diff < -0.2:
            return "degrading"
        else:
            return "stable"
    
    def get_dataset_health_trend(
        self,
        dataset_name: str
    ) -> Dict[str, Any]:
        """Get overall health trend for a dataset."""
        cutoff_time = datetime.utcnow() - timedelta(hours=self.lookback_hours)
        
        with self.db_manager.session_scope() as session:
            # Get all validation runs in timeframe
            runs = (
                session.query(ValidationRun)
                .join(Dataset)
                .filter(
                    and_(
                        Dataset.name == dataset_name,
                        ValidationRun.run_timestamp >= cutoff_time
                    )
                )
                .order_by(ValidationRun.run_timestamp.desc())
                .all()
            )
            
            if not runs:
                return {
                    "status": "no_data",
                    "message": "No validation runs found"
                }
            
            # Calculate success rate
            successful_runs = sum(1 for r in runs if r.success)
            success_rate = successful_runs / len(runs)
            
            # Analyze trend
            recent_runs = runs[:10]
            recent_success_rate = sum(1 for r in recent_runs if r.success) / len(recent_runs)
            
            trend = "stable"
            if recent_success_rate > success_rate + 0.15:
                trend = "improving"
            elif recent_success_rate < success_rate - 0.15:
                trend = "degrading"
            
            return {
                "status": "healthy" if success_rate > 0.8 else "unhealthy",
                "success_rate": success_rate,
                "recent_success_rate": recent_success_rate,
                "trend": trend,
                "total_runs": len(runs),
                "successful_runs": successful_runs
            }
