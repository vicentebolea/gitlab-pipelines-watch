# pipelines-watch

Watches failed GitLab CI jobs through Prometheus and retries the ones an LLM
judges transient, using a corpus of past failures as context. See
`ARCHITECTURE.md` for how it works.

This repo is the online half: the watcher, plus the library code shared with
[vtk-pipelines-knowledge](https://github.com/vicentebolea/vtk-pipelines-knowledge),
which builds the corpus (entries and Chroma database) and publishes it as a
data-only image that the watcher mounts:

```
vtk-pipelines-knowledge --builds--> ghcr.io/.../vtk-pipelines-knowledge --mounted by--> pipelines-watch
```

## Prerequisites

- Python 3.10 or newer, or podman.
- A GitLab token with the `api` scope and Developer access to the projects.
- A Prometheus that scrapes
  [gitlab-ci-pipelines-exporter](https://github.com/mvisonneau/gitlab-ci-pipelines-exporter)
  (the `rigel-deploy` repo installs it on `rigel`). GitLab's own `/-/metrics`
  has no per-job data. Enable job metrics and **merge request refs**, since the
  exporter follows only `main` and `master` by default:

  ```yaml
  project_defaults:
    pull:
      pipeline:
        jobs:
          enabled: true
      refs:
        merge_requests:
          enabled: true
          max_age_seconds: 21600
  ```

- An Anthropic API key.
- ollama with `nomic-embed-text` (`ollama pull nomic-embed-text`), the model the
  knowledge was built with.
- The knowledge: the `vtk-pipelines-knowledge` image, or a directory built by
  that repo.

## Configure

Environment variables (or a `.env` file in the working directory):

```sh
PW_GITLAB_URL=https://gitlab.kitware.com
PW_GITLAB_TOKEN=glpat-xxxx
PW_PROMETHEUS_URL=http://rigel:9090
PW_LLM_MODEL=anthropic:claude-sonnet-5-5       # classifies failures
PW_EXTRACT_MODEL=anthropic:claude-haiku-5-5    # extracts snippet and platform
ANTHROPIC_API_KEY=sk-ant-xxxx
PW_EMBEDDING_MODEL=ollama:nomic-embed-text     # must match the knowledge manifest
OLLAMA_HOST=http://localhost:11434
PW_KNOWLEDGE_DIR=knowledge                     # where the corpus is mounted
PW_STATE_DIR=data                              # the watcher's decision log
```

Tuning (defaults): `PW_CONCURRENCY` (8), `PW_GITLAB_RPS` (5, requests per
second to GitLab, lower it if the instance is busy), `PW_MAX_RETRIES_PER_JOB`
(2), `PW_MIN_CONFIDENCE` (0.6), `PW_POLL_INTERVAL` (60 s), `PW_METRICS_PORT`
(9101).

## Run

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
PW_DRY_RUN=true .venv/bin/pipelines-watch watch   # logs decisions, retries nothing
.venv/bin/pipelines-watch watch
```

Dry-run lines look like `group/project #123 build-linux -> RETRY (network timeout)`.
At startup the watcher checks `manifest.json` in the knowledge directory and
refuses to start if the corpus was built with another embedding model or
extraction version.

## Container

CI pushes `ghcr.io/vicentebolea/gitlab-pipelines-watch` (tags: sha, `latest`,
`v*`). It does not contain the corpus: mount the knowledge image at `/kb`, which
is `/kb/knowledge`, the default `PW_KNOWLEDGE_DIR`.

```sh
podman pull ghcr.io/vicentebolea/vtk-pipelines-knowledge   # an image mount is not pulled by run
podman run -d --env-file .env \
  --mount type=image,source=ghcr.io/vicentebolea/vtk-pipelines-knowledge,destination=/kb,rw=true \
  -v pw-state:/state -p 9101:9101 \
  ghcr.io/vicentebolea/gitlab-pipelines-watch
```

`rw=true` is needed because Chroma writes to its database file; the changes
are discarded with the container. Replace the last argument with `check` to
test that a knowledge image fits this version. CI does this on every push
(`knowledge-compat`), so a version bump turns it red until the knowledge is
rebuilt.

### As a service (podman Quadlet)

```sh
mkdir -p ~/.config/containers/systemd ~/.config/pipelines-watch
cp deploy/pipelines-watch.container deploy/knowledge.image ~/.config/containers/systemd/
cp deploy/pipelines-watch.env.example ~/.config/pipelines-watch/env   # then edit it
systemctl --user daemon-reload
systemctl --user start pipelines-watch
```

`knowledge.image` pulls the knowledge image first, and `AutoUpdate=registry`
lets `podman auto-update` pick up new app images. Start with `PW_DRY_RUN=true`.
To reach an ollama on the host use `OLLAMA_HOST=http://host.containers.internal:11434`
and let ollama listen on more than localhost (`OLLAMA_HOST=0.0.0.0`).

## Diagnose a log

Ask whether a retry of a job log is a good idea, without GitLab or Prometheus:

```sh
pipelines-watch diagnose job.log --job windows-vs2022-mpi-python-qt:build
some-command | pipelines-watch diagnose --job linux-gcc:build
pipelines-watch diagnose --text "fatal: index file corrupt"
```

It prints the extracted platform, error type and snippet, a verdict (`RETRY` or
`DO NOT RETRY`), the reason, and the similar past failures with their outcomes.
The LLM also sees each entry's success rate, which is not printed. The verdict
comes from an LLM and can vary between runs: read the listed failures,
especially when they disagree.

## Tests and checks

```sh
.venv/bin/pytest   # fast, fake embeddings, no services
```

Retrieval quality on the real corpus is tested in the knowledge repo. While
running: logs show one decision per failed job, `curl localhost:9101/metrics |
grep pw_decisions_total` counts `retry`, `skip` and `error`, and every decision
is in `data/state.db` (table `decisions`).

## As a library

`vtk-pipelines-knowledge` imports `pipelines_watch.entries`, `.extract`,
`.corpus`, `.manifest` and `.config`, so entries are written and read the way
the watcher expects. When the extraction prompt, scrubbing or entry format
changes, bump `EXTRACTION_VERSION` in `extract.py`, tag a release, and rebuild
the knowledge with it.
