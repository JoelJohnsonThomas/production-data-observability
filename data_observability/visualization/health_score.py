"""
Health score calculation for datasets.

Computes a 0-100 health score based on multiple dimensions.
"""

from typing import Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import and_, func
import logging

from data_observability.models.database import DatabaseManager
from data_observability.models.results import (
    Dataset, ValidationRun, TestResult, TestStatus, HealthScore
)

logger = logging.getLogger(__name__)


class HealthScoreCalculator:
    """
    Calculates health scores for datasets based on multiple dimensions:
    - Quality: Percentage of passing tests
    - Freshness: How recent the data is
    - Volume: Whether data volume is within expected range
    - Trends: Improvement or degradation over time
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager = None,
        lookback_hours: int = 168  # 7 days
    ):
        """
        Initialize health score calculator.
        
        Args:
            db_manager: Database manager
            lookback_hours: Hours of history to consider
        """
        self.db_manager = db_manager or DatabaseManager()
        self.lookback_hours = lookback_hours
        self.logger = logger
    
    def calculate_health_score(self, dataset_name: str) -> Dict[str, Any]:
        """
        Calculate comprehensive health score for a dataset.
        
        Args:
            dataset_name: Name of dataset
            
        Returns:
            Dictionary with overall score and component scores
        """
        self.logger.info(f"Calculating health score for {dataset_name}")
        
        with self.db_manager.session_scope() as session:
            dataset = session.query(Dataset).filter_by(name=dataset_name).first()
            
            if not dataset:
                return {
                    "error": f"Dataset {dataset_name} not found",
                    "score": 0
                }
            
            cutoff_time = datetime.utcnow() - timedelta(hours=self.lookback_hours)
            
            # Get recent validation runs
            runs = (
                session.query(ValidationRun)
                .filter(
                    and_(
                        ValidationRun.dataset_id == dataset.id,
                        ValidationRun.run_timestamp >= cutoff_time
                    )
                )
                .order_by(ValidationRun.run_timestamp.desc())
                .all()
            )
            
            if not runs:
                return {
                    "score": 0,
                    "message": "No validation runs found",
                    "dataset_name": dataset_name
                }
            
            # Calculate component scores
            quality_score = self._calculate_quality_score(runs)
            freshness_score = self._calculate_freshness_score(runs)
            volume_score = self._calculate_volume_score(runs)
            trend_score = self._calculate_trend_score(runs)
            
            # Weighted overall score
            # Quality is most important, then freshness, then volume, then trend
            overall_score = (
                quality_score * 0.50 +
                freshness_score * 0.25 +
                volume_score * 0.15 +
                trend_score * 0.10
            )
            
            # Determine trend direction
            recent_avg = sum(r.success for r in runs[:5]) / min(5, len(runs))
            earlier_avg = sum(r.success for r in runs[-5:]) / min(5, len(runs))
            
            if recent_avg > earlier_avg + 0.2:
                trend_direction = "improving"
            elif recent_avg < earlier_avg - 0.2:
                trend_direction = "degrading"
            else:
                trend_direction = "stable"
            
            result = {
                "score": round(overall_score, 1),
                "dataset_name": dataset_name,
                "quality_score": round(quality_score, 1),
                "freshness_score": round(freshness_score, 1),
                "volume_score": round(volume_score, 1),
                "trend_score": round(trend_score, 1),
                "trend_direction": trend_direction,
                "total_runs": len(runs),
                "computed_at": datetime.utcnow().isoformat()
            }
            
            # Store health score
            health_score = HealthScore(
                dataset_id=dataset.id,
                score=overall_score,
                passing_rate=quality_score / 100.0,
                freshness_score=freshness_score,
                volume_score=volume_score,
                quality_score=quality_score,
                trend_direction=trend_direction,
                metadata=result
            )
            session.add(health_score)
            
            return result
    
    def _calculate_quality_score(self, runs: list) -> float:
        """
        Calculate quality score based on test pass rate.
        
        100 = all tests passing
        0 = all tests failing
        """
        if not runs:
            return 0.0
        
        total_tests = sum(r.total_tests for r in runs if r.total_tests)
        passed_tests = sum(r.passed_tests for r in runs if r.passed_tests)
        
        if total_tests == 0:
            return 100.0
        
        pass_rate = passed_tests / total_tests
        return pass_rate * 100.0
    
    def _calculate_freshness_score(self, runs: list) -> float:
        """
        Calculate freshness score based on recency of last run.
        
        100 = run within last hour
        0 = no run in last week
        """
        if not runs:
            return 0.0
        
        latest_run = runs[0]
        age_hours = (datetime.utcnow() - latest_run.run_timestamp).total_seconds() / 3600
        
        if age_hours < 1:
            return 100.0
        elif age_hours < 4:
            return 90.0
        elif age_hours < 12:
            return 75.0
        elif age_hours < 24:
            return 60.0
        elif age_hours < 48:
            return 40.0
        elif age_hours < 168:  # 1 week
            return 20.0
        else:
            return 0.0
    
    def _calculate_volume_score(self, runs: list) -> float:
        """
        Calculate volume score based on data volume stability.
        
        100 = volume is consistent
        Lower scores for high variance
        """
        # Simplified - in production, would compare against expected volumes
        # For now, just check if runs are happening consistently
        
        if len(runs) < 2:
            return 100.0
        
        # Check run frequency (should be regular)
        time_gaps = []
        for i in range(len(runs) - 1):
            gap = (runs[i].run_timestamp - runs[i+1].run_timestamp).total_seconds() / 3600
            time_gaps.append(gap)
        
        if not time_gaps:
            return 100.0
        
        avg_gap = sum(time_gaps) / len(time_gaps)
        max_gap = max(time_gaps)
        
        # If max gap is more than 3x average, penalize
        if max_gap > avg_gap * 3:
            return 70.0
        elif max_gap > avg_gap * 2:
            return 85.0
        else:
            return 100.0
    
    def _calculate_trend_score(self, runs: list) -> float:
        """
        Calculate trend score based on improvement or degradation.
        
        100 = improving
        50 = stable
        0 = degrading
        """
        if len(runs) < 10:
            return 50.0  # Neutral/stable
        
        # Compare recent vs earlier success rates
        recent_runs = runs[:5]
        earlier_runs = runs[-5:]
        
        recent_success_rate = sum(1 for r in recent_runs if r.success) / len(recent_runs)
        earlier_success_rate = sum(1 for r in earlier_runs if r.success) / len(earlier_runs)
        
        diff = recent_success_rate - earlier_success_rate
        
        if diff > 0.2:
            return 100.0  # Improving
        elif diff > 0:
            return 75.0  # Slightly improving
        elif diff > -0.2:
            return 50.0  # Stable
        elif diff > -0.4:
            return 25.0  # Degrading
        else:
            return 0.0  # Severely degrading
    
    def get_all_dataset_scores(self) -> list:
        """Get health scores for all datasets."""
        with self.db_manager.session_scope() as session:
            datasets = session.query(Dataset).all()
            
            scores = []
            for dataset in datasets:
                score = self.calculate_health_score(dataset.name)
                scores.append(score)
            
            return sorted(scores, key=lambda x: x.get("score", 0), reverse=True)
