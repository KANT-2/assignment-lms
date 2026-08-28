import os
import re

mockup_path = r'c:\dev\assignment-lms\docs\mockups\tutor-lecture.html'
template_path = r'c:\dev\assignment-lms\apps\tutor\templates\tutor\lecture_manage.html'

with open(mockup_path, 'r', encoding='utf-8') as f:
    html = f.read()

# Extract styles
style_match = re.search(r'<style>(.*?)</style>', html, re.DOTALL)
styles = style_match.group(1) if style_match else ''
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

# Replace localStorage initialization
script_content = re.sub(
    r'const STORAGE_KEY =.*?let lessons = \[\];',
    'let lessons = {{ lessons_json|safe }};\nconst csrfToken = "{{ csrf_token }}";',
    script_content, flags=re.DOTALL
)

# Remove the window.onload data fetching
script_content = re.sub(
    r'window\.onload = function\(\) \{.*?if \(stored\) \{.*?else \{.*?\}.*?\}',
    'window.onload = function() {',
    script_content, flags=re.DOTALL
)

# Replace saveToStorage to use fetch API
save_to_storage_js = """
function saveToStorage() {
  fetch('/tutor/lecture/api/update/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken
    },
    body: JSON.stringify({lessons: lessons})
  }).then(res => res.json()).then(data => {
    if(data.status !== 'success') console.error('Save failed', data);
  }).catch(e => console.error('Error saving:', e));
}
"""

script_content = re.sub(
    r'function saveToStorage\(\) \{.*?\}',
    save_to_storage_js.strip(),
    script_content, flags=re.DOTALL
)


# Construct Django template
django_html = f"""{{% extends 'base.html' %}}

{{% block title %}}강의 및 교안 관리{{% endblock %}}

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

# Clean up duplicate scripts inside block content
django_html = re.sub(r'{{% block content %}}(.*?)<script>.*?</script>(.*?){{% endblock %}}', r'{% block content %}\1\2{% endblock %}', django_html, flags=re.DOTALL)

os.makedirs(os.path.dirname(template_path), exist_ok=True)
with open(template_path, 'w', encoding='utf-8') as f:
    f.write(django_html)

print("Tutor template generated.")
