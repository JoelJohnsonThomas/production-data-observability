"""
Master DAG for data quality validation orchestration.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

# Import custom operators (will be defined in plugins)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from data_observability.core.config_parser import ConfigParser
from data_observability.core.profiler import DataProfiler
from data_observability.core.execution_router import ExecutionRouter
from data_observability.core.engines.gx_engine import GXEngine
from data_observability.core.engines.sql_engine import SQLEngine
from data_observability.core.engines.direct_check_engine import DirectCheckEngine
from data_observability.alerts.alert_manager import AlertManager
from data_observability.models.database import DatabaseManager
from data_observability.models.results import Dataset, ValidationRun, TestResult, TestStatus
from data_observability.visualization.health_score import HealthScoreCalculator


# Default arguments for the DAG
default_args = {
    'owner': 'data-platform',
    'depends_on_past': False,
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}


def validate_dataset(dataset_config_path: str, **context):
    """
    Main validation task for a dataset.
    
    Args:
        dataset_config_path: Path to dataset YAML configuration
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Validating dataset from config: {dataset_config_path}")
    
    # Load configuration
    config = ConfigParser.load_from_file(dataset_config_path)
    dataset_name = config.name
    
    logger.info(f"Dataset: {dataset_name}, Criticality: {config.criticality}")
    
    # Initialize components
    db_manager = DatabaseManager()
    profiler = DataProfiler()
    router = ExecutionRouter()
    gx_engine = GXEngine()
    sql_engine = SQLEngine()
    direct_engine = DirectCheckEngine()
    alert_manager = AlertManager(db_manager)
    
    # Get or create dataset in warehouse
    with db_manager.session_scope() as session:
        dataset = session.query(Dataset).filter_by(name=dataset_name).first()
        if not dataset:
            dataset = Dataset(
                name=dataset_name,
                description=config.description,
                criticality=config.criticality,
                source_type=config.source.type,
                source_table=config.source.table
            )
            session.add(dataset)
            session.flush()
        dataset_id = dataset.id
    
    # Get connection string (from Airflow connection or env)
    connection_string = os.getenv(f"{config.source.connection.upper()}_CONNECTION_STRING")
    if not connection_string:
        raise ValueError(f"Connection string not found for: {config.source.connection}")
    
    # Profile dataset and generate expectations
    logger.info("Profiling dataset and generating expectations...")
    expectations = profiler.profile_dataset(config, connection_string)
    
    # Create execution plan
    logger.info("Creating execution plan...")
    plan = router.route(
        expectations=expectations,
        dataset_name=dataset_name,
        dataset_size_gb=0.0,  # TODO: Calculate actual size
        freshness_config=config.freshness.dict() if config.freshness else None,
        volume_config=config.volume.dict() if config.volume else None
    )
    
    # Create validation run record
    with db_manager.session_scope() as session:
        validation_run = ValidationRun(
            dataset_id=dataset_id,
            execution_backend="hybrid",
            total_tests=len(plan.gx_expectations) + len(plan.sql_checks) + len(plan.direct_checks)
        )
        session.add(validation_run)
        session.flush()
        validation_run_id = validation_run.id
    
    # Execute validations
    all_results = []
    
    # Execute GX expectations
    if plan.gx_expectations:
        logger.info(f"Executing {len(plan.gx_expectations)} GX expectations...")
        gx_results = gx_engine.execute(
            expectations=plan.gx_expectations,
            connection_string=connection_string,
            table_name=config.source.table,
            dataset_name=dataset_name
        )
        all_results.append(gx_results)
    
    # Execute SQL checks
    if plan.sql_checks:
        logger.info(f"Executing {len(plan.sql_checks)} SQL checks...")
        sql_results = sql_engine.execute(
            checks=plan.sql_checks,
            connection_string=connection_string,
            dataset_name=config.source.table or dataset_name
        )
        all_results.append(sql_results)
    
    # Execute direct checks
    if plan.direct_checks:
        logger.info(f"Executing {len(plan.direct_checks)} direct checks...")
        direct_results = direct_engine.execute(
            checks=plan.direct_checks,
            connection_string=connection_string,
            table_name=config.source.table,
            dataset_name=dataset_name
        )
        all_results.append(direct_results)
    
    # Aggregate results
    total_passed = sum(r.get('passed_tests', 0) for r in all_results)
    total_failed = sum(r.get('failed_tests', 0) for r in all_results)
    overall_success = all(r.get('success', False) for r in all_results)
    
    # Update validation run
    with db_manager.session_scope() as session:
        run = session.query(ValidationRun).get(validation_run_id)
        run.passed_tests = total_passed
        run.failed_tests = total_failed
        run.success = overall_success
        run.execution_time_seconds = plan.estimated_runtime_seconds
    
    # Process alerts
    logger.info("Processing alerts...")
    alerts = alert_manager.process_validation_results(
        dataset_name=dataset_name,
        validation_results={
            "success": overall_success,
            "total_tests": total_passed + total_failed,
            "passed_tests": total_passed,
            "failed_tests": total_failed
        },
        validation_run_id=validation_run_id
    )
    
    logger.info(f"Validation complete. Passed: {total_passed}, Failed: {total_failed}, Alerts: {len(alerts)}")
    
    return {
        "dataset": dataset_name,
        "success": overall_success,
        "passed": total_passed,
        "failed": total_failed,
        "alerts": len(alerts)
    }


def calculate_health_scores(**context):
    """Calculate health scores for all datasets."""
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("Calculating health scores for all datasets...")
    
    calculator = HealthScoreCalculator()
    scores = calculator.get_all_dataset_scores()
    
    logger.info(f"Calculated {len(scores)} health scores")
    
    for score in scores[:5]:  # Log top 5
        logger.info(f"  {score['dataset_name']}: {score['score']}")
    
    return scores


# Create the DAG
with DAG(
    'data_quality_master',
    default_args=default_args,
    description='Master DAG for data quality validation',
    schedule_interval='0 */6 * * *',  # Every 6 hours
    start_date=days_ago(1),
    catchup=False,
    tags=['data-quality', 'observability'],
) as dag:
    
    # Example: Validate financial transactions dataset
    validate_transactions = PythonOperator(
        task_id='validate_financial_transactions',
        python_callable=validate_dataset,
        op_kwargs={
            'dataset_config_path': '/opt/airflow/configs/datasets/financial_transactions.yml'
        },
    )
    
    # Example: Validate user events dataset
    validate_user_events = PythonOperator(
        task_id='validate_user_events',
        python_callable=validate_dataset,
        op_kwargs={
            'dataset_config_path': '/opt/airflow/configs/datasets/user_events.yml'
        },
    )
    
    # Calculate health scores after validations
    calculate_scores = PythonOperator(
        task_id='calculate_health_scores',
        python_callable=calculate_health_scores,
    )
    
    # Define dependencies
    [validate_transactions, validate_user_events] >> calculate_scores
