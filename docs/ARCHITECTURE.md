# Architecture

AI BI Workspace is a file-first data analysis application. It imports local data files,
normalizes them to Parquet, profiles data quality, generates dashboard specs, and
provides ChatBI-style follow-up analysis over the active dataset version.

## Runtime Shape

```text
Vue 3 dashboard
  -> FastAPI routes
  -> file import / profiling / cleaning / dashboard / ChatBI services
  -> local storage artifacts
  -> DuckDB over Parquet
  -> OpenAI-compatible LLM provider
```

The current implementation is intentionally local and lightweight. PostgreSQL,
Redis, vector search, and distributed workers are future integration points rather
than active runtime dependencies.

## Backend Layers

- `api`: HTTP routes and request/response contracts.
- `application`: thin use cases that coordinate infrastructure adapters.
- `domain`: small shared domain entities used by the application layer.
- `infrastructure`: local storage, profiling, cleaning, DuckDB querying, LLM calls,
  dashboard generation, reports, and job persistence.
- `tests`: focused unit tests for file import, profiling, cleaning, dashboard
  generation, ChatBI, LLM health, jobs, and DuckDB query safety.

## Storage Layout

```text
storage/raw/{dataset_id}/{version_id}/source.*
storage/warehouse/{dataset_id}/{version_id}/data.parquet
storage/warehouse/{dataset_id}/{version_id}/metadata.json
storage/warehouse/{dataset_id}/{version_id}/profile.json
storage/warehouse/{dataset_id}/{version_id}/analysis.json
storage/warehouse/{dataset_id}/{version_id}/dashboard.json
storage/jobs/{job_id}.json
```

Runtime artifacts are ignored by Git. The repository keeps only `.gitkeep` files
so the expected storage directories exist after cloning.

## Main Workflow

```text
upload CSV / Excel / JSON
 -> save raw file
 -> convert to Parquet
 -> profile schema and data quality
 -> generate analysis plan
 -> build ECharts-ready dashboard cards
 -> preview cleaning operations
 -> create cleaned dataset versions
 -> ask follow-up questions through SQLBot
```

## ChatBI Workflow

```text
question
 -> build dataset context from metadata, profile, analysis, and sample rows
 -> ask LLM to plan safe DuckDB SQL
 -> execute read-only query against Parquet
 -> summarize answer with query evidence
```

Suggested starter questions are generated per dataset by the configured LLM. If
the LLM call fails, the backend falls back to profile-derived questions based on
numeric, categorical, temporal, and quality-issue columns.
