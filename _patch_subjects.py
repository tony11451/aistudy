"""一次性：Mindmap/WrongList/Mine 的学科列表改用 useSubjects（CRLF 容错，run 后自删）。"""
import io


def patch(path, edits):
    s = io.open(path, encoding='utf-8', newline='').read()
    for old, new in edits:
        if old not in s:
            print('SKIP (not found):', path, old[:50])
            continue
        s = s.replace(old, new)
    io.open(path, 'w', encoding='utf-8', newline='').write(s)
    print('patched', path)


patch('frontend/src/pages/WrongList.tsx', [
    ("import { SUBJECTS } from '../constants'\r\n", ''),
    ("import { SUBJECTS } from '../constants'\n", ''),
    ("export default function WrongList() {",
     "export default function WrongList() {\n  const subjects = useSubjects()"),
    ("{SUBJECTS.map((s) => (", "{subjects.map((s) => ("),
])

s = io.open('frontend/src/pages/WrongList.tsx', encoding='utf-8', newline='').read()
if 'useSubjects' in s and "from '../store'" in s:
    s = s.replace("import { useToast } from '../store'", "import { useToast, useSubjects } from '../store'")
    io.open('frontend/src/pages/WrongList.tsx', 'w', encoding='utf-8', newline='').write(s)

patch('frontend/src/pages/Mine.tsx', [
    ("import { SUBJECTS } from '../constants'\r\n", ''),
    ("import { SUBJECTS } from '../constants'\n", ''),
    ("import { useAuth, useToast } from '../store'", "import { useAuth, useToast, useSubjects } from '../store'"),
    ("function MethodsTab() {", "function MethodsTab() {\n  const subjects = useSubjects()"),
    ("function SelectFieldMini({ value, onChange }: { value: string; onChange: (v: string) => void }) {",
     "function SelectFieldMini({ value, onChange }: { value: string; onChange: (v: string) => void }) {\n  const subjects = useSubjects()"),
    ("setEditSubject(SUBJECTS[1])", "setEditSubject('数学')"),
    ("{SUBJECTS.map((s) => (", "{subjects.map((s) => ("),
    ("{SUBJECTS.map((s) => (", "{subjects.map((s) => ("),
])
