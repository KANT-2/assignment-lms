import re

# Student
with open(r'c:\dev\assignment-lms\apps\student\templates\student\lecture.html', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('href="student-assignment-submission.html"', 'href="{% url \'student:dashboard\' %}"')

with open(r'c:\dev\assignment-lms\apps\student\templates\student\lecture.html', 'w', encoding='utf-8') as f:
    f.write(text)

# Tutor
with open(r'c:\dev\assignment-lms\apps\tutor\templates\tutor\lecture_manage.html', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('href="tutor-assignment-submission.html"', 'href="{% url \'tutor:assignment-list\' %}"')

with open(r'c:\dev\assignment-lms\apps\tutor\templates\tutor\lecture_manage.html', 'w', encoding='utf-8') as f:
    f.write(text)

print("Fixed submission links")
