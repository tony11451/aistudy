/** 裁切器：框选 + 旋转 + 透视校正（自动识别纸张四角，可手动拖角微调） */
import { useEffect, useRef, useState } from 'react'
import { Btn, IconBtn } from './ui'
import { IconCheck, IconClose, IconRotate, IconCrop, IconSparkle } from './icons'

type Pt = { x: number; y: number }

interface Props {
  file: File
  onConfirm: (file: File) => void
  onCancel: () => void
}

/** Otsu 阈值 + 极值点法粗定位纸张四角 */
function detectQuad(canvas: HTMLCanvasElement): Pt[] {
  const w = canvas.width
  const h = canvas.height
  const ctx = canvas.getContext('2d')!
  const data = ctx.getImageData(0, 0, w, h).data
  // 亮度直方图 → Otsu
  const hist = new Array(256).fill(0)
  const lum = new Uint8Array(w * h)
  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    const v = (data[i] * 0.299 + data[i + 1] * 0.587 + data[i + 2] * 0.114) | 0
    lum[p] = v
    hist[v]++
  }
  const total = w * h
  let sum = 0
  for (let t = 0; t < 256; t++) sum += t * hist[t]
  let sumB = 0
  let wB = 0
  let best = 0
  let bestVar = -1
  for (let t = 0; t < 256; t++) {
    wB += hist[t]
    if (!wB) continue
    const wF = total - wB
    if (!wF) break
    sumB += t * hist[t]
    const mB = sumB / wB
    const mF = (sum - sumB) / wF
    const between = wB * wF * (mB - mF) ** 2
    if (between > bestVar) {
      bestVar = between
      best = t
    }
  }
  // 亮区（纸张）极值点
  let tl = { x: 0, y: 0, v: Infinity }
  let br = { x: 0, y: 0, v: -Infinity }
  let tr = { x: 0, y: 0, v: -Infinity }
  let bl = { x: 0, y: 0, v: Infinity }
  let count = 0
  for (let y = 0; y < h; y += 2) {
    for (let x = 0; x < w; x += 2) {
      if (lum[y * w + x] > best) {
        count++
        const s = x + y
        const d = x - y
        if (s < tl.v) tl = { x, y, v: s }
        if (s > br.v) br = { x, y, v: s }
        if (d > tr.v) tr = { x, y, v: d }
        if (d < bl.v) bl = { x, y, v: d }
      }
    }
  }
  if (count < (w * h) / 400) {
    // 亮区太小，退化为全图 8% 内缩
    const m = 0.08
    return [
      { x: w * m, y: h * m },
      { x: w * (1 - m), y: h * m },
      { x: w * (1 - m), y: h * (1 - m) },
      { x: w * m, y: h * (1 - m) },
    ]
  }
  return [
    { x: tl.x, y: tl.y },
    { x: tr.x, y: tr.y },
    { x: br.x, y: br.y },
    { x: bl.x, y: bl.y },
  ]
}

/** 4 点透视变换（逆映射 + 双线性采样）输出矫正图 */
function warpPerspective(
  src: HTMLCanvasElement,
  quad: Pt[],
  maxSide = 1600,
): HTMLCanvasElement {
  const [tl, tr, br, bl] = quad
  const widthA = Math.hypot(br.x - bl.x, br.y - bl.y)
  const widthB = Math.hypot(tr.x - tl.x, tr.y - tl.y)
  const heightA = Math.hypot(tr.x - br.x, tr.y - br.y)
  const heightB = Math.hypot(tl.x - bl.x, tl.y - bl.y)
  let dw = Math.max(widthA, widthB)
  let dh = Math.max(heightA, heightB)
  const scale = Math.min(1, maxSide / Math.max(dw, dh))
  dw = Math.round(dw * scale)
  dh = Math.round(dh * scale)

  const dst = document.createElement('canvas')
  dst.width = dw
  dst.height = dh
  const dctx = dst.getContext('2d')!
  const out = dctx.createImageData(dw, dh)

  const sctx = src.getContext('2d')!
  const sdata = sctx.getImageData(0, 0, src.width, src.height).data

  // 目标矩形 (0,0)(dw,0)(dw,dh)(0,dh) → 源 quad 的单应矩阵（8 参数）
  const [x0, y0, x1, y1, x2, y2, x3, y3] = [tl.x, tl.y, tr.x, tr.y, br.x, br.y, bl.x, bl.y]
  const A = [
    [0, 0, 1, 0, 0, 0, 0, 0],
    [dw, 0, 1, 0, 0, 0, -dw * x1, 0],
    [dw, dh, 1, 0, 0, 0, -dw * x2, -dh * x2],
    [0, dh, 1, 0, 0, 0, 0, -dh * x3],
    [0, 0, 0, 0, 0, 1, 0, 0],
    [dw, 0, 0, 0, 0, 1, -dw * y1, 0],
    [dw, dh, 0, 0, 0, 1, -dw * y2, -dh * y2],
    [0, dh, 0, 0, 0, 1, 0, -dh * y3],
  ]
  const B = [x0, x1, x2, x3, y0, y1, y2, y3]
  const h = solveLinear(A, B) // [a,b,c,d,e,f,g,h]

  for (let y = 0; y < dh; y++) {
    for (let x = 0; x < dw; x++) {
      const denom = h[6] * x + h[7] * y + 1
      const sx = (h[0] * x + h[1] * y + h[2]) / denom
      const sy = (h[3] * x + h[4] * y + h[5]) / denom
      const ix = Math.min(src.width - 2, Math.max(0, sx))
      const iy = Math.min(src.height - 2, Math.max(0, sy))
      const fx = ix - Math.floor(ix)
      const fy = iy - Math.floor(iy)
      const x0i = Math.floor(ix)
      const y0i = Math.floor(iy)
      const idx = (px: number, py: number) => (py * src.width + px) * 4
      const p00 = idx(x0i, y0i)
      const p10 = idx(x0i + 1, y0i)
      const p01 = idx(x0i, y0i + 1)
      const p11 = idx(x0i + 1, y0i + 1)
      const o = (y * dw + x) * 4
      for (let c = 0; c < 3; c++) {
        out.data[o + c] =
          sdata[p00 + c] * (1 - fx) * (1 - fy) +
          sdata[p10 + c] * fx * (1 - fy) +
          sdata[p01 + c] * (1 - fx) * fy +
          sdata[p11 + c] * fx * fy
      }
      out.data[o + 3] = 255
    }
  }
  dctx.putImageData(out, 0, 0)
  return dst
}

function solveLinear(A: number[][], B: number[]): number[] {
  const n = B.length
  const M = A.map((row, i) => [...row, B[i]])
  for (let col = 0; col < n; col++) {
    let pivot = col
    for (let r = col + 1; r < n; r++) {
      if (Math.abs(M[r][col]) > Math.abs(M[pivot][col])) pivot = r
    }
    ;[M[col], M[pivot]] = [M[pivot], M[col]]
    const div = M[col][col] || 1e-9
    for (let c = col; c <= n; c++) M[col][c] /= div
    for (let r = 0; r < n; r++) {
      if (r === col) continue
      const factor = M[r][col]
      for (let c = col; c <= n; c++) M[r][c] -= factor * M[col][c]
    }
  }
  return M.map((row) => row[n])
}

export function CropModal({ file, onConfirm, onCancel }: Props) {
  const stageRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [quad, setQuad] = useState<Pt[]>([])
  const [rotation, setRotation] = useState(0)
  const [busy, setBusy] = useState(false)
  const [mode, setMode] = useState<'crop' | 'perspective'>('crop')
  const state = useRef({ img: null as HTMLImageElement | null, dragging: -1 })

  const draw = (rot: number, q: Pt[]) => {
    const canvas = canvasRef.current
    const img = state.current.img
    if (!canvas || !img) return
    const swap = rot % 180 !== 0
    canvas.width = swap ? img.height : img.width
    canvas.height = swap ? img.width : img.height
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.save()
    ctx.translate(canvas.width / 2, canvas.height / 2)
    ctx.rotate((rot * Math.PI) / 180)
    ctx.drawImage(img, -img.width / 2, -img.height / 2)
    ctx.restore()
    if (q.length) {
      ctx.strokeStyle = 'rgba(79,70,229,0.95)'
      ctx.lineWidth = Math.max(2, canvas.width / 400)
      ctx.beginPath()
      q.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)))
      ctx.closePath()
      ctx.stroke()
      ctx.fillStyle = 'rgba(79,70,229,0.18)'
      ctx.fill()
    }
  }

  useEffect(() => {
    const img = new Image()
    img.onload = () => {
      state.current.img = img
      const canvas = canvasRef.current!
      canvas.width = img.width
      canvas.height = img.height
      const q = detectQuad(canvas)
      setQuad(q)
      draw(0, q)
      // 缩放显示
      const stage = stageRef.current!
      const scale = Math.min(1, stage.clientWidth / img.width, (window.innerHeight * 0.62) / img.height)
      canvas.style.width = `${img.width * scale}px`
      canvas.style.height = `${img.height * scale}px`
      canvas.style.position = 'relative'
    }
    img.src = URL.createObjectURL(file)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file])

  useEffect(() => {
    draw(rotation, quad)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rotation, quad])

  const posOf = (e: React.PointerEvent | PointerEvent): Pt => {
    const canvas = canvasRef.current!
    const rect = canvas.getBoundingClientRect()
    return {
      x: ((e.clientX - rect.left) / rect.width) * canvas.width,
      y: ((e.clientY - rect.top) / rect.height) * canvas.height,
    }
  }

  const onDown = (e: React.PointerEvent) => {
    const p = posOf(e)
    let best = -1
    let bestD = 60
    quad.forEach((q, i) => {
      const d = Math.hypot(q.x - p.x, q.y - p.y)
      if (d < bestD) {
        bestD = d
        best = i
      }
    })
    state.current.dragging = best
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }

  const onMove = (e: React.PointerEvent) => {
    const idx = state.current.dragging
    if (idx < 0) return
    const p = posOf(e)
    setQuad((q) => q.map((pt, i) => (i === idx ? p : pt)))
  }

  const onUp = () => {
    state.current.dragging = -1
  }

  const autoDetect = () => {
    const canvas = canvasRef.current!
    setQuad(detectQuad(canvas))
  }

  const rotate = () => {
    const next = (rotation + 90) % 360
    setRotation(next)
    const canvas = canvasRef.current!
    const img = state.current.img!
    const swap = next % 180 !== 0
    canvas.width = swap ? img.height : img.width
    canvas.height = swap ? img.width : img.height
    const q = detectQuad(canvas)
    setQuad(q)
  }

  const confirm = async () => {
    setBusy(true)
    try {
      const canvas = canvasRef.current!
      let srcCanvas = canvas
      if (mode === 'perspective' && quad.length === 4) {
        srcCanvas = warpPerspective(canvas, quad)
      } else {
        // 普通框选裁切：取 quad 外接矩形
        const xs = quad.map((p) => p.x)
        const ys = quad.map((p) => p.y)
        const x = Math.max(0, Math.min(...xs))
        const y = Math.max(0, Math.min(...ys))
        const w = Math.min(canvas.width - x, Math.max(...xs) - x)
        const h = Math.min(canvas.height - y, Math.max(...ys) - y)
        const cropped = document.createElement('canvas')
        cropped.width = Math.max(2, w)
        cropped.height = Math.max(2, h)
        cropped.getContext('2d')!.drawImage(canvas, x, y, w, h, 0, 0, w, h)
        srcCanvas = cropped
      }
      const blob = await new Promise<Blob | null>((r) => srcCanvas.toBlob(r, 'image/jpeg', 0.9))
      if (blob) {
        onConfirm(new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' }))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="viewer-overlay" style={{ flexDirection: 'column', padding: 16 }}>
      <div className="row" style={{ width: '100%', maxWidth: 560, color: '#fff', marginBottom: 10 }}>
        <div className="title-strong" style={{ flex: 1 }}>裁切题目</div>
        <IconBtn icon={<IconClose size={20} />} onClick={onCancel} label="取消" />
      </div>

      <div className="crop-stage" ref={stageRef} style={{ maxWidth: 560 }}>
        <canvas
          ref={canvasRef}
          className="crop-canvas"
          style={{ cursor: 'crosshair' }}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          onPointerCancel={onUp}
        />
        {quad.map((p, i) => {
          const canvas = canvasRef.current
          if (!canvas) return null
          const rect = canvas.getBoundingClientRect()
          const stageRect = stageRef.current!.getBoundingClientRect()
          const left = rect.left - stageRect.left + (p.x / canvas.width) * rect.width
          const top = rect.top - stageRect.top + (p.y / canvas.height) * rect.height
          return (
            <div
              key={i}
              className="crop-handle"
              style={{ left, top }}
              onPointerDown={(e) => {
                e.stopPropagation()
                state.current.dragging = i
                ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
              }}
              onPointerMove={(e) => {
                if (state.current.dragging !== i) return
                e.stopPropagation()
                const canvas2 = canvasRef.current!
                const rect2 = canvas2.getBoundingClientRect()
                const p2 = {
                  x: ((e.clientX - rect2.left) / rect2.width) * canvas2.width,
                  y: ((e.clientY - rect2.top) / rect2.height) * canvas2.height,
                }
                setQuad((q) => q.map((pt, j) => (j === i ? p2 : pt)))
              }}
              onPointerUp={() => (state.current.dragging = -1)}
            />
          )
        })}
      </div>

      <div className="row" style={{ width: '100%', maxWidth: 560, marginTop: 14, gap: 8, flexWrap: 'wrap' }}>
        <Btn variant="tonal" sm onClick={rotate} leadingIcon={<IconRotate size={15} />}>
          旋转
        </Btn>
        <Btn variant="tonal" sm onClick={autoDetect} leadingIcon={<IconSparkle size={15} />}>
          自动识别边框
        </Btn>
        <Btn
          variant={mode === 'perspective' ? 'filled' : 'outlined'}
          sm
          onClick={() => setMode(mode === 'perspective' ? 'crop' : 'perspective')}
          leadingIcon={<IconCrop size={15} />}
        >
          {mode === 'perspective' ? '透视拉正：开' : '透视拉正：关'}
        </Btn>
        <span className="spacer" />
        <Btn variant="text" sm onClick={onCancel} style={{ color: '#fff' }}>
          取消
        </Btn>
        <Btn variant="filled" sm onClick={confirm} disabled={busy} leadingIcon={<IconCheck size={15} />}>
          {busy ? '处理中…' : '确认'}
        </Btn>
      </div>
      <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: 12, marginTop: 8, maxWidth: 560 }}>
        拖动四角对准题目边缘；开启「透视拉正」可将拍歪的纸张矫正为正视图。
      </p>
    </div>
  )
}
