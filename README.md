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

# LLMs, written as provider:model
PW_LLM_MODEL=anthropic:claude-sonnet-5-5       # classifies failures
PW_EXTRACT_MODEL=anthropic:claude-haiku-5-5    # extracts snippet and platform
ANTHROPIC_API_KEY=sk-ant-xxxx

# Embeddings run locally through ollama
PW_EMBEDDING_MODEL=ollama:nomic-embed-text

# Where entries, the Chroma corpus and the decision log live (default: ./data)
PW_DATA_DIR=data
```

Embeddings need a running ollama server with the model pulled
(`ollama serve`, `ollama pull nomic-embed-text`); it uses the GPU if there is
one. Any other langchain provider works too, for example
`PW_EMBEDDING_MODEL=openai:text-embedding-3-small` with `OPENAI_API_KEY`.

Tuning knobs (defaults in parentheses): `PW_CONCURRENCY` (8),
`PW_GITLAB_RPS` (5, requests per second sent to GitLab),
`PW_MAX_RETRIES_PER_JOB` (2), `PW_MIN_CONFIDENCE` (0.6), `PW_POLL_INTERVAL`
(60 seconds). Lower `PW_GITLAB_RPS` if the instance is busy.

## Step 1: build the corpus (offline, two stages)

Stage 1 turns GitLab history into entry files. Stage 2 embeds them into Chroma.
Keeping them apart lets you inspect and edit entries before they are indexed.

### Stage 1: write entries

```sh
.venv/bin/pipelines-watch backfill group/project --pipelines 200
```

It reads the last 200 pipelines of the project, including retried attempts. For
every `script_failure` job that was run again, the LLM extracts the error
snippet and the platform, and one markdown file is written to
`data/entries/group__project/<job_id>.md`:

```markdown
---
project: group/project
job_id: 13516705
platform: windows-vs2022
error_type: artifact-upload
outcome: retry_passed
---

# artifact-upload on windows-vs2022: retry_passed

Job `windows-vs2022-mpi-python-qt:build` (group/project). A retry of this job on this platform passed.

(error snippet in a code block)
```

`outcome` is what the next attempt of the same job did: `retry_passed` (the
failure was transient) or `retry_failed` (a real bug). Failures that were never
retried are skipped. Timestamps, tokens and ids are scrubbed from snippets.

Re-running is safe, existing entry files are skipped. Repeat with another
project path to add more.

### Review the entries

They are plain markdown. Read them, fix a wrong platform or outcome, or delete
bad ones.

### Stage 2: load into Chroma

```sh
.venv/bin/pipelines-watch load
```

Each entry becomes one Chroma record. Only the snippet is embedded, so
similarity depends on the error and not on the surrounding text. The whole
markdown file is stored with the record, and the classifier shows the matching
files to the LLM, which decides from those examples.

Notes:

- Entries already in Chroma are skipped. After editing a file that is already
  loaded, delete the corpus (`rm -rf data/chroma`) and run `load` again, it is
  cheap. Keep `data/state.db`, it holds the watcher's decision log.
- Check the number of entries before going further. If few failures were ever
  retried at the job level, the corpus will be small.
- Stage 1 calls GitLab and the Anthropic API, so it can take a while on large
  projects.
- Run `load` with the watcher stopped, or build into a new directory
  (`PW_DATA_DIR=data-new`) and switch over afterwards.

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
