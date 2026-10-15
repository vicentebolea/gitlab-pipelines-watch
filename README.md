# pipelines-watch

Watches failed GitLab CI jobs through Prometheus and retries the ones an LLM
judges transient, using a corpus of past failures as context.
See `ARCHITECTURE.md` for how it works.

This repo is the online half: the watcher, plus the library code shared with
[vtk-pipelines-knowledge](https://github.com/vicentebolea/vtk-pipelines-knowledge),
which builds the corpus (entries and Chroma database) and publishes it as a
data-only image. The two meet in one artifact:

```
vtk-pipelines-knowledge  --builds-->  ghcr.io/.../vtk-pipelines-knowledge  --mounted by-->  pipelines-watch
```

## Prerequisites

- Python 3.10 or newer, or podman.
- A GitLab token with the `api` scope and Developer access to the projects.
- A Prometheus server that scrapes
  [gitlab-ci-pipelines-exporter](https://github.com/mvisonneau/gitlab-ci-pipelines-exporter).
  GitLab's own `/-/metrics` is not enough, it has no per-job data. The
  `rigel-deploy` repo installs the exporter on `rigel`. If you run it yourself,
  enable job metrics and **merge request refs** (it only follows `main` and
  `master` by default, but most retryable failures happen on merge requests):

  ```yaml
  gitlab:
    url: https://gitlab.kitware.com
    token: <token>
  project_defaults:
    pull:
      pipeline:
        jobs:
          enabled: true
      refs:
        merge_requests:
          enabled: true
          max_age_seconds: 21600
  projects:
    - name: group/project
  ```

- An Anthropic API key (classification and snippet extraction).
- An embedding server: ollama with `nomic-embed-text` pulled
  (`ollama pull nomic-embed-text`). The model must be the one the knowledge
  image was built with.
- The knowledge: the `vtk-pipelines-knowledge` image (or a local directory built
  by that repo).

## Configure

All settings are environment variables. Put them in a `.env` file in the
directory you run from, or in the service environment.

```sh
PW_GITLAB_URL=https://gitlab.kitware.com
PW_GITLAB_TOKEN=glpat-xxxx
PW_PROMETHEUS_URL=http://rigel:9090

PW_LLM_MODEL=anthropic:claude-sonnet-5-5       # classifies failures
PW_EXTRACT_MODEL=anthropic:claude-haiku-5-5    # extracts snippet and platform
ANTHROPIC_API_KEY=sk-ant-xxxx

PW_EMBEDDING_MODEL=ollama:nomic-embed-text     # must match the knowledge manifest
OLLAMA_HOST=http://localhost:11434

PW_KNOWLEDGE_DIR=knowledge   # where the corpus is mounted
PW_STATE_DIR=data            # the watcher's decision log
```

Tuning knobs (defaults in parentheses): `PW_CONCURRENCY` (8),
`PW_GITLAB_RPS` (5, requests per second sent to GitLab),
`PW_MAX_RETRIES_PER_JOB` (2), `PW_MIN_CONFIDENCE` (0.6), `PW_POLL_INTERVAL`
(60 seconds), `PW_METRICS_PORT` (9101). Lower `PW_GITLAB_RPS` if the instance
is busy.

## Install and run

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
```

Try it first without retrying anything:

```sh
PW_DRY_RUN=true .venv/bin/pipelines-watch watch
```

It logs lines like `group/project #123 build-linux -> RETRY (network timeout)`.
When the decisions look right, run it for real with
`.venv/bin/pipelines-watch watch`.

At startup the watcher reads `manifest.json` from the knowledge directory and
refuses to start if the corpus was built with a different embedding model or
extraction version than the ones it runs with. This protects against silently
degraded retrieval.

## Container image

CI builds the app image with podman and pushes it to
`ghcr.io/vicentebolea/gitlab-pipelines-watch` (tags: commit sha, `latest`, and
`v*` for version tags). The image does not contain the corpus: it expects the
knowledge image from `vtk-pipelines-knowledge` mounted at `/kb`.

```sh
podman run -d --env-file .env \
  --mount type=image,source=ghcr.io/vicentebolea/vtk-pipelines-knowledge,destination=/kb,rw=true \
  -v pw-state:/state -p 9101:9101 \
  ghcr.io/vicentebolea/gitlab-pipelines-watch
```

An image mount shows the image root at `/kb`, so the corpus is
`/kb/knowledge`, which is the image's default `PW_KNOWLEDGE_DIR`. `rw=true` is
needed because Chroma writes to its database file, the changes are discarded
with the container. A `scratch` data image cannot be used with
`--volumes-from`, the volume stays empty.

Check that a knowledge image fits this version before deploying (pull it first,
`podman run` does not pull the source of an image mount):

```sh
podman pull ghcr.io/vicentebolea/vtk-pipelines-knowledge
podman run --rm --mount type=image,source=ghcr.io/vicentebolea/vtk-pipelines-knowledge,destination=/kb,rw=true \
  ghcr.io/vicentebolea/gitlab-pipelines-watch check
```

CI runs the same check after every push to `main` against the latest published
knowledge image, so a version bump that makes the corpus stale turns the
`knowledge-compat` job red until the knowledge is rebuilt.

### Run it as a service (podman Quadlet)

`deploy/pipelines-watch.container` runs the app under systemd with the
knowledge image mounted, and `deploy/knowledge.image` pulls that image first
(`podman run` does not pull the source of an image mount). `AutoUpdate=registry`
lets `podman auto-update` pick up a new app image.

```sh
mkdir -p ~/.config/containers/systemd ~/.config/pipelines-watch
cp deploy/pipelines-watch.container deploy/knowledge.image ~/.config/containers/systemd/
cp deploy/pipelines-watch.env.example ~/.config/pipelines-watch/env   # then edit it
systemctl --user daemon-reload
systemctl --user start pipelines-watch
journalctl --user -u pipelines-watch -f
```

Start with `PW_DRY_RUN=true` in the env file. The container reaches an ollama
on the host through `OLLAMA_HOST=http://host.containers.internal:11434`, which
needs ollama to listen on more than localhost (`OLLAMA_HOST=0.0.0.0`).

## Diagnose a log

Ask whether a retry is a good idea for a job log, without GitLab or
Prometheus. It needs the knowledge, the embedding server and the Anthropic key:

```sh
pipelines-watch diagnose job.log --job windows-vs2022-mpi-python-qt:build
some-command | pipelines-watch diagnose --job linux-gcc:build        # stdin
pipelines-watch diagnose --text "fatal: index file corrupt"
```

It prints the extracted platform, error type and snippet, a verdict (`RETRY` or
`DO NOT RETRY`, using the same confidence threshold as the watcher), the
reason, and the similar past failures it based the verdict on. The verdict
comes from an LLM and can vary between runs: read the listed past failures,
especially when they disagree.

## Tests

```sh
.venv/bin/pytest
```

Fast tests with fake embeddings, no services needed. Retrieval quality on the
real corpus is tested in the knowledge repo, where the corpus is built.

## Check it works

- Logs show one decision per failed job.
- `curl localhost:9101/metrics | grep pw_decisions_total` shows counts of
  `retry`, `skip` and `error` decisions.
- Every decision is in `data/state.db` (table `decisions`):
  `sqlite3 data/state.db 'select * from decisions order by rowid desc limit 10'`.

## As a library

`vtk-pipelines-knowledge` imports `pipelines_watch.entries`, `.extract`,
`.corpus`, `.manifest` and `.config`, so that entries are written and indexed
exactly the way the watcher reads them. Changing the extraction prompt, the
scrubbing or the entry format means bumping `EXTRACTION_VERSION` in
`extract.py`, tagging a release, and rebuilding the knowledge with it.
