"""apps/accounts_client/views.py — 로그인/로그아웃 (공통 담당)."""
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import LoginForm

_REMEMBER_AGE = 60 * 60 * 24 * 14  # 2주


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect(request.GET.get("next") or "/")

    form = LoginForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        login(
            request,
            form.get_user(),
            backend="apps.accounts_client.backends.AxPasswordBackend",
        )
        request.session.set_expiry(_REMEMBER_AGE if form.cleaned_data["remember"] else 0)
        return redirect(request.POST.get("next") or request.GET.get("next") or "/")

    return render(request, "registration/login.html", {"form": form})


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect("login")
