"""
SQLAlchemy ORM models for observability warehouse.

Star schema design:
- Fact tables: validation_runs, test_results, alerts
- Dimension tables: datasets, tests
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Float, Text,
    ForeignKey, JSON, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum

from data_observability.models.database import Base


class CriticalityLevel(enum.Enum):
    """Dataset criticality levels."""
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"


class TestStatus(enum.Enum):
    """Test execution status."""
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class AlertStatus(enum.Enum):
    """Alert status."""
    TRIGGERED = "triggered"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class Dataset(Base):
    """Dimension table for datasets being monitored."""
    
    __tablename__ = "datasets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text)
    criticality = Column(SQLEnum(CriticalityLevel), nullable=False)
    source_type = Column(String(50))  # postgresql, bigquery, etc.
    source_table = Column(String(255))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    validation_runs = relationship("ValidationRun", back_populates="dataset")
    alerts = relationship("Alert", back_populates="dataset")


class Test(Base):
    """Dimension table for test definitions."""
    
    __tablename__ = "tests"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    test_type = Column(String(100), nullable=False)  # expectation type
    description = Column(Text)
    column_name = Column(String(255))
    parameters = Column(JSON)  # Test-specific parameters
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    test_results = relationship("TestResult", back_populates="test")


class ValidationRun(Base):
    """Fact table for validation run metadata."""
    
    __tablename__ = "validation_runs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    run_timestamp = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    execution_backend = Column(String(50))  # gx, sql, direct
    total_tests = Column(Integer)
    passed_tests = Column(Integer)
    failed_tests = Column(Integer)
    error_tests = Column(Integer)
    skipped_tests = Column(Integer)
    execution_time_seconds = Column(Float)
    success = Column(Boolean, nullable=False)
    metadata = Column(JSON)  # Additional run metadata
    
    # Relationships
    dataset = relationship("Dataset", back_populates="validation_runs")
    test_results = relationship("TestResult", back_populates="validation_run")


class TestResult(Base):
    """Fact table for individual test results."""
    
    __tablename__ = "test_results"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    validation_run_id = Column(Integer, ForeignKey("validation_runs.id"), nullable=False, index=True)
    test_id = Column(Integer, ForeignKey("tests.id"), nullable=False, index=True)
    status = Column(SQLEnum(TestStatus), nullable=False)
    observed_value = Column(Text)  # JSON serialized observed value
    expected_value = Column(Text)  # JSON serialized expected value
    error_message = Column(Text)
    execution_time_seconds = Column(Float)
    metadata = Column(JSON)
    
    # Relationships
    validation_run = relationship("ValidationRun", back_populates="test_results")
    test = relationship("Test", back_populates="test_results")


class Alert(Base):
    """Fact table for triggered alerts."""
    
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    validation_run_id = Column(Integer, ForeignKey("validation_runs.id"), index=True)
    alert_type = Column(String(100))  # freshness, volume, test_failure, etc.
    severity = Column(SQLEnum(CriticalityLevel), nullable=False)
    status = Column(SQLEnum(AlertStatus), nullable=False, default=AlertStatus.TRIGGERED)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    triggered_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    acknowledged_at = Column(DateTime)
    resolved_at = Column(DateTime)
    acknowledged_by = Column(String(255))
    notification_sent = Column(Boolean, default=False)
    notification_channel = Column(String(100))  # slack, pagerduty, email
    metadata = Column(JSON)
    
    # Relationships
    dataset = relationship("Dataset", back_populates="alerts")


class HealthScore(Base):
    """Table for storing computed health scores over time."""
    
    __tablename__ = "health_scores"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False, index=True)
    computed_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    score = Column(Float, nullable=False)  # 0-100
    passing_rate = Column(Float)  # Percentage of passing tests
    freshness_score = Column(Float)
    volume_score = Column(Float)
    quality_score = Column(Float)
    trend_direction = Column(String(20))  # improving, stable, degrading
    metadata = Column(JSON)


# Create indexes for performance
from sqlalchemy import Index

# Composite indexes for common queries
Index('idx_test_results_run_status', TestResult.validation_run_id, TestResult.status)
Index('idx_alerts_dataset_status', Alert.dataset_id, Alert.status)
Index('idx_validation_runs_dataset_time', ValidationRun.dataset_id, ValidationRun.run_timestamp)
