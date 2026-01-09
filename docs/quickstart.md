# Quick Start Guide

Get started with the Production Data Observability Platform in 15 minutes.

## Prerequisites

- Docker Desktop installed and running
- Python 3.9+ installed
- At least 8GB RAM available

## Step 1: Clone and Setup (2 minutes)

```bash
# Clone the repository
git clone https://github.com/yourusername/production-data-observability.git
cd production-data-observability

# Copy environment template
cp .env.example .env
```

## Step 2: Configure Environment (3 minutes)

Edit `.env` and set your database connection:

```bash
# Minimum required configuration
PROD_POSTGRES_HOST=your-database-host
PROD_POSTGRES_PORT=5432
PROD_POSTGRES_DB=your_database
PROD_POSTGRES_USER=readonly_user
PROD_POSTGRES_PASSWORD=your_password
```

## Step 3: Start the Platform (5 minutes)

```bash
# Start all services (Airflow, PostgreSQL, Metabase)
docker-compose up -d

# Wait for services to be healthy (check with)
docker-compose ps

# Initialize the observability warehouse
docker-compose exec airflow-webserver python /opt/airflow/scripts/init_warehouse.py
```

## Step 4: Access the UI (1 minute)

Open your browser:

- **Airflow**: http://localhost:8080 (admin/admin)
- **Metabase**: http://localhost:3000

## Step 5: Onboard Your First Dataset (4 minutes)

Create a dataset configuration file:

```bash
# Create configs directory if not exists
mkdir -p configs/datasets

# Create your dataset config
cat > configs/datasets/my_dataset.yml << 'EOF'
dataset:
  name: my_first_dataset
  description: "My first monitored dataset"
  criticality: p2
  
  source:
    type: postgresql
    connection: prod_warehouse
    table: your_table_name
  
  freshness:
    warning_threshold: 2h
    failure_threshold: 6h
    timestamp_column: updated_at
  
  volume:
    expected_min_rows_per_run: 1000
  
  columns:
    - name: id
      tests: [unique, not_null]
    
    - name: email
      tests: [not_null]
      regex_pattern: '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
EOF
```

## Step 6: Run Your First Validation

### Option A: Via Airflow UI

1. Go to http://localhost:8080
2. Find the `data_quality_master` DAG
3. Click "Trigger DAG"
4. Watch the execution in the Graph view

### Option B: Via Python Script

```python
# test_validation.py
from data_observability.core.config_parser import ConfigParser
from data_observability.core.profiler import DataProfiler

# Load your config
config = ConfigParser.load_from_file('configs/datasets/my_dataset.yml')

# Profile and generate expectations
profiler = DataProfiler()
expectations = profiler.profile_dataset(
    config,
    connection_string="postgresql://user:pass@host/db"
)

print(f"Generated {len(expectations)} expectations")
for exp in expectations[:5]:
    print(f"  - {exp.expectation_type}")
```

Run it:
```bash
python test_validation.py
```

## Step 7: View Results

### In Airflow
1. Click on your DAG run
2. Click on a task
3. View logs to see validation results

### In the Database
```sql
-- Connect to observability warehouse
-- PostgreSQL: localhost:5432, database: observability

-- View recent runs
SELECT 
    d.name as dataset,
    vr.run_timestamp,
    vr.success,
    vr.passed_tests,
    vr.failed_tests
FROM validation_runs vr
JOIN datasets d ON vr.dataset_id = d.id
ORDER BY vr.run_timestamp DESC
LIMIT 10;

-- View health scores
SELECT 
    d.name,
    hs.score,
    hs.trend_direction,
    hs.computed_at
FROM health_scores hs
JOIN datasets d ON hs.dataset_id = d.id
ORDER BY hs.computed_at DESC;
```

## Common First-Time Issues

### Issue: Services won't start
```bash
# Check Docker resources
docker system df

# Increase Docker memory to 8GB in Docker Desktop settings

# Restart services
docker-compose down
docker-compose up -d
```

### Issue: Can't connect to data source
```bash
# Test connection manually
docker-compose exec airflow-webserver bash -c "
python -c '
import psycopg2
conn = psycopg2.connect(
    host=\"YOUR_HOST\",
    port=5432,
    database=\"YOUR_DB\",
    user=\"YOUR_USER\",
    password=\"YOUR_PASSWORD\"
)
print(\"Connection successful!\")
conn.close()
'
"
```

### Issue: Airflow UI shows "OperationalError"
```bash
# Reset Airflow database
docker-compose down -v
docker-compose up -d
```

## Next Steps

1. **Add More Datasets**: Create configs for all critical tables
2. **Configure Alerts**: Edit `configs/alerts/routing_rules.yml`
3. **Customize Dashboards**: Import Metabase dashboard templates
4. **Schedule Regular Runs**: Adjust DAG schedule in `airflow/dags/data_quality_master.py`
5. **Review Documentation**: See `docs/architecture.md` for deep dive

## Getting Help

- **Documentation**: See `docs/` directory
- **Examples**: Check `configs/datasets/` for example configurations
- **Issues**: GitHub Issues for bug reports
- **Community**: GitHub Discussions for questions

## Health Check Checklist

After setup, verify:

- [ ] Airflow UI accessible at localhost:8080
- [ ] Metabase UI accessible at localhost:3000
- [ ] PostgreSQL warehouse created (`docker-compose exec postgres psql -U airflow -l`)
- [ ] At least one dataset configured
- [ ] At least one successful validation run
- [ ] Results visible in warehouse database
- [ ] Logs show no errors

Congratulations! Your data observability platform is running! 🎉
