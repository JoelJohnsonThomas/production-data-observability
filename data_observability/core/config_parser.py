"""Configuration parser for dataset definitions using Pydantic models."""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, validator
import yaml
from pathlib import Path


class SourceConfig(BaseModel):
    """Data source configuration."""
    type: Literal["postgresql", "mysql", "bigquery", "snowflake", "csv", "parquet"]
    connection: str  # Connection name from Airflow or env vars
    table: Optional[str] = None
    query: Optional[str] = None
    file_path: Optional[str] = None
    
    @validator('table', 'query', always=True)
    def check_table_or_query(cls, v, values):
        """Ensure either table or query is specified for databases."""
        if values.get('type') not in ['csv', 'parquet']:
            if not v and not values.get('query'):
                raise ValueError("Either 'table' or 'query' must be specified")
        return v


class FreshnessConfig(BaseModel):
    """Freshness monitoring configuration."""
    warning_threshold: str = Field(..., description="e.g., '1h', '30m', '2d'")
    failure_threshold: str = Field(..., description="e.g., '4h', '1d'")
    timestamp_column: str = "updated_at"


class VolumeConfig(BaseModel):
    """Volume monitoring configuration."""
    expected_min_rows_per_run: Optional[int] = None
    expected_max_rows_per_run: Optional[int] = None
    anomaly_detection: bool = False
    anomaly_threshold_std: float = 3.0


class ColumnConfig(BaseModel):
    """Column-level validation configuration."""
    name: str
    tests: List[str] = Field(default_factory=list)
    valid_range: Optional[List[float]] = None
    valid_values: Optional[List[Any]] = None
    references: Optional[str] = None  # For referential integrity: "table.column"
    regex_pattern: Optional[str] = None
    custom_expectation: Optional[str] = None


class DatasetConfig(BaseModel):
    """Complete dataset configuration."""
    name: str
    criticality: Literal["p1", "p2", "p3"] = "p2"
    description: Optional[str] = None
    source: SourceConfig
    freshness: Optional[FreshnessConfig] = None
    volume: Optional[VolumeConfig] = None
    columns: List[ColumnConfig] = Field(default_factory=list)
    custom_tests: List[str] = Field(default_factory=list)
    scheduling: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        extra = "forbid"  # Raise error on unknown fields


class ConfigParser:
    """Parser for YAML-based dataset configurations."""
    
    @staticmethod
    def load_from_file(config_path: str) -> DatasetConfig:
        """
        Load and validate dataset configuration from YAML file.
        
        Args:
            config_path: Path to YAML configuration file
            
        Returns:
            Validated DatasetConfig object
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValidationError: If config doesn't match schema
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(path, 'r') as f:
            raw_config = yaml.safe_load(f)
        
        # Handle nested 'dataset' key if present
        if 'dataset' in raw_config:
            raw_config = raw_config['dataset']
        
        return DatasetConfig(**raw_config)
    
    @staticmethod
    def load_from_dict(config_dict: Dict[str, Any]) -> DatasetConfig:
        """
        Load and validate dataset configuration from dictionary.
        
        Args:
            config_dict: Configuration as dictionary
            
        Returns:
            Validated DatasetConfig object
        """
        if 'dataset' in config_dict:
            config_dict = config_dict['dataset']
        
        return DatasetConfig(**config_dict)
    
    @staticmethod
    def to_yaml(config: DatasetConfig, output_path: str) -> None:
        """
        Export configuration to YAML file.
        
        Args:
            config: DatasetConfig object
            output_path: Path to write YAML file
        """
        with open(output_path, 'w') as f:
            yaml.dump(
                {'dataset': config.dict()},
                f,
                default_flow_style=False,
                sort_keys=False
            )


def parse_time_threshold(threshold: str) -> int:
    """
    Convert time threshold string to seconds.
    
    Args:
        threshold: Time string like '1h', '30m', '2d'
        
    Returns:
        Number of seconds
    """
    units = {
        's': 1,
        'm': 60,
        'h': 3600,
        'd': 86400
    }
    
    value = int(threshold[:-1])
    unit = threshold[-1]
    
    if unit not in units:
        raise ValueError(f"Invalid time unit: {unit}. Use s, m, h, or d")
    
    return value * units[unit]
