# apps/tutor/forms.py
# 튜터팀 — 과제 관리 / 평가 폼
#
# 여기에 들어갈 것:
# - AssignmentForm       : 제목/설명/마감일/필수·지각·팀 여부 — 튜터A (FR-001, FR-002)
# - ResubmitRequestForm  : 재제출 요청 사유 — 튜터A (FR-010, 미구현)
# - EvaluationForm       : 점수/피드백 — 튜터B (FR-013)

from datetime import timedelta

from django import forms
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone

from apps.core.models import Assignment, Evaluation

# HTML5 <input type="datetime-local"> 이 주고받는 포맷
_DATETIME_LOCAL_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]


class AssignmentForm(forms.ModelForm):
    """
    과제 등록/수정 폼 — 튜터A (FR-001 등록 / FR-002 수정).

    Assignment 모델 필드 중 튜터가 직접 다루는 8개를 노출한다:
        title, description, due_at, is_required(FR-008), allow_late(FR-007), is_team(FR-009),
        weight_tier(중요도 — 성적 집계 가중치), late_penalty(지각 감점)
    (created_by / deleted_at 등은 폼 밖에서 처리)

    - 신규 등록 시 due_at 기본값 = 현재 시각 + 24시간.
    - 이미 제출물(Submission)이 1건이라도 있는 과제는 is_team(개인/팀 구분)을
      변경할 수 없다. 바뀌면 기존 Submission 의 student_id XOR team_id 배타 제약
      (submission_student_id_xor_team_id) 및 Submission.clean() 과 충돌하기 때문.
    """

    class Meta:
        model = Assignment
        fields = [
            "title", "description", "due_at",
            "is_required", "allow_late", "is_team",
            "weight_tier", "late_penalty",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "maxlength": 60,
                       "placeholder": "예: 4차 프로젝트 최종 보고서 제출"}
            ),
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "maxlength": 600,
                       "placeholder": "학생들에게 안내할 과제 내용을 입력하세요. "
                                      "(예: 무엇을 해야 하는지, 평가 기준 등)"}
            ),
            "due_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "is_required": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "allow_late": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_team": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "weight_tier": forms.Select(attrs={"class": "form-select"}),
            "late_penalty": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100, "placeholder": "0"}
            ),
        }
        labels = {
            "title": "과제명",
            "description": "설명",
            "due_at": "제출 마감일시",
            "is_required": "필수 과제",
            "allow_late": "지각 제출 허용",
            "is_team": "팀 과제",
            "weight_tier": "중요도",
            "late_penalty": "지각 감점",
        }
        help_texts = {
            "is_required": "체크 해제 시 '선택' 과제로 표시됩니다 (마감·제출·집계 동작은 동일).",
            "allow_late": "허용 시 마감 후 제출도 정상 접수됩니다. 불가 시 마감 후 제출이 차단됩니다.",
            "is_team": "체크 시 팀 단위 제출. 제출물이 하나라도 생기면 이후 변경할 수 없습니다.",
            "weight_tier": "성적 집계 시 이 과제의 비중 (상 1.5 / 중 1.0 / 하 0.5).",
            "late_penalty": "지각 제출 시 튜터 점수에서 차감할 고정 점수. 0이면 감점 없음.",
        }

    def __init__(self, *args, has_submissions=None, **kwargs):
        """
        has_submissions:
            None  → instance 로부터 자동 판단 (기본).
            bool  → 호출 측에서 명시적으로 주입 (테스트/조회 최적화용).
        """
        super().__init__(*args, **kwargs)

        self.fields["due_at"].input_formats = _DATETIME_LOCAL_FORMATS
        # 목업 기준: 과제 설명도 필수 입력 (모델은 blank 허용이나 화면에서는 요구)
        self.fields["description"].required = True

        # 지각 감점: 비워두면 0 (감점 없음). 상한 100.
        self.fields["late_penalty"].required = False
        self.fields["late_penalty"].validators.append(MaxValueValidator(100))

        if has_submissions is None:
            has_submissions = bool(self.instance.pk) and self.instance.submissions.exists()
        self.has_submissions = has_submissions

        # 신규 등록: 마감일시 기본값 = 지금 + 24h (PRD 9장 열려있는 질문 — 프로토타입 기본값)
        if not self.instance.pk and not self.is_bound:
            self.initial.setdefault(
                "due_at",
                (timezone.localtime() + timedelta(hours=24)).replace(second=0, microsecond=0),
            )
            self.initial.setdefault("weight_tier", Assignment.WeightTier.MID)
            self.initial.setdefault("late_penalty", 0)

        # 제출물이 있으면 개인/팀 구분 잠금.
        # 템플릿은 이 플래그를 보고 체크박스를 disabled 로 렌더링하고 현재 값을
        # hidden 으로 실어 보낸다. 정상 제출은 값이 그대로라 통과하고,
        # 위조된 POST 로 값을 바꾸려는 시도는 clean_is_team 이 최종 차단한다.
        if self.has_submissions:
            self.fields["is_team"].help_text = "제출물이 있어 개인/팀 구분을 변경할 수 없습니다."

    def clean_late_penalty(self):
        return self.cleaned_data.get("late_penalty") or 0

    def clean_is_team(self):
        value = self.cleaned_data.get("is_team")
        if self.instance.pk and self.has_submissions and value != self.instance.is_team:
            raise forms.ValidationError(
                "이미 제출물이 있는 과제는 개인/팀 구분을 변경할 수 없습니다."
            )
        return value


class EvaluationForm(forms.ModelForm):
    """
    튜터의 공식 평가 입력/수정 폼 — 튜터B (FR-013).

    - 점수(0~100)와 피드백 텍스트 둘 다 필수 (목업 기준).
    - 저장 시 signals.py 가 Submission.final_score / is_locked 를 동기화하므로
      이 폼은 Evaluation 만 저장하면 된다.
    - 팀 과제도 Submission 이 1행이라 그대로 저장하면 팀 전체에 적용된다 (BR-005).
    - 최초 저장 후에도 수정 가능 (instance 를 넘겨 받으면 수정 모드).
    """

    class Meta:
        model = Evaluation
        fields = ["score", "feedback"]
        labels = {"score": "튜터 점수", "feedback": "피드백"}
        widgets = {
            "score": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100, "placeholder": "0-100"}
            ),
            "feedback": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "maxlength": 1000,
                    "placeholder": "텍스트로 피드백을 남겨주세요.",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["score"].validators.extend(
            [MinValueValidator(0), MaxValueValidator(100)]
        )
        self.fields["score"].error_messages["invalid"] = "숫자를 입력해주세요."
        self.fields["feedback"].required = True  # 모델은 blank 허용이나 화면에서는 필수

