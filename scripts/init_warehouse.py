#!/usr/bin/env python
"""
Initialize the observability warehouse.

Creates all tables and sets up the database schema.
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data_observability.models.database import DatabaseManager
from data_observability.models.results import Base
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Initialize warehouse database."""
    logger.info("Initializing observability warehouse...")
    
    try:
        # Create database manager
        db_manager = DatabaseManager()
        
        logger.info(f"Connecting to: {db_manager.connection_string}")
        
        # Create all tables
        db_manager.create_all_tables()
        
        logger.info("✅ Warehouse initialized successfully!")
        logger.info("Tables created:")
        logger.info("  - datasets")
        logger.info("  - tests")
        logger.info("  - validation_runs")
        logger.info("  - test_results")
        logger.info("  - alerts")
        logger.info("  - health_scores")
        
        return 0
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize warehouse: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
