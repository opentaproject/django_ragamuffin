import os
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from django_ragamuffin.models import Assistant, QUser, VectorStore
from django_ragamuffin.utils import get_assistant, normalize_assistant_name


class AssistantResolutionTests(TestCase):
    databases = "__all__"

    def setUp(self):
        self.staff = QUser.objects.create(username="staff", subdomain="base", is_staff=True)
        self.student = QUser.objects.create(username="student", subdomain="base", is_staff=False)

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

    def test_assistant_upload_uses_the_path_returned_by_storage(self):
        unique = uuid.uuid4().hex
        assistant = Assistant.objects.create(name=f"uploadtest-{unique}")
        uploaded = SimpleUploadedFile("notes.txt", unique.encode("utf-8"), content_type="text/plain")

        assistant.add_file("notes.txt", uploaded)

        stored_file = assistant.get_vector_stores()[0].files.get()
        self.assertTrue(os.path.isfile(stored_file.file.path))
        self.assertTrue(os.path.isdir(os.path.join(os.path.dirname(stored_file.file.path), "chunks")))
