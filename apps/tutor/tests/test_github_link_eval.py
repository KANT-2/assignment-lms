"""
AI 채점 — 학생 GitHub 링크 코드 읽기 (docs/assignment-lms-github-link-eval.md).

github_fetch (URL 파싱·화이트리스트·fetch) · ai_gemini._build_prompt (링크 분기·예산·
못 읽은 링크 수집) · generate (읽은 자료 0건 → NoReadableContent).
"""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.models import Assignment, Submission, SubmissionFile
from apps.tutor import ai_gemini, github_fetch


class GithubUrlTests(TestCase):
    def test_is_github_url(self):
        ok = [
            "https://github.com/o/r/blob/main/a.py",
            "https://raw.githubusercontent.com/o/r/main/a.py",
            "https://www.github.com/o/r",
        ]
        bad = [
            "https://gitlab.com/o/r/blob/main/a.py",
            "https://myblog.tistory.com/1",
            "http://127.0.0.1:8000/admin/",
            "https://github.com.evil.com/o/r",
            "not a url",
        ]
        for u in ok:
            self.assertTrue(github_fetch.is_github_url(u), u)
        for u in bad:
            self.assertFalse(github_fetch.is_github_url(u), u)

    def test_raw_url_conversion(self):
        self.assertEqual(
            github_fetch.raw_url("https://github.com/jin/Tutor_task/blob/main/ch11/task01.py"),
            "https://raw.githubusercontent.com/jin/Tutor_task/main/ch11/task01.py",
        )
        self.assertEqual(
            github_fetch.raw_url("https://raw.githubusercontent.com/jin/r/main/a.py"),
            "https://raw.githubusercontent.com/jin/r/main/a.py",
        )
        # blob·raw 아님 → None
        for u in [
            "https://github.com/jin/Tutor_task",
            "https://github.com/jin/Tutor_task/tree/main/ch11",
            "https://github.com/jin/Tutor_task/pull/3",
        ]:
            self.assertIsNone(github_fetch.raw_url(u), u)


class FetchGithubFileTests(TestCase):
    def _resp(self, status=200, content=b"print(1)\n"):
        return SimpleNamespace(status_code=status, content=content)

    def test_success(self):
        with patch("apps.tutor.github_fetch.requests.get", return_value=self._resp()):
            got = github_fetch.fetch_github_file("https://github.com/o/r/blob/main/a.py")
        self.assertEqual(got, "print(1)\n")

    def test_non_github_returns_none(self):
        got = github_fetch.fetch_github_file("https://blog.example.com/post")
        self.assertIsNone(got)

    def test_unsupported_github_form_returns_none(self):
        got = github_fetch.fetch_github_file("https://github.com/o/r")  # 레포 루트
        self.assertIsNone(got)

    def test_404(self):
        with patch("apps.tutor.github_fetch.requests.get", return_value=self._resp(status=404)):
            self.assertIsNone(
                github_fetch.fetch_github_file("https://github.com/o/r/blob/main/a.py")
            )

    def test_too_large(self):
        big = b"x" * (513 * 1024)
        with patch("apps.tutor.github_fetch.requests.get", return_value=self._resp(content=big)):
            self.assertIsNone(
                github_fetch.fetch_github_file("https://github.com/o/r/blob/main/a.py")
            )

    def test_binary(self):
        with patch("apps.tutor.github_fetch.requests.get", return_value=self._resp(content=b"\xff\xfe\x00")):
            self.assertIsNone(
                github_fetch.fetch_github_file("https://github.com/o/r/blob/main/a.py")
            )

    def test_network_error(self):
        with patch("apps.tutor.github_fetch.requests.get", side_effect=github_fetch.requests.RequestException):
            self.assertIsNone(
                github_fetch.fetch_github_file("https://github.com/o/r/blob/main/a.py")
            )


class BuildPromptTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.assignment = Assignment.objects.create(
            title="과제1", description="설명", due_at=timezone.now(),
            is_team=False, created_by=1,
        )
        self.submission = Submission.objects.create(
            assignment=self.assignment, student_id=11, description="제출 설명",
        )

    def _file(self, *, name, url, kind=SubmissionFile.Kind.OTHER):
        return SubmissionFile.objects.create(
            submission=self.submission, kind=kind, file_url=url, file_name=name, file_size=0,
        )

    def test_local_file_counted(self):
        self._file(name="a.py", url="/media/submissions/11/a.py", kind=SubmissionFile.Kind.PY)
        with patch("apps.tutor.ai_gemini._read_text", return_value="def f(): return 1"):
            prompt, read_count, unreadable = ai_gemini._build_prompt(self.submission)
        self.assertEqual(read_count, 1)
        self.assertEqual(unreadable, [])
        self.assertIn("def f(): return 1", prompt)

    def test_github_link_fetched_and_counted(self):
        self._file(name="https://github.com/o/r/blob/main/a.py",
                   url="https://github.com/o/r/blob/main/a.py")
        with patch("apps.tutor.ai_gemini._read_text", return_value=None), \
             patch("apps.tutor.ai_gemini.github_fetch.fetch_github_file", return_value="print('hi from gh')"):
            prompt, read_count, unreadable = ai_gemini._build_prompt(self.submission)
        self.assertEqual(read_count, 1)
        self.assertEqual(unreadable, [])
        self.assertIn("print('hi from gh')", prompt)

    def test_broken_github_link_only(self):
        url = "https://github.com/o/r/blob/main/missing.py"
        self._file(name=url, url=url)
        with patch("apps.tutor.ai_gemini._read_text", return_value=None), \
             patch("apps.tutor.ai_gemini.github_fetch.fetch_github_file", return_value=None):
            prompt, read_count, unreadable = ai_gemini._build_prompt(self.submission)
        self.assertEqual(read_count, 0)
        self.assertEqual(unreadable, [url])
        self.assertIn("확인 불가", prompt)

    def test_mixed_file_plus_broken_link(self):
        self._file(name="a.py", url="/media/submissions/11/a.py", kind=SubmissionFile.Kind.PY)
        url = "https://github.com/o/r/blob/main/missing.py"
        self._file(name=url, url=url)

        def fake_read(sf):
            return "code here" if sf.file_url.startswith("/media/") else None

        with patch("apps.tutor.ai_gemini._read_text", side_effect=fake_read), \
             patch("apps.tutor.ai_gemini.github_fetch.fetch_github_file", return_value=None):
            prompt, read_count, unreadable = ai_gemini._build_prompt(self.submission)
        self.assertEqual(read_count, 1)
        self.assertEqual(unreadable, [url])

    def test_non_github_link(self):
        url = "https://myblog.tistory.com/1"
        self._file(name=url, url=url)
        with patch("apps.tutor.ai_gemini._read_text", return_value=None):
            prompt, read_count, unreadable = ai_gemini._build_prompt(self.submission)
        self.assertEqual(read_count, 0)
        self.assertEqual(unreadable, [url])
        self.assertIn("지원하지 않는 링크", prompt)

    def test_ipynb_link_cell_parsed(self):
        url = "https://github.com/o/r/blob/main/nb.ipynb"
        self._file(name=url, url=url)
        raw = '{"cells":[{"cell_type":"code","source":["x = 1\\n","print(x)"]}]}'
        with patch("apps.tutor.ai_gemini._read_text", return_value=None), \
             patch("apps.tutor.ai_gemini.github_fetch.fetch_github_file", return_value=raw):
            prompt, read_count, unreadable = ai_gemini._build_prompt(self.submission)
        self.assertEqual(read_count, 1)
        self.assertIn("[code cell]", prompt)
        self.assertIn("print(x)", prompt)
        self.assertNotIn('"cell_type"', prompt)  # 원본 JSON 아님

    @override_settings(GEMINI_API_KEY="test")
    def test_generate_raises_when_nothing_readable(self):
        url = "https://github.com/o/r/blob/main/missing.py"
        self._file(name=url, url=url)
        with patch("apps.tutor.ai_gemini._read_text", return_value=None), \
             patch("apps.tutor.ai_gemini.github_fetch.fetch_github_file", return_value=None):
            with self.assertRaises(ai_gemini.NoReadableContent) as ctx:
                ai_gemini.generate(self.submission)
        self.assertEqual(ctx.exception.links, [url])
