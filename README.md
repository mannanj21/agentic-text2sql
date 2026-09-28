# Agentic Text-to-SQL Analytics Platform

An agentic platform that translates natural language questions into SQL queries, executes them safely against connected databases, and returns structured answers with visualizations.

## Status

🚧 **Under Development** — Stage 0: Environment & Repository Bootstrap

## Quick Start

```bash
# Clone and configure
cp .env.example .env
# Edit .env with your settings (see .env.example for docs)

# Start services
docker compose up -d --build --wait

# Verify
curl http://localhost:8000/health
```

## Development

```bash
# Check environment
python scripts/check_env.py

# Run tests
make check        # Quick: lint + format + types + unit tests
make test-all     # Full: Quick + agent + integration tests
make smoke        # Stack: Docker compose smoke test
```

## License

MIT — see [LICENSE](LICENSE).
