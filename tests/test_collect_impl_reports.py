import types

import pytest

import collect_impl_reports as cir


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_find_impl_report_prefers_latest_correction(monkeypatch):
    """[기재정정]이 있으면 접수번호가 큰 최신본을 쓴다."""
    payload = {"status": "000", "list": [
        {"report_nm": "증권발행실적보고서", "rcept_no": "20241031000328"},
        {"report_nm": "[기재정정]증권발행실적보고서", "rcept_no": "20241031000452"},
        {"report_nm": "투자설명서", "rcept_no": "20241025000263"},
    ]}
    monkeypatch.setattr(cir, "_fetch_with_retry",
                        lambda *a, **k: _FakeResp(payload))
    r = cir.find_impl_report("01573336", "2024-11-07")
    assert r["rcept_no"] == "20241031000452"


def test_find_impl_report_returns_none_when_absent(monkeypatch):
    """공모 없는 상장(이전상장 등)은 실적보고서가 없다 → None (결측 아님)."""
    payload = {"status": "000", "list": [
        {"report_nm": "투자설명서", "rcept_no": "20241025000263"}]}
    monkeypatch.setattr(cir, "_fetch_with_retry",
                        lambda *a, **k: _FakeResp(payload))
    assert cir.find_impl_report("01573336", "2024-11-07") is None


def test_find_impl_report_raises_on_quota(monkeypatch):
    """DART 한도 초과는 조용히 넘기면 안 된다."""
    monkeypatch.setattr(cir, "_fetch_with_retry",
                        lambda *a, **k: _FakeResp({"status": "020", "message": "한도초과"}))
    with pytest.raises(RuntimeError, match="한도"):
        cir.find_impl_report("01573336", "2024-11-07")


def test_search_window_spans_listing_date():
    """검색창은 상장 4개월 전 ~ 1개월 후. 연도 경계를 넘어도 깨지지 않아야 한다."""
    bgn, end = cir.search_window("2024-02-10")
    assert bgn == "20231010"
    assert end == "20240310"
