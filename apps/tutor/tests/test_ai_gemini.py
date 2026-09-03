"""
ai_gemini.generate — Gemini 응답 매핑 (채점 루브릭 프롬프트 · docs 없음).

실제 API 는 부르지 않는다. genai.Client 를 목으로 갈아끼워
score 클램핑 / comment 검증 / requirements_check 무시(저장 안 함) 를 확인한다.
"""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from google.genai.errors import ServerError

from apps.tutor import ai_gemini


def _fake_client(parsed, text="{}"):
    response = SimpleNamespace(parsed=parsed, text=text)
    models = SimpleNamespace(generate_content=lambda **kw: response)
    return lambda **kw: SimpleNamespace(models=models)


def _server_error(code=503):
    return ServerError(code, {"error": {"message": "busy", "status": "UNAVAILABLE"}})


def _fake_client_by_model(outcomes):
    """outcomes: {model_name: _GeminiResult | Exception}. 모델별로 다르게 응답."""
    def generate_content(**kw):
        result = outcomes[kw["model"]]
        if isinstance(result, Exception):
            raise result
        return SimpleNamespace(parsed=result, text="{}")

    return lambda **kw: SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )


@override_settings(GEMINI_API_KEY="test")
class GenerateMappingTests(SimpleTestCase):
    def _submission(self):
        sub = SimpleNamespace(
            assignment=SimpleNamespace(title="과제", description="설명", is_team=False),
            description="",
            files=SimpleNamespace(all=lambda: [SimpleNamespace(
                file_name="a.py", file_url="/media/a.py", file_size=10)]),
        )
        return sub

    def test_maps_score_and_comment_and_ignores_requirements_check(self):
        parsed = ai_gemini._GeminiResult(
            requirements_check="1) 함수명 OK 2) 짝수 필터 OK", score=88, comment="좋은 구현입니다.",
        )
        with patch("apps.tutor.ai_gemini._read_text", return_value="code"), \
             patch("apps.tutor.ai_gemini.genai.Client", side_effect=_fake_client(parsed)):
            result = ai_gemini.generate(self._submission())
        self.assertEqual(result.score, 88)
        self.assertEqual(result.comment, "좋은 구현입니다.")
        self.assertFalse(hasattr(result, "requirements_check"))

    def test_score_is_clamped(self):
        parsed = ai_gemini._GeminiResult(score=150, comment="ok")
        with patch("apps.tutor.ai_gemini._read_text", return_value="code"), \
             patch("apps.tutor.ai_gemini.genai.Client", side_effect=_fake_client(parsed)):
            self.assertEqual(ai_gemini.generate(self._submission()).score, 100)

    def test_requirements_check_defaults_when_omitted(self):
        # 모델이 requirements_check 를 빼먹어도 파싱은 통과해야 한다.
        parsed = ai_gemini._GeminiResult(score=70, comment="부분 구현입니다.")
        self.assertEqual(parsed.requirements_check, "")
        with patch("apps.tutor.ai_gemini._read_text", return_value="code"), \
             patch("apps.tutor.ai_gemini.genai.Client", side_effect=_fake_client(parsed)):
            self.assertEqual(ai_gemini.generate(self._submission()).score, 70)

    def test_blank_comment_rejected(self):
        parsed = ai_gemini._GeminiResult(score=50, comment="   ")
        with patch("apps.tutor.ai_gemini._read_text", return_value="code"), \
             patch("apps.tutor.ai_gemini.genai.Client", side_effect=_fake_client(parsed)):
            with self.assertRaises(ValueError):
                ai_gemini.generate(self._submission())

    @override_settings(GEMINI_MODEL="primary", GEMINI_FALLBACK_MODELS=["backup"])
    def test_falls_back_to_next_model_on_server_error(self):
        outcomes = {
            "primary": _server_error(503),
            "backup": ai_gemini._GeminiResult(score=77, comment="폴백 모델 채점."),
        }
        with patch("apps.tutor.ai_gemini._read_text", return_value="code"), \
             patch("apps.tutor.ai_gemini.genai.Client",
                   side_effect=_fake_client_by_model(outcomes)):
            result = ai_gemini.generate(self._submission())
        self.assertEqual(result.score, 77)

    @override_settings(GEMINI_MODEL="primary", GEMINI_FALLBACK_MODELS=["backup"])
    def test_all_models_server_error_reraises(self):
        outcomes = {"primary": _server_error(503), "backup": _server_error(504)}
        with patch("apps.tutor.ai_gemini._read_text", return_value="code"), \
             patch("apps.tutor.ai_gemini.genai.Client",
                   side_effect=_fake_client_by_model(outcomes)):
            with self.assertRaises(ServerError):
                ai_gemini.generate(self._submission())

    @override_settings(GEMINI_MODEL="only", GEMINI_FALLBACK_MODELS=[])
    def test_no_fallback_configured(self):
        outcomes = {"only": _server_error(503)}
        with patch("apps.tutor.ai_gemini._read_text", return_value="code"), \
             patch("apps.tutor.ai_gemini.genai.Client",
                   side_effect=_fake_client_by_model(outcomes)):
            with self.assertRaises(ServerError):
                ai_gemini.generate(self._submission())
