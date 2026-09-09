"""apps/common — 공용 미리보기 로직."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.common.preview import _is_link_submission, _preview
from apps.core.models import SubmissionFile


def _sf(*, file_url, file_name, file_size, kind=SubmissionFile.Kind.OTHER):
    return SimpleNamespace(
        file_url=file_url, file_name=file_name, file_size=file_size, kind=kind
    )


class IsLinkSubmissionTests(SimpleTestCase):
    def test_link_submission_detected(self):
        sf = _sf(
            file_url="https://github.com/x/y",
            file_name="https://github.com/x/y",
            file_size=0,
        )
        self.assertTrue(_is_link_submission(sf))
        self.assertTrue(_preview(sf)["is_link"])

    def test_uploaded_file_is_not_a_link(self):
        sf = _sf(
            file_url="/media/submissions/11/abc_solution.py",
            file_name="solution.py",
            file_size=1234,
        )
        self.assertFalse(_is_link_submission(sf))
        self.assertFalse(_preview(sf)["is_link"])

    def test_link_wins_over_extension_heuristics(self):
        # 확장자가 .png 인 링크라도 is_image 가 아니라 is_link 로 잡혀야 한다.
        sf = _sf(
            file_url="https://example.com/chart.png",
            file_name="https://example.com/chart.png",
            file_size=0,
        )
        preview = _preview(sf)
        self.assertTrue(preview["is_link"])
        self.assertFalse(preview["is_image"])
