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


def test_search_window_clamps_invalid_day_for_short_months():
    """상장일이 29~31일이면 4개월 전/1개월 후가 그 일자가 없는 달일 수 있다
    (예: 5/31 -4개월 = 1/31은 유효하지만 +1개월 = 6/31은 존재하지 않음).
    DART API는 이런 날짜를 status=100(잘못된 날짜형식)으로 거부하므로,
    실제 있는 마지막 날로 클램프해야 한다. 실측: KC산업(2016-05-31)."""
    bgn, end = cir.search_window("2016-05-31")
    assert bgn == "20160131"      # 1월은 31일까지 있어 그대로
    assert end == "20160630"      # 6월은 30일까지 → 31이 아니라 30으로 클램프

    # 로스웰(2016-06-30): 4개월 전 = 2월, 2016년은 윤년이라 29일까지
    bgn2, _ = cir.search_window("2016-06-30")
    assert bgn2 == "20160229"


class _FakeDocResp:
    """document.xml 응답. 정상은 zip 바이너리, 오류는 JSON/XML 본문이 온다."""

    def __init__(self, content=b"", ctype="application/x-msdownload", text=""):
        self.content = content
        self.headers = {"content-type": ctype}
        self.text = text

    def json(self):
        import json
        return json.loads(self.text)


def test_find_impl_report_returns_none_only_for_no_data(monkeypatch):
    """status=013(조회결과 없음)만 na로 간다 — 공모 없는 상장의 정상 신호."""
    monkeypatch.setattr(cir, "_fetch_with_retry",
                        lambda *a, **k: _FakeResp({"status": "013"}))
    assert cir.find_impl_report("01573336", "2024-11-07") is None


def test_find_impl_report_raises_on_unknown_status(monkeypatch):
    """000/013이 아닌 status를 na로 적으면 안 된다.

    na는 재수집 스킵 대상이라 한 번 잘못 적히면 영구히 되돌아오지 않는다.
    '공모가 없다'와 'API가 이상하다'를 같은 칸에 적으면 구분할 방법이 사라진다.
    error로 기록돼 다음 실행에서 재시도되도록 예외를 올린다.
    """
    monkeypatch.setattr(cir, "_fetch_with_retry",
                        lambda *a, **k: _FakeResp({"status": "100",
                                                   "message": "부적절한 필드 값"}))
    with pytest.raises(cir.DartStatusError):
        cir.find_impl_report("01573336", "2024-11-07")


def test_dart_status_error_is_not_runtime_error():
    """한도류(RuntimeError)는 중단, 그 밖의 status 이상은 회사별 error로 기록.

    main()이 `except RuntimeError: raise` 로 둘을 가르므로 상속 관계가 뒤집히면
    한도 초과가 회사별 error로 삼켜진다.
    """
    assert not issubclass(cir.DartStatusError, RuntimeError)


def test_fetch_document_raises_on_quota_body(monkeypatch):
    """document.xml 한도 초과는 BadZipFile이 아니라 한도 예외로 올라와야 한다.

    zip이 아닌 JSON 본문을 그대로 unzip하면 BadZipFile이 나고, 호출부의 광범위한
    except가 이를 회사별 '파싱실패'로 적는다 — 한도 벽에 부딪힌 뒤 남은 회사
    전량이 조용히 오분류되고 이미 소진된 한도를 계속 두드린다.
    """
    monkeypatch.setattr(cir, "_fetch_with_retry", lambda *a, **k: _FakeDocResp(
        ctype="application/json;charset=UTF-8",
        text='{"status":"020","message":"요청 제한을 초과하였습니다."}'))
    with pytest.raises(RuntimeError, match="한도"):
        cir.fetch_document("20241031000452")


def test_fetch_document_raises_on_error_body_xml(monkeypatch):
    """XML 에러 본문(비한도)도 삼키지 않고 error로 기록되게 올린다."""
    monkeypatch.setattr(cir, "_fetch_with_retry", lambda *a, **k: _FakeDocResp(
        ctype="text/xml; charset=utf-8",
        text="<result><status>101</status><message>부적절한 접근</message></result>"))
    with pytest.raises(cir.DartStatusError):
        cir.fetch_document("20241031000452")


def test_fetch_document_unzips_normal_binary_response(monkeypatch):
    """정상 응답(zip 바이너리)은 그대로 풀어서 디코딩한다."""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("doc.xml", "<TABLE>내용</TABLE>".encode("cp949"))
    monkeypatch.setattr(cir, "_fetch_with_retry", lambda *a, **k: _FakeDocResp(
        content=buf.getvalue(), ctype="application/x-msdownload"))
    assert cir.fetch_document("20241031000452") == "<TABLE>내용</TABLE>"
