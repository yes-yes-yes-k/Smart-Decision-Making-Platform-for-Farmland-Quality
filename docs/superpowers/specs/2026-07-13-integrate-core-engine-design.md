---
archived-with: 2026-07-13-integrate-core-engine
status: final
status: final
---
# Integrate Core Engine Design Doc

## Overview

This document describes the integration of `src/ai_culti_demo` as the underlying core engine for the unified framework.

## Architecture

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              New Framework (framework/)                      │
├─────────────────────────────────────────────────────────────┤
│  API Layer (Flask)                                          │
│  Multi-Agent Orchestration (LangGraph)                      │
│  RAG (Chroma + bge-m3)                                      │
│  Function Calling                                           │
│  Authentication (JWT)                                       │
│  Database (SQLAlchemy)                                      │
├─────────────────────────────────────────────────────────────┤
│  Core Engine Adapter (framework/core_engine/)               │
│    ├── adapter.py — CoreEngine class with unified interface │
│    └── __init__.py — exports                                │
├─────────────────────────────────────────────────────────────┤
│              Core Engine (src/ai_culti_demo/)                │
├─────────────────────────────────────────────────────────────┤
│  Catalog — Data asset management                            │
│  Overview — County overview and layers                       │
│  Diagnosis — Acidification, quality, improvement            │
│  Thematic Models — 6 specialized models                     │
│  Report — Report generation                                 │
└─────────────────────────────────────────────────────────────┘
```

## Integration Points

### 1. Core Engine Adapter

**File**: `framework/core_engine/adapter.py`

**Interface**:
```python
class CoreEngine:
    def get_county_overview(area_code: str) -> dict
    def diagnose_county(payload: dict) -> dict
    def list_thematic_models(area_code: str) -> dict
    def run_thematic_model(payload: dict) -> dict
    def build_report_summary(diagnosis: dict) -> dict
    def load_catalog(path: Optional[str]) -> dict
    def verify_runtime() -> dict
```

### 2. County API Routes

**File**: `framework/api/routes/county.py`

- `GET /api/v1/county/overview` → `core_engine.get_county_overview()`
- `POST /api/v1/county/diagnose` → `core_engine.diagnose_county()`

### 3. Models API Routes

**File**: `framework/api/routes/models.py`

- `GET /api/v1/models/` → `core_engine.list_thematic_models()`

### 4. Multi-Agent Nodes

**File**: `framework/agents/nodes.py`

- `execute_models()` → `core_engine.run_thematic_model()`
- Model mapping:
  - question_type=1 → acidification-governance
  - question_type=2 → multi-factor-collaborative-improvement
  - question_type=3 → organic-matter-improvement

## Error Handling

- All adapter methods include exception catching
- Graceful fallback to old implementation when core engine fails
- Error responses include code and message

## Testing

Integration test validates:
- Core engine initialization
- County overview retrieval
- Thematic models listing
- Thematic model execution
- County diagnosis
- API route imports
- Multi-agent node imports
