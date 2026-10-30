"""一次性：修复 skills.py 行尾括号（run 后自删）。"""
import io

p = 'backend/app/services/skills.py'
lines = io.open(p, encoding='utf-8', newline='').read().split('\n')
i = next(i for i, l in enumerate(lines) if '请为学生生成一份复习资料' in l)
assert lines[i].rstrip().endswith('}],'), repr(lines[i][-30:])
lines[i] = lines[i].replace('}],', '},')
io.open(p, 'w', encoding='utf-8', newline='').write('\n'.join(lines))
print('fixed line', i + 1)
