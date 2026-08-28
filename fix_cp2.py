import re

with open(r'c:\dev\assignment-lms\apps\common\context_processors.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = re.sub(
    r'    match = getattr\(request, "resolver_match", None\).*?return \{',
    '''    match = getattr(request, "resolver_match", None)
    
    if getattr(settings, "DEV_SKIP_AUTH", False):
        if request.path.startswith("/tutor/"):
            role = "TUTOR"
        else:
            role = "STUDENT"

    return {''',
    text,
    flags=re.DOTALL
)

with open(r'c:\dev\assignment-lms\apps\common\context_processors.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated CP")
