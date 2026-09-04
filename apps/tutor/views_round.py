"""
apps/tutor/views_round.py — 👨‍🏫 튜터B · 회차 점수 마감 (FR: docs/assignment-lms-round-close.md)

튜터가 "이번 회차 점수 마감"을 누르면 이 회차 과제로 학생별 점수를 계산해 RoundScore 로 박제한다.
재마감은 덮어쓰기. 외부 데이터(AX)는 읽기 전용.
"""
import csv

from django.contrib import messages
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.accounts_client import services as accounts
from apps.core.models import Assignment

from . import grading
from .models import RoundScore
from .views_student import tutor_required


def _current_round_or_404():
    rnd = accounts.get_current_round()
    if rnd is None:
        raise Http404("현재 라운드를 찾을 수 없습니다.")
    return rnd


def _score_changed(sc, row) -> bool:
    """실시간 계산(sc)이 박제된 스냅샷(row)과 달라졌는지 — 재마감 유도 판정."""
    def r(x):
        return round(x, 1) if x is not None else None

    return (r(sc.final), r(sc.achievement), r(sc.sincerity)) != (
        r(row.total), r(row.achievement), r(row.sincerity)
    )


def _preview(round_obj, now):
    """마감 전 미리보기 — 저장하지 않고 계산만."""
    students = list(accounts.get_students() or [])
    assignments = grading.scope_assignments(round_obj.id, now=now)
    teams = grading._safe_student_teams()
    team_included = grading._team_included(assignments, teams)

    scores = grading.compute(
        [s.id for s in students], now=now, assignments=assignments
    )
    ungraded_total = sum(sc.ungraded_count for sc in scores.values())
    computable = sum(1 for sc in scores.values() if sc.final is not None)
    period = accounts.get_round_period(round_obj.id)

    # ── 학생별 점수 미리보기 (저장 안 함) — 산출 가능 → 최종 높은 순 ──
    preview_rows = sorted(
        (
            {"name": getattr(s, "name", None) or f"학생 #{s.id}", "sc": scores.get(s.id, grading.StudentScore())}
            for s in students
        ),
        key=lambda r: (r["sc"].final is None, -(r["sc"].final or 0), r["name"]),
    )
    finals = [sc.final for sc in scores.values() if sc.final is not None]
    avg_final = round(sum(finals) / len(finals), 1) if finals else None

    # ── 과제별 채점 진행 (제출 대비 튜터 평가 등록 수) ──
    progress = {
        row["id"]: row
        for row in Assignment.all_objects.filter(id__in=[a.id for a in assignments])
        .annotate(
            _sub=Count("submissions", distinct=True),
            _graded=Count("submissions", filter=Q(submissions__evaluation__isnull=False), distinct=True),
        )
        .values("id", "_sub", "_graded")
    }
    for a in assignments:
        p = progress.get(a.id, {"_sub": 0, "_graded": 0})
        a.grade_total = p["_sub"]
        a.grade_done = p["_graded"]
        a.grade_missing = p["_sub"] - p["_graded"]

    # ── 마지막 마감 이후 점수가 달라진 학생 수 (재마감 유도) ──
    existing = RoundScore.objects.filter(round_id=round_obj.id).order_by("-closed_at").first()
    stale_count = 0
    if existing:
        snap = {r.student_id: r for r in RoundScore.objects.filter(round_id=round_obj.id)}
        stale_count = sum(
            1
            for sid, sc in scores.items()
            if sid in snap and _score_changed(sc, snap[sid])
        )

    return {
        "round": round_obj,
        "period": period,
        "students": students,
        "student_count": len(students),
        "assignments": assignments,
        "team_assignment_count": sum(1 for a in assignments if a.is_team),
        "team_included": team_included,
        "ungraded_total": ungraded_total,
        "computable_count": computable,
        "preview_rows": preview_rows,
        "avg_final": avg_final,
        "existing": existing,
        "stale_count": stale_count,
    }


@tutor_required
def round_close(request):
    """GET: 마감 확인 화면. POST: 마감 실행 → 결과로 이동."""
    now = timezone.now()
    round_obj = _current_round_or_404()

    if request.method == "POST":
        raw_ids = request.POST.getlist("assignment_ids")
        assignment_ids = [int(i) for i in raw_ids] if raw_ids else None
        result = grading.snapshot(round_obj, request.user.id, assignment_ids=assignment_ids, now=now)
        messages.success(
            request,
            f"{round_obj.title} 점수를 마감했습니다. "
            f"학생 {result.student_count}명"
            + ("" if result.team_included else " · 팀 미편성(개인 점수만)"),
        )
        return redirect("tutor:round-close-result", round_id=round_obj.id)

    ctx = _preview(round_obj, now)
    return render(request, "tutor/round_close.html", ctx)


@tutor_required
def round_close_result(request, round_id):
    rows = RoundScore.objects.filter(round_id=round_id)
    if not rows.exists():
        raise Http404("마감된 회차가 아닙니다.")
    head = rows.first()
    return render(request, "tutor/round_close_result.html", {
        "round_id": round_id,
        "round_title": head.round_title,
        "closed_at": head.closed_at,
        "team_included": head.team_included,
        "rows": rows,
        "assignment_ids": head.assignment_ids,
    })


@tutor_required
def round_close_csv(request, round_id):
    rows = RoundScore.objects.filter(round_id=round_id)
    if not rows.exists():
        raise Http404("마감된 회차가 아닙니다.")

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="round_{round_id}_scores.csv"'
    response.write("﻿")  # Excel 한글 깨짐 방지 BOM

    writer = csv.writer(response)
    writer.writerow(["student_id", "student_name", "round_id", "round_title", "total", "team_included", "closed_at"])
    for r in rows:
        writer.writerow([
            r.student_id, r.student_name, r.round_id, r.round_title,
            "" if r.total is None else f"{r.total:.1f}",
            "true" if r.team_included else "false",
            timezone.localtime(r.closed_at).isoformat(timespec="seconds"),
        ])
    return response
