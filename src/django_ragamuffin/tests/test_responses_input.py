import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase

from django_ragamuffin.models import build_responses_input, retrieved_mmd_images


class ResponsesInputTests(SimpleTestCase):
    def test_text_only_input_remains_a_string(self):
        self.assertEqual(build_responses_input("student question"), "student question")

    def test_png_is_added_as_a_vision_input(self):
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

    def test_source_reference_tells_the_model_how_to_display_the_image(self):
        with TemporaryDirectory() as directory:
            image_path = Path(directory) / "diagram.jpg"
            image_path.write_bytes(b"fake jpeg bytes")
            reference = "./images/diagram.jpg"

            request_input = build_responses_input(
                "show the diagram",
                [image_path],
                {str(image_path): reference},
            )

        content = request_input[0]["content"]
        self.assertEqual(content[1]["type"], "input_text")
        self.assertIn(f"![]({reference})", content[1]["text"])
        self.assertEqual(content[2]["type"], "input_image")

    def test_missing_image_is_skipped(self):
        self.assertEqual(
            build_responses_input("student question", ["/missing/diagram.png"]),
            "student question",
        )


class RetrievedMmdImagesTests(SimpleTestCase):
    def test_resolves_only_images_referenced_by_search_results(self):
        with TemporaryDirectory() as directory:
            image_directory = Path(directory) / "mmd" / "images"
            image_directory.mkdir(parents=True)
            wanted = image_directory / "wanted.jpg"
            wanted.write_bytes(b"wanted")
            (image_directory / "other.jpg").write_bytes(b"other")

            uploaded_file = SimpleNamespace(path=directory)
            vector_store = SimpleNamespace(
                vsid="vs-1",
                files=SimpleNamespace(all=lambda: [uploaded_file]),
            )
            result = SimpleNamespace(
                content=[
                    SimpleNamespace(
                        text="The figure is ![](./images/wanted.jpg)."
                    )
                ]
            )
            client = Mock()
            client.vector_stores.search.return_value = SimpleNamespace(data=[result])

            resolved = retrieved_mmd_images(
                client,
                [vector_store],
                "show the figure",
                8,
            )

        self.assertEqual(resolved, {str(wanted): "./images/wanted.jpg"})
        client.vector_stores.search.assert_called_once_with(
            vector_store_id="vs-1",
            query="show the figure",
            max_num_results=8,
        )
