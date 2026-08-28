with open(r'c:\dev\assignment-lms\apps\common\context_processors.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''    match = getattr(request, "resolver_match", None)
    
    if match and getattr(settings, "DEV_SKIP_AUTH", False):
        if match.namespace == "student":
            role = "STUDENT"
        elif match.namespace == "tutor":
            role = "TUTOR"

    return {'''

text = text.replace('    match = getattr(request, "resolver_match", None)\n    return {', replacement)
with open(r'c:\dev\assignment-lms\apps\common\context_processors.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated context processor")
