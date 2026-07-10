from scripts.run_load_test import Sample, percentile, summarize


def test_percentile_interpolates_ordered_values():
    values = [10.0, 20.0, 30.0, 40.0]

    assert percentile(values, 0.50) == 25.0
    assert percentile(values, 0.95) == 38.5


def test_summarize_reports_errors_throughput_and_operation_breakdown():
    samples = [
        Sample("GET /events page 1", 200, 10.0, True),
        Sample("GET /events page 1", 200, 20.0, True),
        Sample("GET /metrics", 500, 30.0, False, "server error"),
    ]

    report = summarize(samples, elapsed_seconds=1.5)

    assert report["requests"] == 3
    assert report["successful"] == 2
    assert report["failed"] == 1
    assert report["error_rate_percent"] == 33.3333
    assert report["requests_per_second"] == 2.0
    assert report["status_codes"] == {200: 2, 500: 1}
    assert report["operations"]["GET /events page 1"]["requests"] == 2
    assert report["operations"]["GET /metrics"]["failed"] == 1
