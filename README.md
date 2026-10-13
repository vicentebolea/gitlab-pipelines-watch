# pipelines-watch

Watches failed GitLab CI jobs through Prometheus and retries the ones an LLM
judges transient, using a corpus of past failures as context.
See `ARCHITECTURE.md` for how it works.

There are two separate steps:

1. Offline: build the corpus (a vector database of past failures).
2. Online: run the watcher, which reads that corpus and retries jobs.

## Prerequisites

- Python 3.10 or newer.
- A GitLab token with the `api` scope and Developer access to the projects.
- A Prometheus server that scrapes
  [gitlab-ci-pipelines-exporter](https://github.com/mvisonneau/gitlab-ci-pipelines-exporter).
  GitLab's own `/-/metrics` is not enough, it has no per-job data.
- An LLM and an embedding model reachable through an OpenAI-compatible API
  (or any other provider langchain supports).

### Exporter setup (once)

Run the exporter next to Prometheus (for example on `rigel`) with job metrics
enabled, and list the projects to watch:

```yaml
gitlab:
  url: https://gitlab.kitware.com
  token: <token>
project_defaults:
  pull:
    pipeline:
      jobs:
        enabled: true
projects:
  - name: group/project
```

Then add the exporter as a scrape target in Prometheus (in `rigel-deploy`, the
`prometheus_scrape_configs` in `site.yml`). The exporter listens on port 8080
by default. The watcher itself also exposes its own metrics on port 9100, which
you can add as a second target.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Configure

All settings are environment variables. Put them in a `.env` file in the
directory you run from, or in the service environment.

```sh
PW_GITLAB_URL=https://gitlab.kitware.com
PW_GITLAB_TOKEN=glpat-xxxx
PW_PROMETHEUS_URL=http://rigel:9090

# LLM and embeddings, written as provider:model
PW_LLM_MODEL=openai:gemini-2.0-flash
PW_EMBEDDING_MODEL=openai:text-embedding-3-small

# Used by the openai provider
OPENAI_API_KEY=xxxx
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai

# Where the corpus and decision log live (default: ./data)
PW_DATA_DIR=data
```

The embedding model must be one your endpoint actually serves. With the Gemini
endpoint above, use `PW_EMBEDDING_MODEL=openai:gemini-embedding-001` (tested).

Tuning knobs (defaults in parentheses): `PW_CONCURRENCY` (8),
`PW_GITLAB_RPS` (5, requests per second sent to GitLab),
`PW_MAX_RETRIES_PER_JOB` (2), `PW_MIN_CONFIDENCE` (0.6), `PW_POLL_INTERVAL`
(60 seconds). Lower `PW_GITLAB_RPS` if the instance is busy.

## Step 1: build the corpus (offline)

The corpus is a Chroma database in `PW_DATA_DIR/chroma`. It is built from
GitLab history, one project at a time:

```sh
.venv/bin/pipelines-watch backfill group/project --pipelines 200
```

What this does: it reads the last 200 pipelines of the project, including
retried attempts. For every `script_failure` job that was run again, it stores
the log tail with a label:

- `retry_passed`: the next attempt succeeded, so the failure was transient.
- `retry_failed`: the next attempt failed too, so it was a real bug.

Failures that were never retried are skipped.

Notes:

- Run it once per project. Repeat the command with a different project path to
  add more; re-running the same project is safe, entries are keyed by
  `project:job_id`.
- Check the result is big enough before going further. If few failures were
  ever retried at the job level, the corpus will be small.
- Run it with the watcher stopped, or build into a new directory
  (`PW_DATA_DIR=data-new`) and switch over afterwards.
- To start over, delete the corpus only: `rm -rf data/chroma`. Keep
  `data/state.db`, it holds the watcher's decision log and retry counts.
- Backfill talks to GitLab and the embedding API, so it can take a while on
  large projects.

## Step 2: run the watcher (online)

Try it first without retrying anything:

```sh
PW_DRY_RUN=true .venv/bin/pipelines-watch watch
```

It logs lines like `group/project #123 build-linux -> RETRY (network timeout)`.
When the decisions look right, run it for real:

```sh
.venv/bin/pipelines-watch watch
```

### Run it as a service (systemd)

`/etc/systemd/system/pipelines-watch.service`:

```ini
[Unit]
Description=pipelines-watch
After=network-online.target

[Service]
WorkingDirectory=/opt/pipelines-watch
EnvironmentFile=/opt/pipelines-watch/.env
ExecStart=/opt/pipelines-watch/.venv/bin/pipelines-watch watch
Restart=always
User=pipelines-watch

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl enable --now pipelines-watch
journalctl -u pipelines-watch -f
```

After building a new corpus, restart the service so it picks it up.

## Check it works

- Logs show one decision per failed job.
- `curl localhost:9100/metrics | grep pw_decisions_total` shows counts of
  `retry`, `skip` and `error` decisions.
- Every decision is in `data/state.db` (table `decisions`):
  `sqlite3 data/state.db 'select * from decisions order by rowid desc limit 10'`.
