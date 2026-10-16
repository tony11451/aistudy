/** 渲染冒烟：SSR 输出验证 Material3Provider 属性与组件类名（构建时临时用，可删除） */
;(globalThis as any).localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
}
import { renderToStaticMarkup } from 'react-dom/server'
import { ThemeProvider, Btn, CardView, ChipFilter, TopBar } from './ui'

const html = renderToStaticMarkup(
  <ThemeProvider>
    <TopBar title="测试" />
    <CardView variant="filled">
      <Btn variant="filled">确定</Btn>
      <ChipFilter label="数学" selected />
    </CardView>
  </ThemeProvider>,
)

const checks: [string, boolean][] = [
  ['data-m3e-color-mode 属性', html.includes('data-m3e-color-mode')],
  ['m3e-button 组件类', html.includes('m3e-button')],
  ['m3e-card 组件类', html.includes('m3e-card')],
  ['m3e-chip 组件类', html.includes('m3e-chip')],
  ['m3e-app-root 容器', html.includes('m3e-app-root')],
  ['chip 选中态', html.includes('data-m3e-selected')],
]
let failed = 0
for (const [name, ok] of checks) {
  console.log(ok ? 'PASS' : 'FAIL', name)
  if (!ok) failed++
}
console.log(failed ? `=== ${checks.length - failed}/${checks.length} passed ===` : `=== ${checks.length}/${checks.length} passed ===`)
;(globalThis as any).process?.exit(failed ? 1 : 0)
