"""Multi-URL result support: JobStatus.result_urls default + gateways._result_urls
collector + Kie/MuAPI populate all image URLs on a complete task."""
from __future__ import annotations

from core.ai_router.base import JobStatus
from core.ai_router.gateways import KieGateway, MuapiGateway, _result_urls


def test_jobstatus_result_urls_defaults_empty():
    js = JobStatus("complete", result_url="https://x/1.png")
    assert js.result_urls == []


def test_result_urls_known_key_wins_dedup_ordered():
    # A known result-key subtree wins; dedup + order preserved; the misc/thumb subtree
    # is ignored so a preview URL elsewhere can't intrude.
    obj = {"resultUrls": ["https://a/1.png", "https://a/2.png", "https://a/1.png"],
           "misc": {"thumb": "https://a/3.png"}}
    assert _result_urls(obj) == ["https://a/1.png", "https://a/2.png"]


def test_result_urls_walks_when_no_known_key():
    # No known result-key present → full walk collects every http URL.
    obj = {"gallery": ["https://a/1.png", "https://a/2.png"]}
    assert _result_urls(obj) == ["https://a/1.png", "https://a/2.png"]


def test_result_urls_empty_when_none():
    assert _result_urls({"state": "success", "n": 5}) == []


def test_kie_complete_populates_result_urls():
    data = {"state": "success",
            "resultJson": {"resultUrls": ["https://k/1.png", "https://k/2.png"]}}
    js = KieGateway._to_status(data)
    assert js.status == "complete"
    assert js.result_url == "https://k/1.png"
    assert js.result_urls == ["https://k/1.png", "https://k/2.png"]


def test_muapi_complete_populates_result_urls():
    data = {"status": "completed",
            "outputs": ["https://m/1.png", "https://m/2.png", "https://m/3.png"]}
    js = MuapiGateway._to_status(data)
    assert js.status == "complete"
    assert js.result_urls == ["https://m/1.png", "https://m/2.png", "https://m/3.png"]
