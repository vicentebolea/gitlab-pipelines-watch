from pipelines_watch.entries import Entry

E = dict(project="g/p", job_id=1, pipeline_id=2, ref="r", job_name="j", platform="linux",
         error_type="git", snippet="fatal: index file corrupt", outcome="retry_passed")


def test_rate_roundtrip_and_text():
    e = Entry(**E, similar=4, success_rate=0.75)
    md = e.to_markdown()
    assert "Across 4 retries of this error, 75% passed." in md
    assert Entry.from_markdown(md) == e


def test_entry_without_rate_is_unchanged():
    md = Entry(**E).to_markdown()
    assert "similar" not in md and "Across" not in md
    assert Entry.from_markdown(md).success_rate is None
