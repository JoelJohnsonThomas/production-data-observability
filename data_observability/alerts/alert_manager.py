"""
Alert manager for routing and delivery of data quality alerts.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import requests
import logging
import os

from data_observability.models.database import DatabaseManager
from data_observability.models.results import Alert, Dataset, CriticalityLevel, AlertStatus
from data_observability.alerts.trend_analyzer import TrendAnalyzer

logger = logging.getLogger(__name__)


class AlertManager:
    """
    Manages alert routing, deduplication, and delivery.
    
    Features:
    - Severity-based routing (P1→PagerDuty, P2→Slack, P3→Dashboard)
    - Alert deduplication
    - Trend-aware triggering
    - Integration with external services
    """
    
    def __init__(
        self,
        db_manager: DatabaseManager = None,
        trend_analyzer: TrendAnalyzer = None,
        enable_trend_filtering: bool = True
    ):
        """
        Initialize alert manager.
        
        Args:
            db_manager: Database manager
            trend_analyzer: Trend analyzer for filtering
            enable_trend_filtering: Whether to use trend analysis
        """
        self.db_manager = db_manager or DatabaseManager()
        self.trend_analyzer = trend_analyzer or TrendAnalyzer(self.db_manager)
        self.enable_trend_filtering = enable_trend_filtering
        self.logger = logger
        
        # Load configuration from environment
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        self.pagerduty_key = os.getenv("PAGERDUTY_INTEGRATION_KEY")
        self.email_config = {
            "smtp_host": os.getenv("SMTP_HOST"),
            "smtp_port": os.getenv("SMTP_PORT"),
            "smtp_user": os.getenv("SMTP_USER"),
            "smtp_password": os.getenv("SMTP_PASSWORD"),
            "to_address": os.getenv("ALERT_EMAIL_TO")
        }
    
    def process_validation_results(
        self,
        dataset_name: str,
        validation_results: Dict[str, Any],
        validation_run_id: int
    ) -> List[Alert]:
        """
        Process validation results and trigger alerts if needed.
        
        Args:
            dataset_name: Name of dataset
            validation_results: Validation results dictionary
            validation_run_id: ID of validation run
            
        Returns:
            List of triggered alerts
        """
        self.logger.info(f"Processing validation results for {dataset_name}")
        
        triggered_alerts = []
        
        # Get dataset info
        with self.db_manager.session_scope() as session:
            dataset = session.query(Dataset).filter_by(name=dataset_name).first()
            
            if not dataset:
                self.logger.error(f"Dataset {dataset_name} not found")
                return triggered_alerts
            
            criticality = dataset.criticality
        
        # Check overall validation success
        if not validation_results.get("success"):
            alert_decision = self._should_trigger_alert(
                dataset_name,
                "validation_failure",
                True
            )
            
            if alert_decision["should_alert"]:
                alert = self._create_alert(
                    dataset_name=dataset_name,
                    alert_type="validation_failure",
                    severity=criticality,
                    validation_run_id=validation_run_id,
                    title=f"Data Quality Alert: {dataset_name} validation failed",
                    description=(
                        f"Validation run failed. "
                        f"Failed tests: {validation_results.get('failed_tests', 0)}. "
                        f"Reason: {alert_decision['reason']}"
                    ),
                    metadata={
                        "trend_analysis": alert_decision,
                        "validation_summary": validation_results
                    }
                )
                
                triggered_alerts.append(alert)
                self._deliver_alert(alert)
        
        return triggered_alerts
    
    def _should_trigger_alert(
        self,
        dataset_name: str,
        alert_type: str,
        failure_occurred: bool
    ) -> Dict[str, Any]:
        """Determine if alert should be triggered based on trend analysis."""
        if not self.enable_trend_filtering:
            return {
                "should_alert": failure_occurred,
                "reason": "Trend filtering disabled"
            }
        
        return self.trend_analyzer.should_alert(
            dataset_name=dataset_name,
            test_type=alert_type,
            current_failure=failure_occurred
        )
    
    def _create_alert(
        self,
        dataset_name: str,
        alert_type: str,
        severity: CriticalityLevel,
        validation_run_id: int,
        title: str,
        description: str,
        metadata: Dict[str, Any] = None
    ) -> Alert:
        """Create and store an alert."""
        with self.db_manager.session_scope() as session:
            # Get dataset ID
            dataset = session.query(Dataset).filter_by(name=dataset_name).first()
            
            alert = Alert(
                dataset_id=dataset.id,
                validation_run_id=validation_run_id,
                alert_type=alert_type,
                severity=severity,
                status=AlertStatus.TRIGGERED,
                title=title,
                description=description,
                triggered_at=datetime.utcnow(),
                metadata=metadata or {}
            )
            
            session.add(alert)
            session.flush()
            
            alert_id = alert.id
        
        self.logger.info(f"Alert created: {alert_id} - {title}")
        return alert
    
    def _deliver_alert(self, alert: Alert) -> None:
        """Route and deliver alert based on severity."""
        severity = alert.severity
        
        try:
            if severity == CriticalityLevel.P1:
                # Critical - send to PagerDuty AND Slack
                self._send_to_pagerduty(alert)
                self._send_to_slack(alert, urgent=True)
            elif severity == CriticalityLevel.P2:
                # Medium - send to Slack
                self._send_to_slack(alert, urgent=False)
            else:  # P3
                # Low - dashboard only (already in DB)
                self.logger.info(f"P3 alert {alert.id} - dashboard only")
            
            # Mark notification as sent
            with self.db_manager.session_scope() as session:
                db_alert = session.query(Alert).get(alert.id)
                db_alert.notification_sent = True
                db_alert.notification_channel = self._get_channel_name(severity)
                
        except Exception as e:
            self.logger.error(f"Failed to deliver alert {alert.id}: {e}", exc_info=True)
    
    def _send_to_slack(self, alert: Alert, urgent: bool = False) -> None:
        """Send alert to Slack."""
        if not self.slack_webhook:
            self.logger.warning("Slack webhook not configured")
            return
        
        color = "#FF0000" if urgent else "#FFA500"
        emoji = "🚨" if urgent else "⚠️"
        
        payload = {
            "attachments": [{
                "color": color,
                "title": f"{emoji} {alert.title}",
                "text": alert.description,
                "fields": [
                    {
                        "title": "Severity",
                        "value": alert.severity.value.upper(),
                        "short": True
                    },
                    {
                        "title": "Type",
                        "value": alert.alert_type,
                        "short": True
                    }
                ],
                "footer": "Data Observability Platform",
                "ts": int(alert.triggered_at.timestamp())
            }]
        }
        
        response = requests.post(self.slack_webhook, json=payload, timeout=10)
        response.raise_for_status()
        
        self.logger.info(f"Alert {alert.id} sent to Slack")
    
    def _send_to_pagerduty(self, alert: Alert) -> None:
        """Send alert to PagerDuty."""
        if not self.pagerduty_key:
            self.logger.warning("PagerDuty integration key not configured")
            return
        
        payload = {
            "routing_key": self.pagerduty_key,
            "event_action": "trigger",
            "payload": {
                "summary": alert.title,
                "severity": "critical",
                "source": "data-observability-platform",
                "custom_details": {
                    "description": alert.description,
                    "alert_type": alert.alert_type,
                    "alert_id": alert.id
                }
            }
        }
        
        response = requests.post(
            "https://events.pagerduty.com/v2/enqueue",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        
        self.logger.info(f"Alert {alert.id} sent to PagerDuty")
    
    def _get_channel_name(self, severity: CriticalityLevel) -> str:
        """Get notification channel name for severity."""
        if severity == CriticalityLevel.P1:
            return "pagerduty,slack"
        elif severity == CriticalityLevel.P2:
            return "slack"
        else:
            return "dashboard"
    
    def acknowledge_alert(self, alert_id: int, acknowledged_by: str) -> None:
        """Acknowledge an alert."""
        with self.db_manager.session_scope() as session:
            alert = session.query(Alert).get(alert_id)
            if alert:
                alert.status = AlertStatus.ACKNOWLEDGED
                alert.acknowledged_at = datetime.utcnow()
                alert.acknowledged_by = acknowledged_by
                self.logger.info(f"Alert {alert_id} acknowledged by {acknowledged_by}")
    
    def resolve_alert(self, alert_id: int) -> None:
        """Resolve an alert."""
        with self.db_manager.session_scope() as session:
            alert = session.query(Alert).get(alert_id)
            if alert:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.utcnow()
                self.logger.info(f"Alert {alert_id} resolved")
