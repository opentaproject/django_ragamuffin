import asyncio
import json
import logging
import mimetypes
import os
import re
import time

import httpx
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

MATHPIX_API_ROOT = "https://api.mathpix.com/v3"
MAX_LOGGED_RESPONSE_LENGTH = 4000

preamble = "\\documentclass{article} \n \
    \\usepackage{amsmath}  \n \
    \\usepackage[utf8]{inputenc}  \n  \
    \\usepackage[T1]{fontenc}   \n   \
    \\usepackage{lmodern}      \n   \
    \\usepackage{hyperref}  \n \
    \\title{ mathpix-generated}\n "



def get_mathpix_credentials():
    app_id = getattr(settings, 'APP_ID', None) or os.environ.get('APP_ID')
    app_key = getattr(settings, 'APP_KEY', None) or os.environ.get('APP_KEY')
    if not app_id or not app_key:
        raise ImproperlyConfigured("Mathpix APP_ID and APP_KEY must be configured for PDF conversion.")
    return app_id, app_key


def _setting(name, default, converter):
    value = getattr(settings, name, None)
    if value in (None, ""):
        value = os.environ.get(name, default)
    try:
        return converter(value)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(f"{name} must be a valid {converter.__name__}.") from exc


def _request_id(response):
    headers = getattr(response, "headers", {})
    return headers.get("x-request-id") or headers.get("request-id") or "unavailable"


def _response_request_id(response, payload=None):
    if isinstance(payload, dict) and payload.get("request_id"):
        return payload["request_id"]
    return _request_id(response)


def _response_text(response):
    text = getattr(response, "text", "")
    return text[:MAX_LOGGED_RESPONSE_LENGTH]


def _json_details(value):
    return json.dumps(value, default=str)[:MAX_LOGGED_RESPONSE_LENGTH]


def _json_response(response, operation, job_id=None):
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        logger.error(
            "Mathpix %s returned invalid JSON: job_id=%s http_status=%s "
            "request_id=%s response=%r",
            operation,
            job_id or "not-assigned",
            response.status_code,
            _request_id(response),
            _response_text(response),
        )
        raise RuntimeError(
            f"Mathpix {operation} returned invalid JSON "
            f"(job_id={job_id or 'not-assigned'}, HTTP {response.status_code})."
        ) from exc
    if not isinstance(payload, dict):
        logger.error(
            "Mathpix %s returned unexpected JSON: job_id=%s http_status=%s "
            "request_id=%s response=%s",
            operation,
            job_id or "not-assigned",
            response.status_code,
            _request_id(response),
            _json_details(payload),
        )
        raise RuntimeError(
            f"Mathpix {operation} returned unexpected JSON "
            f"(job_id={job_id or 'not-assigned'}, HTTP {response.status_code})."
        )
    return payload


def _detected_content_type(file_path):
    with open(file_path, "rb") as source:
        signature = source.read(16)
    if signature.startswith(b"%PDF-"):
        return "application/pdf"
    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if signature.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if signature.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if signature.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if signature.startswith(b"BM"):
        return "image/bmp"
    if signature.startswith(b"RIFF") and signature[8:12] == b"WEBP":
        return "image/webp"
    return mimetypes.guess_type(file_path)[0] or "application/octet-stream"


def _normalise_mmd(text):
    text = re.sub(r'\\\(', '$', text)
    return re.sub(r'\\\)', '$', text)


async def convert_pdf_file(pdf_path, format_out='mmd'):
    app_id, app_key = get_mathpix_credentials()
    headers = {
        "app_id": app_id,
        "app_key": app_key
    }
    filename = os.path.basename(pdf_path)
    poll_interval = _setting("MATHPIX_POLL_INTERVAL_SECONDS", 2, float)
    poll_timeout = _setting("MATHPIX_POLL_TIMEOUT_SECONDS", 600, float)
    http_timeout = _setting("MATHPIX_HTTP_TIMEOUT_SECONDS", 60, float)
    job_id = None
    current_operation = "submission"
    current_url = f"{MATHPIX_API_ROOT}/pdf"

    try:
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            with open(pdf_path, 'rb') as pdf_file:
                files = {
                    'file': (filename, pdf_file, 'application/pdf'),
                    'options_json': (
                        None,
                        json.dumps({
                            "ocr": ["math", "text"],
                            "formats": ["latex_styled", "latex_simplified", "mmd"],
                            "include_image_data": True,
                        }),
                        'application/json'
                    )
                }
                response = await client.post(current_url, headers=headers, files=files)

            if response.status_code != 200:
                logger.error(
                    "Mathpix PDF submission failed: filename=%s http_status=%s "
                    "request_id=%s response=%r",
                    filename,
                    response.status_code,
                    _request_id(response),
                    _response_text(response),
                )
                raise RuntimeError(
                    f"Mathpix PDF submission failed (HTTP {response.status_code}, "
                    f"request_id={_request_id(response)})."
                )

            submission = _json_response(response, "PDF submission")
            job_id = submission.get("pdf_id")
            if not job_id:
                logger.error(
                    "Mathpix PDF submission returned no pdf_id: filename=%s request_id=%s "
                    "response=%s",
                    filename,
                    _request_id(response),
                    _json_details(submission),
                )
                raise RuntimeError("Mathpix PDF submission returned no pdf_id.")
            logger.info(
                "Mathpix PDF submitted: job_id=%s filename=%s request_id=%s",
                job_id,
                filename,
                _request_id(response),
            )

            # PDF jobs are polled at /v3/pdf/{pdf_id}.  /v3/converter/{pdf_id}
            # only describes separately requested conversion-format jobs.
            current_operation = "status poll"
            current_url = f"{MATHPIX_API_ROOT}/pdf/{job_id}"
            deadline = time.monotonic() + poll_timeout
            while True:
                poll = await client.get(current_url, headers=headers)
                if poll.status_code != 200:
                    logger.error(
                        "Mathpix status poll failed: job_id=%s http_status=%s "
                        "request_id=%s response=%r",
                        job_id,
                        poll.status_code,
                        _request_id(poll),
                        _response_text(poll),
                    )
                    raise RuntimeError(
                        f"Mathpix status poll failed (job_id={job_id}, "
                        f"HTTP {poll.status_code}, request_id={_request_id(poll)})."
                    )

                poll_result = _json_response(poll, "status poll", job_id)
                status = poll_result.get("status")
                logger.info(
                    "Mathpix PDF status: job_id=%s status=%s percent_done=%s "
                    "pages_completed=%s pages_total=%s request_id=%s",
                    job_id,
                    status or "missing",
                    poll_result.get("percent_done", "unavailable"),
                    poll_result.get("num_pages_completed", "unavailable"),
                    poll_result.get("num_pages", "unavailable"),
                    _request_id(poll),
                )
                if status == "completed":
                    break
                if status == "error":
                    details = _json_details(poll_result)
                    logger.error(
                        "Mathpix PDF processing failed: job_id=%s request_id=%s details=%s",
                        job_id,
                        _request_id(poll),
                        details,
                    )
                    raise RuntimeError(
                        f"Mathpix PDF processing failed (job_id={job_id}): {details}"
                    )
                if time.monotonic() >= deadline:
                    logger.error(
                        "Mathpix PDF processing timed out: job_id=%s timeout_seconds=%s "
                        "last_status=%s",
                        job_id,
                        poll_timeout,
                        status or "missing",
                    )
                    raise RuntimeError(
                        f"Mathpix PDF processing timed out after {poll_timeout:g} seconds "
                        f"(job_id={job_id}, last_status={status or 'missing'})."
                    )
                await asyncio.sleep(poll_interval)

            current_operation = "result download"
            current_url = f"{MATHPIX_API_ROOT}/pdf/{job_id}.{format_out}"
            result = await client.get(current_url, headers=headers)
            if result.status_code != 200:
                logger.error(
                    "Mathpix result download failed: job_id=%s format=%s http_status=%s "
                    "request_id=%s response=%r",
                    job_id,
                    format_out,
                    result.status_code,
                    _request_id(result),
                    _response_text(result),
                )
                raise RuntimeError(
                    f"Mathpix result download failed (job_id={job_id}, "
                    f"format={format_out}, HTTP {result.status_code}, "
                    f"request_id={_request_id(result)})."
                )
            logger.info(
                "Mathpix result downloaded: job_id=%s format=%s bytes=%s request_id=%s",
                job_id,
                format_out,
                len(result.content),
                _request_id(result),
            )
    except httpx.RequestError as exc:
        request = getattr(exc, "_request", None)
        logger.exception(
            "Mathpix network request failed: operation=%s job_id=%s filename=%s "
            "method=%s url=%s",
            current_operation,
            job_id or "not-assigned",
            filename,
            getattr(request, "method", "unknown"),
            getattr(request, "url", current_url),
        )
        raise RuntimeError(
            f"Mathpix network request failed during {current_operation} "
            f"(job_id={job_id or 'not-assigned'}): {exc}"
        ) from exc

    s = _normalise_mmd(result.content.decode('utf-8', errors='replace'))
    if format_out == 'tex':
        _, m, r = s.partition(r'\begin{document')
        s = m + r
        b, m, _ = s.partition(r'\end{document}')
        s = b + m
        s = re.sub(r'^\s*\n', '', s, flags=re.MULTILINE)
        s = f"{preamble} {s}"
    return s


async def convert_image_file(image_path, format_out='mmd'):
    app_id, app_key = get_mathpix_credentials()
    headers = {
        "app_id": app_id,
        "app_key": app_key,
    }
    filename = os.path.basename(image_path)
    content_type = _detected_content_type(image_path)
    http_timeout = _setting("MATHPIX_HTTP_TIMEOUT_SECONDS", 60, float)
    url = f"{MATHPIX_API_ROOT}/text"

    if not content_type.startswith("image/"):
        raise RuntimeError(
            f"Mathpix image conversion requires an image; detected {content_type} "
            f"for {filename}."
        )

    options = {
        "formats": ["text", "latex_styled", "latex_simplified"],
        "enable_document_layout": True,
    }
    try:
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            with open(image_path, "rb") as image_file:
                files = {
                    "file": (filename, image_file, content_type),
                    "options_json": (
                        None,
                        json.dumps(options),
                        "application/json",
                    ),
                }
                response = await client.post(url, headers=headers, files=files)
    except httpx.RequestError as exc:
        request = getattr(exc, "_request", None)
        logger.exception(
            "Mathpix image request failed: filename=%s content_type=%s method=%s url=%s",
            filename,
            content_type,
            getattr(request, "method", "unknown"),
            getattr(request, "url", url),
        )
        raise RuntimeError(f"Mathpix image request failed for {filename}: {exc}") from exc

    if response.status_code != 200:
        try:
            error_details = _json_details(response.json())
        except (TypeError, ValueError):
            error_details = _response_text(response)
        logger.error(
            "Mathpix image processing failed: filename=%s content_type=%s "
            "http_status=%s request_id=%s response=%s",
            filename,
            content_type,
            response.status_code,
            _request_id(response),
            error_details,
        )
        raise RuntimeError(
            f"Mathpix image processing failed for {filename} "
            f"(HTTP {response.status_code}, request_id={_request_id(response)}): "
            f"{error_details}"
        )

    payload = _json_response(response, "image processing")
    request_id = _response_request_id(response, payload)
    error_info = payload.get("error_info") or payload.get("error")
    if error_info:
        details = _json_details(error_info)
        logger.error(
            "Mathpix image processing returned an error: filename=%s content_type=%s "
            "request_id=%s details=%s",
            filename,
            content_type,
            request_id,
            details,
        )
        raise RuntimeError(
            f"Mathpix image processing failed for {filename} "
            f"(request_id={request_id}): {details}"
        )

    output_field = {
        "mmd": "text",
        "text": "text",
        "latex_styled": "latex_styled",
        "latex_simplified": "latex_simplified",
    }.get(format_out)
    if output_field is None:
        raise RuntimeError(
            f"Mathpix image output format {format_out!r} is not supported."
        )
    output = payload.get(output_field)
    if output is None:
        details = _json_details(payload)
        logger.error(
            "Mathpix image response omitted output: filename=%s output_field=%s "
            "request_id=%s response=%s",
            filename,
            output_field,
            request_id,
            details,
        )
        raise RuntimeError(
            f"Mathpix image response omitted {output_field!r} for {filename} "
            f"(request_id={request_id})."
        )

    logger.info(
        "Mathpix image processed: filename=%s content_type=%s request_id=%s "
        "confidence=%s confidence_rate=%s output_chars=%s",
        filename,
        content_type,
        request_id,
        payload.get("confidence", "unavailable"),
        payload.get("confidence_rate", "unavailable"),
        len(output),
    )
    return _normalise_mmd(output) if output_field == "text" else output


def mathpix(file_path, format_out='mmd'):
    content_type = _detected_content_type(file_path)
    if content_type == "application/pdf":
        conversion = convert_pdf_file(file_path, format_out)
    elif content_type.startswith("image/"):
        conversion = convert_image_file(file_path, format_out)
    else:
        raise RuntimeError(
            f"Unsupported Mathpix input type {content_type!r} for "
            f"{os.path.basename(file_path)}."
        )
    return asyncio.run(conversion)
