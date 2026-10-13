from prometheus_api_client import PrometheusConnect

# gitlab-ci-pipelines-exporter: job_id's value is the GitLab job id; join it with the failed status.
FAILED_JOBS = (
    'gitlab_ci_pipeline_job_id * on(project, ref, stage, job_name) group_left() '
    '(gitlab_ci_pipeline_job_status{status="failed"} == 1)'
)


def failed_jobs(prometheus_url):
    """Return [(project_path, job_id, job_name, failure_reason)] currently failed per Prometheus."""
    prom = PrometheusConnect(url=prometheus_url)
    return [
        (m["metric"]["project"], int(float(m["value"][1])), m["metric"]["job_name"],
         m["metric"].get("failure_reason", ""))
        for m in prom.custom_query(FAILED_JOBS)
    ]
