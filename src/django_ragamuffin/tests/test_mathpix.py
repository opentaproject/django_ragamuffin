import asyncio
import json
import logging

import pytest
from django.test import override_settings

from django_ragamuffin import mathpix


class FakeResponse:
    def __init__(self, status_code, payload=None, content=b"", request_id="request-1"):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = {"x-request-id": request_id}
        self.text = content.decode("utf-8", errors="replace")

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.post_kwargs = None
        self.timeout = None

    def factory(self, *, timeout):
        self.timeout = timeout
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        self.post_kwargs = kwargs
        return next(self.responses)

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return next(self.responses)


@override_settings(
    APP_ID="test-app-id",
    APP_KEY="test-app-key",
    MATHPIX_POLL_INTERVAL_SECONDS=0,
    MATHPIX_POLL_TIMEOUT_SECONDS=10,
    MATHPIX_HTTP_TIMEOUT_SECONDS=12,
)
def test_convert_pdf_polls_pdf_status_endpoint(monkeypatch, tmp_path, caplog):
    source = tmp_path / "answer.pdf"
    source.write_bytes(b"%PDF test")
    client = FakeAsyncClient([
        FakeResponse(200, {"pdf_id": "job-123"}, request_id="submit-request"),
        FakeResponse(200, {
            "status": "processing",
            "percent_done": 50,
            "num_pages_completed": 1,
            "num_pages": 2,
        }, request_id="poll-request-1"),
        FakeResponse(200, {"status": "completed"}, request_id="poll-request-2"),
        FakeResponse(200, content=b"Result \\(x\\)", request_id="download-request"),
    ])
    monkeypatch.setattr(mathpix.httpx, "AsyncClient", client.factory)

    with caplog.at_level(logging.INFO, logger=mathpix.__name__):
        result = asyncio.run(mathpix.convert_pdf_file(str(source)))

    assert result == "Result $x$"
    assert client.timeout == 12
    assert client.calls == [
        ("POST", "https://api.mathpix.com/v3/pdf"),
        ("GET", "https://api.mathpix.com/v3/pdf/job-123"),
        ("GET", "https://api.mathpix.com/v3/pdf/job-123"),
        ("GET", "https://api.mathpix.com/v3/pdf/job-123.mmd"),
    ]
    assert "/converter/" not in " ".join(url for _, url in client.calls)
    assert "job_id=job-123 status=processing" in caplog.text
    assert "percent_done=50" in caplog.text


@override_settings(
    APP_ID="test-app-id",
    APP_KEY="test-app-key",
    MATHPIX_POLL_INTERVAL_SECONDS=0,
    MATHPIX_POLL_TIMEOUT_SECONDS=10,
)
def test_convert_pdf_reports_mathpix_processing_error(monkeypatch, tmp_path, caplog):
    source = tmp_path / "answer.pdf"
    source.write_bytes(b"%PDF test")
    client = FakeAsyncClient([
        FakeResponse(200, {"pdf_id": "job-456"}),
        FakeResponse(200, {
            "status": "error",
            "error": "Unsupported PDF",
            "conversion_status": {},
        }, request_id="failed-poll-request"),
    ])
    monkeypatch.setattr(mathpix.httpx, "AsyncClient", client.factory)

    with caplog.at_level(logging.ERROR, logger=mathpix.__name__):
        with pytest.raises(RuntimeError) as exc_info:
            asyncio.run(mathpix.convert_pdf_file(str(source)))

    assert "job_id=job-456" in str(exc_info.value)
    assert "Unsupported PDF" in str(exc_info.value)
    assert "request_id=failed-poll-request" in caplog.text
    assert "Unsupported PDF" in caplog.text


@override_settings(
    APP_ID="test-app-id",
    APP_KEY="test-app-key",
    MATHPIX_POLL_INTERVAL_SECONDS=0,
    MATHPIX_POLL_TIMEOUT_SECONDS=10,
)
def test_convert_pdf_reports_status_http_error(monkeypatch, tmp_path, caplog):
    source = tmp_path / "answer.pdf"
    source.write_bytes(b"%PDF test")
    client = FakeAsyncClient([
        FakeResponse(200, {"pdf_id": "job-789"}),
        FakeResponse(
            503,
            content=b"temporary Mathpix failure",
            request_id="failed-http-request",
        ),
    ])
    monkeypatch.setattr(mathpix.httpx, "AsyncClient", client.factory)

    with caplog.at_level(logging.ERROR, logger=mathpix.__name__):
        with pytest.raises(RuntimeError) as exc_info:
            asyncio.run(mathpix.convert_pdf_file(str(source)))

    message = str(exc_info.value)
    assert "job_id=job-789" in message
    assert "HTTP 503" in message
    assert "request_id=failed-http-request" in message
    assert "temporary Mathpix failure" in caplog.text


@override_settings(
    APP_ID="test-app-id",
    APP_KEY="test-app-key",
    MATHPIX_HTTP_TIMEOUT_SECONDS=12,
)
def test_mathpix_sends_png_to_synchronous_image_endpoint(monkeypatch, tmp_path, caplog):
    source = tmp_path / "answer.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test image")
    client = FakeAsyncClient([
        FakeResponse(200, {
            "request_id": "image-request",
            "text": "Image result \\(x + y\\)",
            "confidence": 0.98,
            "confidence_rate": 0.95,
        }),
    ])
    monkeypatch.setattr(mathpix.httpx, "AsyncClient", client.factory)

    with caplog.at_level(logging.INFO, logger=mathpix.__name__):
        result = mathpix.mathpix(str(source))

    assert result == "Image result $x + y$"
    assert client.calls == [("POST", "https://api.mathpix.com/v3/text")]
    file_part = client.post_kwargs["files"]["file"]
    assert file_part[0] == "answer.png"
    assert file_part[2] == "image/png"
    options = json.loads(client.post_kwargs["files"]["options_json"][1])
    assert options["enable_document_layout"] is True
    assert "request_id=image-request" in caplog.text


@override_settings(APP_ID="test-app-id", APP_KEY="test-app-key")
def test_mathpix_rejects_unsupported_input_before_api_call(monkeypatch, tmp_path):
    source = tmp_path / "answer.txt"
    source.write_text("not an image or PDF")
    client = FakeAsyncClient([])
    monkeypatch.setattr(mathpix.httpx, "AsyncClient", client.factory)

    with pytest.raises(RuntimeError, match="Unsupported Mathpix input type"):
        mathpix.mathpix(str(source))

    assert client.calls == []
