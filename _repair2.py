"""一次性：修复 skills.py 中被误展开的 f-string（run 后自删）。"""
import io

p = 'backend/app/services/skills.py'
lines = io.open(p, encoding='utf-8', newline='').read().split('\n')
start = next(i for i, l in enumerate(lines) if '请为学生生成一份复习资料' in l)
end = start
while end < len(lines) and not lines[end].rstrip().endswith(('}],', '},"', '},')):
    end += 1
assert end < len(lines), 'end not found'
new_line = (
    '        {"role": "user", "content": "请为学生生成一份复习资料（" + focus + "）。'
    '\\n【薄弱点】\\n" + weaknesses + "\\n【近 " + str(days) + " 天错题】\\n" + (material or "（无）")}],'
)
lines[start:end + 1] = [new_line]
io.open(p, 'w', encoding='utf-8', newline='').write('\n'.join(lines))
print('repaired lines', start + 1, 'to', end + 1)
