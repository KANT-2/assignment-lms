import os
import re

mockup_path = r'c:\dev\assignment-lms\docs\mockups\student-lecture.html'
template_path = r'c:\dev\assignment-lms\apps\student\templates\student\lecture.html'

with open(mockup_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Extract styles
style_match = re.search(r'<style>(.*?)</style>', html, re.DOTALL)
styles = style_match.group(1) if style_match else ''

# Remove generic body styling that might conflict with base.html
styles = re.sub(r'body\s*\{[^}]*\}', '', styles)
styles = re.sub(r'\*\s*\{[^}]*\}', '', styles)
styles = re.sub(r'html,\s*body\s*\{[^}]*\}', '', styles)

# Extract body content
body_match = re.search(r'<div class="wrap">(.*?)</body>', html, re.DOTALL)
body_content = body_match.group(1) if body_match else ''
body_content = '<div class="wrap">' + body_content

# Extract scripts
script_match = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
script_content = script_match.group(1) if script_match else ''

# Replace localStorage logic with Django context variable
script_content = re.sub(
    r'const STORAGE_KEY =.*?let lessonsData = \[\];', 
    'const lessonsData = {{ lessons_json|safe }};\nlet currentLessonId = null;\nlet selectedDateStr = null;\nlet currentCalDate = new Date();', 
    script_content, flags=re.DOTALL
)

script_content = re.sub(
    r'function loadLessons\(\) \{.*?if \(lessonsData.length === 0\) return;',
    'function loadLessons() {\n    if (lessonsData.length === 0) return;',
    script_content, flags=re.DOTALL
)


# Construct Django template
django_html = f"""{{% extends 'base.html' %}}

{{% block title %}}강의 및 교안{{% endblock %}}

{{% block extra_head %}}
<style>
{styles}
</style>
{{% endblock %}}

{{% block content %}}
{body_content}
{{% endblock %}}

{{% block extra_script %}}
<script>
{script_content}
</script>
{{% endblock %}}
"""

os.makedirs(os.path.dirname(template_path), exist_ok=True)
with open(template_path, 'w', encoding='utf-8') as f:
    f.write(django_html)

print("Student template generated.")
