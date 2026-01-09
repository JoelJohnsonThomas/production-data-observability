"""
Database connection and session management.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

# Base class for ORM models
Base = declarative_base()

# Database connection configuration
WAREHOUSE_CONNECTION_STRING = os.getenv(
    "WAREHOUSE_CONNECTION_STRING",
    "postgresql://observability:observability_password@localhost:5432/observability"
)


class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self, connection_string: str = None):
        """
        Initialize database manager.
        
        Args:
            connection_string: SQLAlchemy connection string
        """
        self.connection_string = connection_string or WAREHOUSE_CONNECTION_STRING
        self.engine = create_engine(
            self.connection_string,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        self.session_factory = sessionmaker(bind=self.engine)
        self.Session = scoped_session(self.session_factory)
        
    def create_all_tables(self):
        """Create all tables defined in ORM models."""
        Base.metadata.create_all(self.engine)
        logger.info("All tables created successfully")
    
    def drop_all_tables(self):
        """Drop all tables (use with caution!)."""
        Base.metadata.drop_all(self.engine)
        logger.warning("All tables dropped")
    
    @contextmanager
    def session_scope(self):
        """
        Provide a transactional scope for database operations.
        
        Usage:
            with db_manager.session_scope() as session:
                session.add(obj)
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def get_session(self):
        """Get a new session."""
        return self.Session()


# Global database manager instance
db_manager = DatabaseManager()
