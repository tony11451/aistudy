import { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { libraryApi } from '../api'
import { Btn, CardView, Loading, Sheet, TopBar, Badge, IconBtn } from '../ui'
import { useAsync } from '../components'
import { ImageViewer } from '../viewer'
import { useToast } from '../store'
import { IconCamera, IconDelete, IconPlus, IconImage } from '../icons'

export default function BookDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const toast = useToast()
  const [viewImg, setViewImg] = useState<string | null>(null)
  const [page, setPage] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const { data, loading, reload } = useAsync(
    () => libraryApi.bookPages(Number(id)),
    [id],
  )

  const addPage = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy(true)
    try {
      for (const f of Array.from(files).slice(0, 12)) {
        await libraryApi.addPage(Number(id), f)
      }
      toast('页面已添加，文字提取可稍后批量进行')
      reload()
    } catch (e: any) {
      toast(e.message || '上传失败')
    } finally {
      setBusy(false)
    }
  }

  const book = data?.book
  const pages = (data?.pages || []).slice().sort((a: any, b: any) => a.page_no - b.page_no)

  return (
    <div className="page" style={{ paddingTop: 0 }}>
      <TopBar
        title={book?.name || '书本'}
        back={() => nav('/library')}
        right={
          <IconBtn icon={<IconPlus size={20} />} label="添加页面" onClick={() => fileRef.current?.click()} />
        }
      />
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
        multiple
        hidden
        onChange={(e) => {
          addPage(e.target.files)
          e.target.value = ''
        }}
      />

      <div className="row" style={{ flexWrap: 'wrap', gap: 6, margin: '10px 0' }}>
        <Badge tone="primary">{book?.kind === 'notebook' ? '笔记本' : '课本'}</Badge>
        {book?.subject && <Badge>{book.subject}</Badge>}
        <Badge>共 {pages.length} 页</Badge>
        <span className="spacer" />
        <Btn variant="tonal" sm disabled={busy} leadingIcon={<IconCamera size={15} />}
             onClick={() => fileRef.current?.click()}>
          拍照加页
        </Btn>
      </div>

      {loading && <Loading />}
      {!loading && !pages.length && (
        <CardView variant="outlined">
          <div className="muted" style={{ textAlign: 'center', lineHeight: 1.6 }}>
            还没有页面。拍照上传课本/笔记页面（自动识别页码与文字），<br />就像把这本书存进服务器。
          </div>
          <Btn variant="filled" block style={{ marginTop: 12 }} onClick={() => fileRef.current?.click()}>
            <IconImage size={16} /> 上传第一页
          </Btn>
        </CardView>
      )}

      {/* 电子书式页面列表 */}
      <div className="col">
        {pages.map((p: any) => (
          <CardView key={p.id} variant="filled" onClick={() => setPage(p)}>
            <div className="row">
              <Badge tone="primary">第 {p.page_no} 页</Badge>
              <span className="spacer" />
              <Badge>{p.ocr_status === 'done' ? '文字已提取' : p.ocr_status === 'pending' ? '待提取' : '—'}</Badge>
            </div>
            <div className="img-cell" style={{ aspectRatio: '4/3', marginTop: 8 }}>
              <img src={`/api/images/${p.image_path}`} alt="" />
            </div>
            {p.ocr_preview && <div className="caption clamp-2" style={{ marginTop: 6 }}>{p.ocr_preview}</div>}
          </CardView>
        ))}
      </div>

      <Sheet open={!!page} onClose={() => setPage(null)} title={page ? `第 ${page.page_no} 页` : ''}>
        {page && (
          <div className="col">
            <div className="img-cell" style={{ aspectRatio: '4/3' }}
                 onClick={() => setViewImg(`/api/images/${page.image_path}`)}>
              <img src={`/api/images/${page.image_path}`} alt="" />
            </div>
            <div className="caption">点击图片可放大 · 双指缩放</div>
            {page.ocr_preview && (
              <div>
                <div className="caption">本页文字</div>
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{page.ocr_preview}</div>
              </div>
            )}
            <Btn variant="tonal" block onClick={() => libraryApi.download(Number(id), page.image_path)}>
              下载本页
            </Btn>
          </div>
        )}
      </Sheet>

      {viewImg && <ImageViewer src={viewImg} onClose={() => setViewImg(null)} />}
    </div>
  )
}
