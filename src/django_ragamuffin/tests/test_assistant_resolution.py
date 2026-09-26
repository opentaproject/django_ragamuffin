import os
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from django_ragamuffin.models import Assistant, Mode, ModeChoice, QUser, Thread, VectorStore
from django_ragamuffin.utils import get_assistant, normalize_assistant_name


class AssistantResolutionTests(TestCase):
    databases = "__all__"

    def setUp(self):
        self.staff = QUser.objects.create(username="staff", subdomain="base", is_staff=True)
        self.student = QUser.objects.create(username="student", subdomain="base", is_staff=False)

    def test_file_rows_are_sorted_case_insensitively(self):
        rows = [(1, "zeta.txt"), (2, "Alpha.txt"), (3, "beta.txt")]

        self.assertEqual(
            Assistant._sort_file_rows(rows),
            [(2, "Alpha.txt"), (3, "beta.txt"), (1, "zeta.txt")],
        )

    def test_normalizes_url_path_to_dotted_name(self):
        self.assertEqual(normalize_assistant_name("base/sub1/sub2"), "base.sub1.sub2")

    def test_returns_closest_existing_parent(self):
        parent = Assistant.objects.create(name="base.sub1")

        self.assertEqual(get_assistant("base/sub1/sub2", self.student), parent)

    def test_staff_creates_default_branch_without_copying_fields(self):
        assistant = get_assistant("base/sub1/sub2", self.staff)

        self.assertEqual(assistant.name, "base.sub1.sub2")
        self.assertEqual(
            set(Assistant.objects.values_list("name", flat=True)),
            {"base", "base.sub1", "base.sub1.sub2"},
        )
        self.assertIsNone(assistant.instructions)
        self.assertIsNone(assistant.temperature)
        self.assertIsNone(assistant.mode_choice)

    def test_staff_creates_missing_branch_even_when_base_exists(self):
        Assistant.objects.create(name="base")

        assistant = get_assistant("base/sub1/sub2", self.staff)

        self.assertEqual(assistant.name, "base.sub1.sub2")
        self.assertEqual(
            set(Assistant.objects.values_list("name", flat=True)),
            {"base", "base.sub1", "base.sub1.sub2"},
        )

    def test_staff_creates_missing_parents_when_leaf_already_exists(self):
        leaf = Assistant.objects.create(name="base.sub1.sub2")

        assistant = get_assistant("base/sub1/sub2", self.staff)

        self.assertEqual(assistant, leaf)
        self.assertEqual(
            set(Assistant.objects.values_list("name", flat=True)),
            {"base", "base.sub1", "base.sub1.sub2"},
        )

    def test_temperature_comes_from_closest_ancestor(self):
        root = Assistant.objects.create(name="base.sub1", temperature=0.2)
        child = Assistant.objects.create(name="base.sub1.sub2", temperature=0.4)
        leaf = Assistant.objects.create(name="base.sub1.sub2.leaf")

        self.assertEqual(root.get_temperature(), 0.2)
        self.assertEqual(child.get_temperature(), 0.4)
        self.assertEqual(leaf.get_temperature(), 0.4)

    def test_instructions_and_documents_accumulate_down_branch(self):
        root = Assistant.objects.create(name="base.sub1", instructions="base instructions")
        child = Assistant.objects.create(name="base.sub1.sub2", instructions="child instructions")
        leaf = Assistant.objects.create(name="base.sub1.sub2.leaf")
        root_store, child_store = VectorStore.objects.bulk_create(
            [VectorStore(name="root documents"), VectorStore(name="child documents")]
        )
        through = Assistant.vector_stores.through
        through.objects.bulk_create(
            [
                through(assistant_id=root.pk, vectorstore_id=root_store.pk),
                through(assistant_id=child.pk, vectorstore_id=child_store.pk),
            ]
        )

        instructions = leaf.get_instructions()
        stores = leaf.get_vector_stores()

        self.assertIn("base instructions", instructions)
        self.assertIn("child instructions", instructions)
        self.assertLess(instructions.index("base instructions"), instructions.index("child instructions"))
        self.assertEqual({store.pk for store in stores}, {root_store.pk, child_store.pk})

    def test_non_staff_does_not_create_missing_assistant(self):
        self.assertIsNone(get_assistant("base/sub1/sub2", self.student))
        self.assertFalse(Assistant.objects.exists())

    def test_query_result_includes_usage_dump(self):
        assessment = ModeChoice.objects.create(key="assessment-test", label="Assessment test")
        Mode.objects.create(choice=assessment, text="ASSESSMENT MODE PROLOG")
        assistant = Assistant.objects.create(name="usage-test", mode_choice=assessment)
        thread = Thread(name="usage-test", assistant=assistant, user=self.student)
        thread.save()

        with self.assertLogs("django_ragamuffin.models", level="ERROR") as logs:
            result = thread.run_query(
                query="hello student",
                instructions="QUESTION XML INSTRUCTIONS",
            )

        self.assertEqual(
            result["usage"],
            {
                "input_tokens": 2,
                "input_tokens_details": {"cache_write_tokens": 0, "cached_tokens": 0},
                "output_tokens": 0,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 2,
            },
        )
        self.assertEqual(result["ntokens"], result["usage"]["total_tokens"])
        self.assertEqual(
            result["instructions"],
            "ASSESSMENT MODE PROLOG\nQUESTION XML INSTRUCTIONS",
        )
        logged_instructions = "\n".join(logs.output)
        self.assertIn(result["instructions"], logged_instructions)

    def test_assistant_upload_uses_the_path_returned_by_storage(self):
        unique = uuid.uuid4().hex
        assistant = Assistant.objects.create(name=f"uploadtest-{unique}")
        uploaded = SimpleUploadedFile("notes.txt", unique.encode("utf-8"), content_type="text/plain")

        assistant.add_file("notes.txt", uploaded)

        stored_file = assistant.get_vector_stores()[0].files.get()
        self.assertTrue(os.path.isfile(stored_file.file.path))
        self.assertTrue(os.path.isdir(os.path.join(os.path.dirname(stored_file.file.path), "chunks")))

    @override_settings(AI_KEY="test-key")
    def test_sync_local_files_replaces_only_leaf_files(self):
        root = Assistant.objects.create(name="sync-root")
        leaf = Assistant.objects.create(name="sync-root.leaf")
        root.add_file(
            "inherited.txt",
            SimpleUploadedFile("inherited.txt", b"inherited", content_type="text/plain"),
        )
        leaf.add_file(
            "stale.txt",
            SimpleUploadedFile("stale.txt", b"stale", content_type="text/plain"),
        )

        with TemporaryDirectory() as directory:
            desired = Path(directory) / "exercise.txt"
            desired.write_text("exercise material")
            leaf.sync_local_files([desired])

        self.assertEqual(
            [row[1] for row in leaf.local_files()],
            ["exercise.txt"],
        )
        self.assertEqual(
            set(leaf.file_names()),
            {"exercise.txt", "inherited.txt"},
        )
