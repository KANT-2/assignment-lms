with open(r'c:\dev\assignment-lms\apps\student\templates\student\lecture.html', 'r', encoding='utf-8') as f:
    text = f.read()
text = text.replace('href="student-dashboard.html"', 'href="{% url \'student:dashboard\' %}"')
with open(r'c:\dev\assignment-lms\apps\student\templates\student\lecture.html', 'w', encoding='utf-8') as f:
    f.write(text)

with open(r'c:\dev\assignment-lms\apps\tutor\templates\tutor\lecture_manage.html', 'r', encoding='utf-8') as f:
    text2 = f.read()
text2 = text2.replace('href="tutor-assign-management.html"', 'href="{% url \'tutor:assignment-list\' %}"')
with open(r'c:\dev\assignment-lms\apps\tutor\templates\tutor\lecture_manage.html', 'w', encoding='utf-8') as f:
    f.write(text2)
print("Fixed links")
