import hashlib
import os
import uuid
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import django_ragamuffin.models as models_module
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings

from django_ragamuffin.models import Assistant, Mode, ModeChoice, QUser, Thread, VectorStore
from django_ragamuffin.utils import get_assistant, normalize_assistant_name
from django_ragamuffin.views import AssistantEditForm


def test_sync_local_files_locks_on_assistant_database(monkeypatch):
    events = []

    @contextmanager
    def atomic(*, using):
        events.append(("atomic-enter", using))
        try:
            yield
        finally:
            events.append(("atomic-exit", using))

    class QuerySet:
        def using(self, alias):
            events.append(("using", alias))
            return self

        def select_for_update(self):
            events.append(("select-for-update",))
            return self

        def get(self, *, pk):
            events.append(("get", pk))
            return SimpleNamespace(local_files=lambda: [])

    sync_local_files = Assistant.sync_local_files
    assistant = SimpleNamespace(
        pk=17,
        _state=SimpleNamespace(db="django_ragamuffin"),
    )
    monkeypatch.setattr(models_module.transaction, "atomic", atomic)
    monkeypatch.setattr(
        models_module,
        "Assistant",
        SimpleNamespace(objects=QuerySet()),
    )

    assert sync_local_files(assistant, []) == []
    assert events == [
        ("atomic-enter", "django_ragamuffin"),
        ("using", "django_ragamuffin"),
        ("select-for-update",),
        ("get", 17),
        ("atomic-exit", "django_ragamuffin"),
    ]


class AssistantResolutionTests(TestCase):
    databases = "__all__"

    def setUp(self):
        self.staff = QUser.objects.create(username="staff", subdomain="base", is_staff=True)
        self.student = QUser.objects.create(username="student", subdomain="base", is_staff=False)

    def test_assistant_edit_form_preserves_instruction_newlines(self):
        assistant = Assistant.objects.create(
            name=f"instruction-format-{uuid.uuid4().hex}",
            instructions="First paragraph.\n\nSecond paragraph.\n  Indented line.",
        )

        form = AssistantEditForm(instance=assistant)

        self.assertEqual(
            form.fields["actual_instructions"].initial,
            "First paragraph.\n\nSecond paragraph.\n  Indented line.",
        )

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

    def test_non_creating_lookup_does_not_create_missing_assistant_for_staff(self):
        parent = Assistant.objects.create(name="base.sub1")

        self.assertEqual(
            get_assistant("base/sub1/sub2", self.staff, create=False),
            parent,
        )
        self.assertEqual(
            list(Assistant.objects.values_list("name", flat=True)),
            ["base.sub1"],
        )

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

    def test_png_upload_is_converted_to_searchable_mathpix_chunks(self):
        assistant = Assistant.objects.create(name=f"png-upload-{uuid.uuid4().hex}")
        uploaded = SimpleUploadedFile(
            "diagram.png",
            b"\x89PNG\r\n\x1a\nimage-data",
            content_type="image/png",
        )

        with patch.object(models_module, "mathpix", return_value="Diagram result \\(x\\)") as convert:
            assistant.add_file("diagram.png", uploaded)

        stored_file = assistant.get_vector_stores()[0].files.get()
        chunk_file = Path(stored_file.file.path).parent / "chunks" / "diagram.json"
        vision_file = Path(stored_file.file.path).parent / "mmd" / "images" / "diagram.png"
        convert.assert_called_once_with(stored_file.file.path, format_out="mmd")
        self.assertTrue(chunk_file.is_file())
        self.assertIn("Diagram result", chunk_file.read_text())
        self.assertIn("./images/diagram.png", chunk_file.read_text())
        self.assertEqual(vision_file.read_bytes(), b"\x89PNG\r\n\x1a\nimage-data")

    def test_pdf_upload_is_reprocessed_when_cached_mmd_directory_is_missing(self):
        assistant = Assistant.objects.create(name=f"pdf-repair-{uuid.uuid4().hex}")
        pdf_content = b"%PDF-1.4\nidentical-pdf"

        def convert_pdf(src, format_out):
            (Path(src).parent / "mmd").mkdir(exist_ok=True)
            return "# Converted"

        with patch.object(models_module, "mathpix", side_effect=convert_pdf) as convert:
            assistant.add_file(
                "document.pdf",
                SimpleUploadedFile("document.pdf", pdf_content, content_type="application/pdf"),
            )
            original = assistant.vector_stores.get().files.get()
            mmd_directory = Path(original.file.path).parent / "mmd"
            for child in mmd_directory.rglob("*"):
                if child.is_file():
                    child.unlink()
            for child in sorted(mmd_directory.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            mmd_directory.rmdir()

            assistant.add_file(
                "document.pdf",
                SimpleUploadedFile("document.pdf", pdf_content, content_type="application/pdf"),
            )

        repaired = assistant.vector_stores.get().files.get()
        self.assertNotEqual(repaired.pk, original.pk)
        self.assertTrue((Path(repaired.file.path).parent / "mmd").is_dir())
        self.assertEqual(convert.call_count, 2)

    def test_backfill_command_dry_runs_then_repairs_missing_mmd(self):
        assistant = Assistant.objects.create(name=f"pdf-backfill-{uuid.uuid4().hex}")
        pdf_content = b"%PDF-1.4\nbackfill-pdf"

        def convert_pdf(src, format_out):
            (Path(src).parent / "mmd").mkdir(exist_ok=True)
            return "# Converted"

        with patch.object(models_module, "mathpix", side_effect=convert_pdf):
            assistant.add_file(
                "backfill.pdf",
                SimpleUploadedFile("backfill.pdf", pdf_content, content_type="application/pdf"),
            )

        original = assistant.vector_stores.get().files.get()
        mmd_directory = Path(original.file.path).parent / "mmd"
        mmd_directory.rmdir()

        dry_run_output = StringIO()
        with patch.object(models_module, "mathpix") as convert:
            call_command("backfill_ragamuffin_mmd", dry_run=True, stdout=dry_run_output)
        convert.assert_not_called()
        self.assertFalse(mmd_directory.exists())
        self.assertIn("WOULD REPROCESS", dry_run_output.getvalue())

        output = StringIO()
        with patch.object(models_module, "mathpix", side_effect=convert_pdf) as convert:
            call_command("backfill_ragamuffin_mmd", stdout=output)

        convert.assert_called_once()
        self.assertTrue(mmd_directory.is_dir())
        command_output = output.getvalue()
        self.assertIn("PROCESSING [1/1] file=backfill.pdf", command_output)
        self.assertIn("DONE [1/1] file=backfill.pdf", command_output)
        self.assertLess(command_output.index("PROCESSING"), command_output.index("DONE"))

    def test_image_without_mathpix_content_is_preserved_for_vision(self):
        assistant = Assistant.objects.create(name=f"figure-upload-{uuid.uuid4().hex}")
        uploaded = SimpleUploadedFile(
            "figure.jpg",
            b"\xff\xd8\xfffigure-data",
            content_type="image/jpeg",
        )

        with patch.object(
            models_module,
            "mathpix",
            side_effect=models_module.MathpixNoContentError("Content not found"),
        ):
            assistant.add_file("figure.jpg", uploaded)

        stored_file = assistant.get_vector_stores()[0].files.get()
        chunk_file = Path(stored_file.file.path).parent / "chunks" / "figure.json"
        vision_file = Path(stored_file.file.path).parent / "mmd" / "images" / "figure.jpg"
        self.assertIn("./images/figure.jpg", chunk_file.read_text())
        self.assertEqual(vision_file.read_bytes(), b"\xff\xd8\xfffigure-data")

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

    @override_settings(AI_KEY="test-key")
    def test_sync_local_files_skips_unchanged_file(self):
        assistant = Assistant.objects.create(name="sync-unchanged")

        with TemporaryDirectory() as directory:
            desired = Path(directory) / "exercise.txt"
            desired.write_text("unchanged exercise material")
            assistant.sync_local_files([desired])
            original = assistant.vector_stores.get().files.get()
            original_file_ids = list(original.file_ids)

            with patch.object(Assistant, "add_file_by_name") as add_file_by_name:
                assistant.sync_local_files([desired])

        current = assistant.vector_stores.get().files.get()
        add_file_by_name.assert_not_called()
        self.assertEqual(current.pk, original.pk)
        self.assertEqual(current.file_ids, original_file_ids)

    @override_settings(AI_KEY="test-key")
    def test_sync_local_files_uploads_changed_content_with_same_name(self):
        assistant = Assistant.objects.create(name="sync-same-name")

        with TemporaryDirectory() as directory:
            desired = Path(directory) / "exercise.txt"
            desired.write_text("original exercise material")
            assistant.sync_local_files([desired])
            vector_store = assistant.vector_stores.get()
            original = vector_store.files.get()
            original_file_ids = set(original.file_ids)

            desired.write_text("updated exercise material")
            with self.assertLogs("django_ragamuffin.models", level="ERROR") as logs:
                assistant.sync_local_files([desired])

        vector_store.refresh_from_db()
        current = vector_store.files.get()
        current_file_ids = set(current.file_ids)
        self.assertEqual(current.name, "exercise.txt")
        self.assertEqual(
            current.checksum,
            hashlib.md5(b"updated exercise material").hexdigest(),
        )
        self.assertNotEqual(current.pk, original.pk)
        self.assertTrue(current_file_ids)
        self.assertTrue(current_file_ids.isdisjoint(original_file_ids))
        self.assertTrue(vector_store.files_ok())
        self.assertIn("stage=openai_file_upload_start", "\n".join(logs.output))

    @override_settings(AI_KEY="test-key")
    def test_same_name_replacement_does_not_remove_inherited_file(self):
        root = Assistant.objects.create(name="sync-shared-name")
        leaf = Assistant.objects.create(name="sync-shared-name.leaf")
        root.add_file(
            "exercise.txt",
            SimpleUploadedFile("exercise.txt", b"inherited material", content_type="text/plain"),
        )
        leaf.add_file(
            "exercise.txt",
            SimpleUploadedFile("exercise.txt", b"old local material", content_type="text/plain"),
        )
        inherited_pk = root.vector_stores.get().files.get().pk

        with TemporaryDirectory() as directory:
            desired = Path(directory) / "exercise.txt"
            desired.write_text("new local material")
            leaf.sync_local_files([desired])

        self.assertEqual(root.vector_stores.get().files.get().pk, inherited_pk)
        self.assertEqual(
            leaf.vector_stores.get().files.get().checksum,
            hashlib.md5(b"new local material").hexdigest(),
        )
        self.assertEqual(
            {row[0] for row in leaf.files()},
            {inherited_pk, leaf.vector_stores.get().files.get().pk},
        )
