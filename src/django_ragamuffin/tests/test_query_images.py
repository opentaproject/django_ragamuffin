from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase

from django_ragamuffin.views import query_image_view


class QueryImageTests(SimpleTestCase):
    @patch("django_ragamuffin.views.get_assistant")
    @patch("django_ragamuffin.views.QUser.objects.filter")
    def test_serves_an_image_from_the_assistant_files(
        self, filter_users, get_assistant
    ):
        with TemporaryDirectory() as directory:
            image_directory = Path(directory) / "mmd" / "images"
            image_directory.mkdir(parents=True)
            image_path = image_directory / "figure.jpg"
            image_path.write_bytes(b"image bytes")

            filter_users.return_value.first.return_value = SimpleNamespace(
                username="student", is_staff=False
            )
            uploaded_file = SimpleNamespace(path=directory)
            vector_store = SimpleNamespace(
                files=SimpleNamespace(all=lambda: [uploaded_file])
            )
            get_assistant.return_value = SimpleNamespace(
                get_vector_stores=lambda: [vector_store]
            )
            request = RequestFactory().get(
                "/query/course/images/figure.jpg",
                HTTP_HOST="course-2025.localhost:8000",
            )
            request.user = SimpleNamespace(
                is_authenticated=True,
                username="student",
            )

            response = query_image_view(request, "course", "figure.jpg")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"image bytes")
            get_assistant.assert_called_once_with(
                "course", filter_users.return_value.first.return_value, create=False
            )

    def test_rejects_non_image_filenames(self):
        request = RequestFactory().get("/query/course/images/secrets.txt")
        request.user = SimpleNamespace(is_authenticated=True, username="student")

        with self.assertRaises(Http404):
            query_image_view(request, "course", "secrets.txt")
