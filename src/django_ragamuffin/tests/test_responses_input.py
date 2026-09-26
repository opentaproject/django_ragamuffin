import base64

from django.test import SimpleTestCase

from django_ragamuffin.models import build_responses_input


class ResponsesInputTests(SimpleTestCase):
    def test_text_only_input_remains_a_string(self):
        self.assertEqual(build_responses_input("student question"), "student question")

    def test_png_is_added_as_a_vision_input(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "diagram.png"
            image_bytes = b"fake png bytes"
            image_path.write_bytes(image_bytes)

            request_input = build_responses_input(
                "interpret the diagram", [image_path]
            )

        content = request_input[0]["content"]
        self.assertEqual(
            content[0],
            {"type": "input_text", "text": "interpret the diagram"},
        )
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(content[1]["detail"], "auto")
        self.assertEqual(
            content[1]["image_url"],
            "data:image/png;base64,"
            + base64.b64encode(image_bytes).decode("ascii"),
        )

    def test_missing_image_is_skipped(self):
        self.assertEqual(
            build_responses_input("student question", ["/missing/diagram.png"]),
            "student question",
        )
