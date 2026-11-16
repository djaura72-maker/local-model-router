# local-model-router

A zero-dependency, OpenAI-compatible `/v1` proxy in Python that routes requests across **LM Studio** and **Ollama** with task-aware model selection (`model="auto"`), automatic backend failover, and latency logging.

## Features

- **Unified `/v1` Endpoint:** Exposes `/v1/models`, `/v1/chat/completions`, and `/health` on `http://localhost:4000/v1`.
- **Smart Auto-Routing:** Automatically picks your coding, reasoning, or general model when `model` is set to `"auto"`.
- **Automatic Failover:** Falls back across configured local backends by priority if one server is offline.
- **Zero Dependencies:** Pure Python 3.10+ standard library.

## Quick Start

```bash
cp config.example.json config.json
python3 router.py --config config.json
```

Then point any OpenAI-compatible client (Hermes Agent, Continue, Cursor, or Python scripts) to `http://localhost:4000/v1`.

## License

MIT License — see [`LICENSE`](LICENSE).
