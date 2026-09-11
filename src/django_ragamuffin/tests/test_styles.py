from pathlib import Path

from django.contrib.staticfiles import finders
from django.forms import RadioSelect
from django.template.loader import get_template
from django.test import SimpleTestCase

from django_ragamuffin.views import AssistantEditForm
from django_ragamuffin.utils import query_cost_from_response, response_with_query_cost


class TemplateStylesTests(SimpleTestCase):
    def test_templates_use_shared_stylesheet_without_inline_css(self):
        for name in ("edit_assistant.html", "query_form.html", "upload.html"):
            source = get_template(f"django_ragamuffin/{name}").template.source

            self.assertIn("django_ragamuffin/styles.css", source)
            self.assertNotIn("<style", source)
            self.assertNotIn("style=", source)

    def test_query_form_row_layout_does_not_affect_assistant_file_rows(self):
        stylesheet = Path(
            finders.find("django_ragamuffin/styles.css")
        ).read_text()

        self.assertIn(".query-page .form-row", stylesheet)
        self.assertNotIn("\n.form-row {", stylesheet)

    def test_query_metadata_places_cost_after_tokens(self):
        source = get_template(
            "django_ragamuffin/query_form.html"
        ).template.source

        self.assertIn("tokens={{m.ntokens}} cost={{m.cost", source)
        self.assertIn("ntokens={{ntokens}} cost={{cost", source)

    def test_query_cost_marker_requires_no_model_field(self):
        response = response_with_query_cost("The response", 0.089316)

        self.assertEqual(query_cost_from_response(response), 0.089316)
        self.assertEqual(query_cost_from_response("Historical response"), None)
        self.assertIn("<!-- openta-query-cost:0.089316 -->", response)

    def test_local_file_spacing_follows_the_list(self):
        source = get_template(
            "django_ragamuffin/edit_assistant.html"
        ).template.source

        self.assertIn('class="local-files-section"', source)
        self.assertIn('class="all-file-entries"', source)
        self.assertIn('class="file-list-heading"', source)
        self.assertIn('class="local-file-entries"', source)
        self.assertIn('class="upload-assistant-link"', source)
        self.assertIn('class="file-actions"', source)
        self.assertIn('form="deletion-form"', source)
        self.assertIn("delete-files-button", source)
        self.assertIn("upload-file-button", source)
        self.assertNotIn("<p/> <b> Local files", source)

    def test_assistant_editor_has_three_ordered_sections(self):
        source = get_template(
            "django_ragamuffin/edit_assistant.html"
        ).template.source

        directory = source.index("directory-section")
        heading = source.index("Edit Assistant:")
        files = source.index("files-section")
        instructions = source.index("instructions-section")

        self.assertLess(heading, directory)
        self.assertLess(directory, files)
        self.assertLess(files, instructions)
        self.assertIn('<h2 class="assistant-page-title">', source)
        self.assertEqual(
            AssistantEditForm.base_fields["directory_name"].widget.attrs["form"],
            "assistant-settings-form",
        )
        self.assertIsInstance(
            AssistantEditForm.base_fields["mode_choice"].widget,
            RadioSelect,
        )
        self.assertEqual(
            AssistantEditForm.base_fields["mode_choice"].widget.attrs["class"],
            "mode-choice-options",
        )
        self.assertEqual(
            list(AssistantEditForm.base_fields),
            [
                "mode_choice",
                "actual_instructions",
                "instructions",
                "temperature",
                "directory_name",
            ],
        )
        self.assertEqual(
            AssistantEditForm.base_fields["actual_instructions"].widget.attrs["rows"],
            1,
        )
        self.assertEqual(
            AssistantEditForm.base_fields["instructions"].widget.attrs["rows"],
            5,
        )
        self.assertIn("fitActualInstructions", source)
        self.assertIn("submit-assistant-button", source)
        self.assertEqual(source.count("assistant-action-button"), 3)

        stylesheet = Path(
            finders.find("django_ragamuffin/styles.css")
        ).read_text()
        self.assertIn(".assistant-editor-page > .container", stylesheet)
        self.assertIn("width: 95%", stylesheet)
        self.assertIn("align-items: flex-start", stylesheet)
        self.assertIn("font-size: 0.7rem", stylesheet)
