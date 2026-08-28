with open(r'c:\dev\assignment-lms\apps\common\templates\includes\topbar.html', 'r', encoding='utf-8') as f:
    text = f.read()

swap_buttons = '''
    <a href="{% url 'student:dashboard' %}" class="btn btn-sm btn-outline-success ms-2">학생 모드</a>
    <a href="{% url 'tutor:assignment-list' %}" class="btn btn-sm btn-outline-primary ms-2">강사 모드</a>
'''

text = text.replace('<div class="utils">', '<div class="utils">' + swap_buttons)

with open(r'c:\dev\assignment-lms\apps\common\templates\includes\topbar.html', 'w', encoding='utf-8') as f:
    f.write(text)

print("Added swap buttons")
