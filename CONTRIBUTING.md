# Contributing to Production Data Observability Platform

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/production-data-observability.git
   cd production-data-observability
   ```
3. **Create a branch** for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

### Prerequisites
- Python 3.9+
- Docker & Docker Compose
- PostgreSQL 12+

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Start local services
docker-compose up -d

# Initialize warehouse
python scripts/init_warehouse.py
```

## Development Workflow

### Code Style

We use the following tools to maintain code quality:

- **Black** for code formatting
- **Flake8** for linting
- **MyPy** for type checking
- **isort** for import sorting

Before committing, run:

```bash
# Format code
black data_observability/ tests/

# Sort imports
isort data_observability/ tests/

# Check linting
flake8 data_observability/ tests/

# Type checking
mypy data_observability/
```

### Testing

All contributions should include appropriate tests.

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/unit/test_profiler.py -v

# Run with coverage
pytest tests/ -v --cov=data_observability --cov-report=html
```

### Commit Messages

Follow conventional commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `chore`: Maintenance tasks

**Example:**
```
feat(profiler): add support for JSON column validation

Implement custom expectations for JSON columns that validate
schema structure and required fields.

Closes #123
```

## Pull Request Process

1. **Update documentation** if you've changed APIs
2. **Add tests** for new functionality
3. **Ensure all tests pass** locally
4. **Update CHANGELOG.md** with your changes
5. **Submit PR** with clear description of changes

### PR Title Format

Use conventional commits format for PR titles:
```
feat(component): brief description of change
```

### PR Description Template

```markdown
## Description
Brief description of what this PR does.

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe the tests you ran and how to reproduce.

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] All tests passing
```

## Areas for Contribution

### High Priority
- Additional database connectors (Redshift, MySQL, Oracle)
- Advanced anomaly detection algorithms
- Dashboard templates for Metabase
- Performance optimizations
- Documentation improvements

### Good First Issues
- Adding more example dataset configurations
- Improving error messages
- Writing additional unit tests
- Documentation examples

### Advanced Features
- Machine learning-based drift detection
- Custom expectation library
- Real-time streaming validation support
- Integration with dbt

## Code Review

All submissions require review. We use GitHub pull requests for this purpose. Reviewers will check:

- **Functionality**: Does it work as intended?
- **Tests**: Are there adequate tests?
- **Documentation**: Is it documented?
- **Code Quality**: Follows style guidelines?
- **Performance**: Any performance implications?

## Communication

- **Issues**: Use GitHub Issues for bug reports and feature requests
- **Discussions**: Use GitHub Discussions for questions and ideas
- **Security**: Email security concerns to security@example.com

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

## Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes
- Project documentation

Thank you for contributing! 🎉
