"""학생 제출 폼."""

from django import forms

MAX_UPLOAD_SIZE = 30 * 1024 * 1024


class SubmissionForm(forms.Form):
    description = forms.CharField(
        label="과제 설명",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 5,
            "placeholder": "제출물에 대한 간단한 설명을 작성해 주세요.",
        }),
    )
    file = forms.FileField(
        label="제출 파일",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if uploaded_file and uploaded_file.size > MAX_UPLOAD_SIZE:
            raise forms.ValidationError("파일 크기는 30MB를 초과할 수 없습니다.")
        return uploaded_file


class AssignmentSubmissionForm(SubmissionForm):
    """파일 또는 링크를 복수로 받는 최초 제출 화면용 폼."""
    file = forms.FileField(
        label="제출 파일",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control"}),
    )


class ResubmissionForm(AssignmentSubmissionForm):
    """파일 또는 링크를 복수로 받아 기존 최종 제출본을 덮어쓰는 폼."""
