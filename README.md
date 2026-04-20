# DeskPricer

Local HTTP pricing microservice for vanilla European and American equity options. Replaces legacy VBA Greeks UDFs in Excel trading workbooks.

## Design Principles

- **Fat caller, thin service** — all market data arrives in the HTTP request; no Bloomberg or database calls inside the service.
- **Pure functions** — same inputs, same outputs; no shared mutable state between requests.
- **XML by default** — Excel `WEBSERVICE` + `FILTERXML` work out of the box; JSON available via `Accept: application/json`.
- **Localhost-only** — binds to `127.0.0.1`; no network exposure.

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
uvicorn desk_pricer.main:app --host 127.0.0.1 --port 8765 --reload
```

Test with curl:

```powershell
curl "http://127.0.0.1:8765/v1/greeks?s=100&k=105&t=0.25&r=0.05&q=0.02&v=0.20&type=call&style=european"
```

## Running Tests

```powershell
pytest tests -v
```

## Windows Service (Production)

1. Install [NSSM](https://nssm.cc/).
2. Copy this repo to `C:\deskpricer` and install the Python package.
3. Run `scripts\install_service.bat` as Administrator.
4. Check `http://127.0.0.1:8765/v1/health` from Excel or browser.

Uninstall: `scripts\uninstall_service.bat` as Administrator.

## Concurrency Note

QuantLib uses process-global state (`Settings.instance().evaluationDate`). In v1.0, all pricing work is serialized through an `asyncio.Lock` and the service runs with `workers=1`. This guarantees correctness at the cost of throughput. For v1.1, a `ProcessPoolExecutor` is under consideration.

## Project Structure

```
desk-pricer/
├── pyproject.toml
├── README.md
├── requirements.txt
├── src/desk_pricer/          # FastAPI app + pricing core
├── tests/                    # pytest + hypothesis
├── scripts/                  # NSSM install/uninstall
└── docs/                     # API ref + Excel usage
```

## License

MIT
