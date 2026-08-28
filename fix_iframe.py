with open(r'c:\dev\assignment-lms\apps\student\templates\student\lecture.html', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace('allowfullscreen></iframe>', 'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>')
# Also change it back to www.youtube.com just in case youtube-nocookie is causing the error!
text = text.replace('https://www.youtube-nocookie.com/embed/', 'https://www.youtube.com/embed/')

with open(r'c:\dev\assignment-lms\apps\student\templates\student\lecture.html', 'w', encoding='utf-8') as f:
    f.write(text)

with open(r'c:\dev\assignment-lms\apps\tutor\templates\tutor\lecture_manage.html', 'r', encoding='utf-8') as f:
    text2 = f.read()

text2 = text2.replace('allowfullscreen></iframe>', 'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>')
text2 = text2.replace('https://www.youtube-nocookie.com/embed/', 'https://www.youtube.com/embed/')

with open(r'c:\dev\assignment-lms\apps\tutor\templates\tutor\lecture_manage.html', 'w', encoding='utf-8') as f:
    f.write(text2)

print("Added referrerpolicy and reverted to standard youtube")
