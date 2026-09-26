import uuid
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.urls import reverse


class UploadPageTests(SimpleTestCase):
    def test_upload_page_contains_multi_file_progress(self):
        response = self.client.get(reverse("upload", kwargs={"pk": 1}))

        self.assertContains(response, 'id="upload-progress"')
        self.assertContains(response, 'id="upload-progress-text"')
        html = response.content.decode()
        self.assertIn("django_ragamuffin/batch-progress.js", html)
        self.assertIn('formId: "upload-form"', html)

    @patch("django_ragamuffin.views.Assistant.objects.get")
    def test_batch_upload_records_completed_file_count(self, get_assistant):
        upload_id = uuid.uuid4()
        response = self.client.post(
            reverse("upload", kwargs={"pk": 1}),
            {
                "upload_id": str(upload_id),
                "myfile": [
                    SimpleUploadedFile("one.txt", b"one"),
                    SimpleUploadedFile("two.txt", b"two"),
                ],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_assistant.return_value.add_file.call_count, 2)
        status = self.client.get(reverse("upload_status", kwargs={"pk": 1, "upload_id": upload_id}))
        self.assertEqual(status.json(), {"completed": 2, "total": 2})

    @patch("django_ragamuffin.views.Assistant.objects.get")
    def test_upload_logs_failed_file_with_traceback(self, get_assistant):
        upload_id = uuid.uuid4()
        get_assistant.return_value.add_file.side_effect = RuntimeError("upload broke")

        with self.assertLogs("django_ragamuffin.views", level="ERROR") as logs:
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse("upload", kwargs={"pk": 1}),
                    {
                        "upload_id": str(upload_id),
                        "myfile": SimpleUploadedFile("large.pdf", b"%PDF-test"),
                    },
                )

        output = "\n".join(logs.output)
        self.assertIn("stage=received", output)
        self.assertIn("stage=failed", output)
        self.assertIn("large.pdf", output)

    def test_client_upload_failure_is_logged(self):
        with self.assertLogs("django_ragamuffin.views", level="ERROR") as logs:
            response = self.client.post(
                reverse("upload", kwargs={"pk": 7}),
                {
                    "upload_client_event": "1",
                    "client_stage": "failed",
                    "upload_id": "upload-123",
                    "http_status": "413",
                    "status_text": "Content Too Large",
                    "error": "upload failed with status 413",
                    "files": '[{"name":"large.pdf","size":123456,"type":"application/pdf"}]',
                    "response": "request body exceeded the configured limit",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"reported": True})
        output = "\n".join(logs.output)
        self.assertIn("stage=client_failed", output)
        self.assertIn("http_status=413", output)
        self.assertIn("large.pdf", output)
        self.assertIn("request body exceeded", output)

    def test_client_upload_start_is_logged_before_file_transfer(self):
        with self.assertLogs("django_ragamuffin.views", level="ERROR") as logs:
            response = self.client.post(
                reverse("upload", kwargs={"pk": 7}),
                {
                    "upload_client_event": "1",
                    "client_stage": "started",
                    "upload_id": "upload-124",
                    "files": '[{"name":"stuck.pdf","size":654321,"type":"application/pdf"}]',
                },
            )

        self.assertEqual(response.status_code, 200)
        output = "\n".join(logs.output)
        self.assertIn("stage=client_started", output)
        self.assertIn("stuck.pdf", output)


class EmptyAssistantForm:
    custom_data = []
    local_files = [(1, "one.txt", "checksum", "one.txt"), (2, "two.txt", "checksum", "two.txt")]

    def __iter__(self):
        return iter(())


class DeletionProgressTests(SimpleTestCase):
    def test_edit_page_contains_multi_file_deletion_progress(self):
        html = render_to_string(
            "django_ragamuffin/edit_assistant.html",
            {"assistant": SimpleNamespace(pk=1, name="assistant"), "form": EmptyAssistantForm()},
        )

        self.assertIn('id="deletion-progress"', html)
        self.assertIn('id="deletion-progress-text"', html)
        self.assertIn('formId: "deletion-form"', html)

    @patch("django_ragamuffin.views.get_object_or_404")
    def test_batch_deletion_records_completed_file_count(self, get_object_or_404):
        deletion_id = uuid.uuid4()
        assistant = get_object_or_404.return_value
        assistant.pk = 1

        response = self.client.post(
            reverse("edit_assistant", kwargs={"pk": 1}),
            {"deletion_id": str(deletion_id), "deletion": ["1", "2"]},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(assistant.delete_file.call_count, 2)
        status = self.client.get(
            reverse("deletion_status", kwargs={"pk": 1, "deletion_id": deletion_id})
        )
        self.assertEqual(status.json(), {"completed": 2, "total": 2})
