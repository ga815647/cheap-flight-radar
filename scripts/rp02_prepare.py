from pathlib import Path

path = Path('.github/workflows/rp02-bootstrap.yml')
text = path.read_text(encoding='utf-8')
replacements = {
    'module = "\\n".join(line[10:] if line.startswith("          ") else line for line in module.splitlines()) + "\\n"':
        'module = "\\n".join(module.splitlines()) + "\\n"',
    'tests = "\\n".join(line[10:] if line.startswith("          ") else line for line in tests.splitlines()) + "\\n"':
        'tests = "\\n".join(tests.splitlines()) + "\\n"',
}
for old, new in replacements.items():
    if old not in text:
        raise SystemExit(f'missing indentation normalization anchor: {old[:40]}')
    text = text.replace(old, new, 1)
path.write_text(text, encoding='utf-8')
print('RP-02 embedded generators normalized')
