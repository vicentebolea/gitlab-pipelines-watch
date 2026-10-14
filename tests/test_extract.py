from pipelines_watch.extract import scrub


def test_scrub_removes_timestamps_and_secrets():
    raw = (
        "2026-10-13T13:26:47.791816Z 01E ERROR: upload failed token=abc_FAKE1 correlation_id=abc123 id=99 status=413   \n"
        "2026-10-13T13:26:47.792155Z 01E FATAL: too large glpat-xxxx"
    )
    assert scrub(raw) == (
        "ERROR: upload failed token=<redacted> correlation_id=<redacted> id=<redacted> status=413\n"
        "FATAL: too large <redacted>"
    )


def test_terminal_errors_picks_last_errors_before_job_failed():
    from pipelines_watch.extract import terminal_errors

    log = "fatal: bad config\nok\nERROR: upload 413\nFATAL: too large\nERROR: Job failed: exit status 128\n"
    assert terminal_errors(log, n=2) == "ERROR: upload 413\nFATAL: too large"


def test_entry_markdown_roundtrip():
    from pipelines_watch.entries import Entry

    e = Entry(project="g/p", job_id=1, pipeline_id=2, ref="main", job_name="build:linux", platform="linux-x86_64",
              error_type="network", snippet="ERROR: timeout\nFATAL: gave up", outcome="retry_passed")
    assert Entry.from_markdown(e.to_markdown()) == e
