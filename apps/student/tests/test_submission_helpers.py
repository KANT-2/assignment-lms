import json

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from apps.core.models import SubmissionFile
from apps.student.forms import MAX_UPLOAD_SIZE, SubmissionForm
from apps.student.views_submit import _notebook_cells, _submission_kind


class SubmissionFormTests(SimpleTestCase):
    def test_rejects_file_larger_than_30_mb(self):
        uploaded = SimpleUploadedFile("large.py", b"x" * (MAX_UPLOAD_SIZE + 1))
        form = SubmissionForm(files={"file": uploaded})
        self.assertFalse(form.is_valid())
        self.assertIn("30MB", form.errors["file"][0])

    def test_accepts_small_file(self):
        form = SubmissionForm(files={"file": SimpleUploadedFile("answer.py", b"print(1)")})
        self.assertTrue(form.is_valid())


class PreviewHelperTests(SimpleTestCase):
    def test_file_kind_is_case_insensitive(self):
        self.assertEqual(_submission_kind("answer.PY"), SubmissionFile.Kind.PY)
        self.assertEqual(_submission_kind("answer.IPYNB"), SubmissionFile.Kind.IPYNB)
        self.assertEqual(_submission_kind("answer.pdf"), SubmissionFile.Kind.OTHER)

    def test_notebook_cells_include_text_output(self):
        raw = json.dumps({"cells": [{
            "cell_type": "code",
            "source": ["print('ok')"],
            "outputs": [{"text": ["ok\n"]}],
        }]})
        self.assertEqual(_notebook_cells(raw)[0]["outputs"], ["ok\n"])

    def test_broken_notebook_returns_none(self):
        self.assertIsNone(_notebook_cells("not-json"))
