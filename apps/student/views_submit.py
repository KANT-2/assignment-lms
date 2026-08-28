# apps/student/views_submit.py
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib import messages
from django.db import models
from apps.core.models import Assignment, Submission, SubmissionFile
from apps.student.views_dashboard import student_required
from apps.accounts_client import services as accounts

@student_required
def assignment_list(request):
    uid = request.user.id
    team = accounts.get_user_team(uid)
    
    # Active assignments only
    assignments = Assignment.objects.all().order_by('due_at')
    
    # User's submissions (personal and team)
    mine = models.Q(student_id=uid)
    if team:
        mine |= models.Q(team_id=team.id)
        
    my_subs = {s.assignment_id: s for s in Submission.objects.filter(mine)}
    
    context_list = []
    for a in assignments:
        if a.is_team and not team:
            continue # skip team assignments if student has no team
            
        sub = my_subs.get(a.id)
        status = 'todo'
        if sub:
            status = 'graded' if sub.final_score is not None else 'done'
            
        is_late = timezone.now() > a.due_at
            
        context_list.append({
            'assignment': a,
            'submission': sub,
            'status': status,
            'is_late': is_late,
            'is_team': a.is_team,
            'due_date_str': timezone.localtime(a.due_at).strftime('%Y-%m-%d'),
        })
        
    return render(request, 'student/assignment_list.html', {
        'assignments_data': context_list
    })

@student_required
def submission_form(request, pk):
    assignment = get_object_or_404(Assignment, pk=pk)
    uid = request.user.id
    team = accounts.get_user_team(uid)
    
    if assignment.is_team and not team:
        messages.error(request, '배정된 팀이 없어 팀 과제에 접근할 수 없습니다.')
        return redirect('student:assignment-list')
        
    # Check existing submission
    if assignment.is_team:
        sub = Submission.objects.filter(assignment=assignment, team_id=team.id).first()
    else:
        sub = Submission.objects.filter(assignment=assignment, student_id=uid).first()
        
    is_late = timezone.now() > assignment.due_at
    can_submit = not sub and (not is_late or assignment.allow_late)
    
    if request.method == 'POST' and can_submit:
        description = request.POST.get('description', '').strip()
        
        # Create submission
        sub = Submission.objects.create(
            assignment=assignment,
            student_id=None if assignment.is_team else uid,
            team_id=team.id if assignment.is_team else None,
            description=description,
        )
        
        # Note: Actual file uploads would be processed here using request.FILES
        # For this mockup, we just redirect back to the form (which will now show as 'done')
        messages.success(request, '과제가 성공적으로 제출되었습니다.')
        return redirect('student:submission-form', pk=pk)

    return render(request, 'student/submission_form.html', {
        'assignment': assignment,
        'submission': sub,
        'is_late': is_late,
        'can_submit': can_submit,
        'team': team,
    })
