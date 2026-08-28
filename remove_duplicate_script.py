import re

with open(r'c:\dev\assignment-lms\apps\tutor\templates\tutor\lecture_manage.html', 'r', encoding='utf-8') as f:
    text = f.read()

# We need to find the first <script> block and remove it.
# The first script block is inside {% block content %} and ends with </script>
text = re.sub(r'<script>.*?</script>', '', text, count=1, flags=re.DOTALL)

with open(r'c:\dev\assignment-lms\apps\tutor\templates\tutor\lecture_manage.html', 'w', encoding='utf-8') as f:
    f.write(text)

print("Removed first script block")
