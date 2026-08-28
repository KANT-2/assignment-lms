"""apps/accounts_client/forms.py — 로그인 폼 (공통 담당)."""
from django import forms
from django.contrib.auth import authenticate


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="이메일",
        widget=forms.EmailInput(attrs={"class": "form-control", "autofocus": True}),
    )
    password = forms.CharField(
        label="비밀번호",
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
    )
    remember = forms.BooleanField(
        label="로그인 상태 유지",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        email, password = data.get("email"), data.get("password")
        if email and password:
            self.user = authenticate(self.request, email=email, password=password)
            if self.user is None:
                # 미승인 계정이면 다른 안내 (backend 는 인증 실패로 처리)
                from .backends import account_login_status

                if account_login_status(email):
                    raise forms.ValidationError(
                        "계정이 아직 승인되지 않았거나 비활성 상태입니다. 관리자에게 문의하세요."
                    )
                raise forms.ValidationError("이메일 또는 비밀번호가 올바르지 않습니다.")
        return data

    def get_user(self):
        return self.user
