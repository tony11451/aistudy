import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, libraryApi } from '../api'
import {
  Btn,
  CardView,
  ChipFilter,
  ChipRow,
  DialogBox,
  Empty,
  Field,
  Loading,
  Sheet,
  TopBar,
  Badge,
  IconBtn,
} from '../ui'
import { useAsync } from '../components'
import { ImageViewer } from '../viewer'
import { useToast, useSubjects } from '../store'
import {
  IconBook,
  IconCamera,
  IconCheck,
  IconClose,
  IconDelete,
  IconImage,
  IconPlus,
  IconSearch,
  IconSparkle,
  IconZoomIn,
} from '../icons'

type KindFilter = '' | 'image' | 'wrong_question' | 'text' | 'attachment' | 'review'

export default function Library() {
  const nav = useNavigate()
  const toast = useToast()
  const subjects = useSubjects()
  const [subject, setSubject] = useState('')
  const [kind, setKind] = useState<KindFilter>('')
  const [q, setQ] = useState('')
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState('')
  const [viewImg, setViewImg] = useState<string | null>(null)
  const [item, setItem] = useState<any>(null)
  const [showUpload, setShowUpload] = useState<'' | 'image' | 'attachment' | 'text'>('')
  const [showBook, setShowBook] = useState<'textbook' | 'notebook' | ''>('')
  const [newBook, setNewBook] = useState({ name: '', subject: '' })
  const [newBoard, setNewBoard] = useState({ name: '', parent: 0, subject: '' })
  const [showBoard, setShowBoard] = useState(false)
  const [uploadSubject, setUploadSubject] = useState('')
  const [uploadBoard, setUploadBoard] = useState(0)
  const [textForm, setTextForm] = useState({ title: '', content: '', board_id: 0 })
  const fileRef = useRef<HTMLInputElement>(null)
  const albumRef = useRef<HTMLInputElement>(null)
  const [pendingKind, setPendingKind] = useState<'image' | 'attachment'>('image')

  const { data: ov, loading, reload } = useAsync(
    () => libraryApi.overview(subject),
    [subject],
  )
  const { data: boards } = useAsync(() => libraryApi.boards(subject), [subject])
  const { data: items, loading: itemsLoading, reload: reloadItems } = useAsync(
    () =>
      libraryApi.search({
        q: query,
        subject,
        kind,
        limit: 60,
      }),
    [query, subject, kind],
  )

  const openUpload = (k: 'image' | 'attachment') => {
    setPendingKind(k)
    setUploadSubject(subject)
    fileRef.current?.click()
  }

  const doUpload = async (files: FileList | null) => {
    if (!files?.length) return
    setBusy('upload')
    try {
      await libraryApi.uploadItems(Array.from(files).slice(0, 12), {
        subject: uploadSubject,
        kind: pendingKind,
        board_id: uploadBoard || undefined,
      })
      toast(`已入库 ${files.length} 个文件`)
      reload()
      reloadItems()
    } catch (e: any) {
      toast(e.message || '上传失败')
    } finally {
      setBusy('')
    }
  }

  const runOcr = async () => {
    setBusy('ocr')
    try {
      const res = await libraryApi.runOcr()
      toast(`OCR 完成：${res.done} 条成功，${res.failed} 条失败`)
      reloadItems()
    } catch (e: any) {
      toast(e.message || 'OCR 失败（需要配置视觉模型）')
    } finally {
      setBusy('')
    }
  }

  const boardTree = (boards || []).filter((b: any) => !b.parent_id)
  const childBoards = (pid: number) => (boards || []).filter((b: any) => b.parent_id === pid)

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 10 }}>
        <div className="topbar-title" style={{ fontSize: '1.35rem' }}>档案库</div>
        <Btn variant="text" sm disabled={busy === 'ocr'} onClick={runOcr}>
          {busy === 'ocr' ? 'OCR 中…' : '文字提取'}
        </Btn>
        <Btn variant="text" sm disabled={busy === 'nightly'} onClick={async () => {
          setBusy('nightly')
          try {
            const res = await api.post<any>('/api/library/nightly/run', {})
            toast(`整理完成：OCR ${res.result?.ocr?.done || 0} 条${res.result?.report ? '，已生成简报' : ''}`)
            reload()
            reloadItems()
          } catch (e: any) {
            toast(e.message || '整理失败')
          } finally {
            setBusy('')
          }
        }}>
          {busy === 'nightly' ? '整理中…' : '夜间整理'}
        </Btn>
        <Btn variant="tonal" sm disabled={busy === 'review'} onClick={async () => {
          const focus = prompt('复习资料主题（如：期中复习 / 函数专题）', '期中复习')
          if (focus === null) return
          setBusy('review')
          try {
            await api.post('/api/library/review/generate', { subject, focus, days: 14 })
            toast('复习资料已生成，见下方资料库')
            reloadItems()
          } catch (e: any) {
            toast(e.message || '生成失败')
          } finally {
            setBusy('')
          }
        }}>
          {busy === 'review' ? '生成中…' : '复习资料'}
        </Btn>
      </div>

      {/* 搜索 + 筛选 */}
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault()
          setQuery(q.trim())
        }}
      >
        <div style={{ flex: 1 }}>
          <Field label="" value={q} onChange={setQ} placeholder="搜索档案（标题/正文/图片文字）" />
        </div>
        <Btn variant="filled" sm type="submit" leadingIcon={<IconSearch size={16} />}>
          搜索
        </Btn>
      </form>
      <ChipRow>
        <ChipFilter label="全部学科" selected={!subject} onClick={() => setSubject('')} />
        {subjects.map((s) => (
          <ChipFilter key={s} label={s} selected={subject === s} onClick={() => setSubject(s)} />
        ))}
      </ChipRow>
      <ChipRow>
        {(
          [
            ['', '全部'],
            ['image', '图片'],
            ['wrong_question', '错题图'],
            ['text', '文字'],
            ['attachment', '附件'],
            ['review', '复习资料'],
          ] as [KindFilter, string][]
        ).map(([k, label]) => (
          <ChipFilter key={label} label={label} selected={kind === k} onClick={() => setKind(k)} />
        ))}
      </ChipRow>

      {/* 快捷上传 */}
      <div className="row" style={{ gap: 8, margin: '10px 0', flexWrap: 'wrap' }}>
        <Btn variant="filled" sm leadingIcon={<IconCamera size={16} />} onClick={() => openUpload('image')}>
          拍照入库
        </Btn>
        <Btn variant="tonal" sm leadingIcon={<IconImage size={16} />} onClick={() => {
          setPendingKind('image')
          setUploadSubject(subject)
          albumRef.current?.click()
        }}>
          相册
        </Btn>
        <Btn variant="tonal" sm leadingIcon={<IconSparkle size={16} />} onClick={() => setShowUpload('text')}>
          文字录入
        </Btn>
        <Btn variant="outlined" sm leadingIcon={<IconPlus size={16} />} onClick={() => openUpload('attachment')}>
          附件
        </Btn>
        <input
          ref={albumRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            doUpload(e.target.files)
            e.target.value = ''
          }}
        />
        <input
          ref={fileRef}
          type="file"
          accept={pendingKind === 'image' ? 'image/*' : '.pdf,.docx,.txt,.md,.csv,.json,image/*'}
          capture={pendingKind === 'image' ? 'environment' : undefined}
          multiple
          hidden
          onChange={(e) => {
            doUpload(e.target.files)
            e.target.value = ''
          }}
        />
      </div>

      {loading && <Loading />}

      {/* 书本区 / 笔记本 */}
      {ov && (
        <>
          <div className="row" style={{ marginTop: 8 }}>
            <div className="section-title" style={{ flex: 1 }}>📚 书本区</div>
            <Btn variant="tonal" sm onClick={() => setShowBook('textbook')}>
              <IconPlus size={15} /> 添加书本
            </Btn>
          </div>
          <div className="row-wrap">
            {ov.books.filter((b: any) => b.kind === 'textbook').map((b: any) => (
              <CardView key={b.id} variant="elevated" onClick={() => nav(`/library/book/${b.id}`)}
                        style={{ width: 140, padding: 10, textAlign: 'center' }}>
                <div style={{ fontSize: 32 }}>{b.cover_image ? '📖' : '📘'}</div>
                <div className="text-ellipsis" style={{ fontWeight: 650 }}>{b.name}</div>
                <div className="caption">{b.subject || '综合'}</div>
              </CardView>
            ))}
            {!ov.books.filter((b: any) => b.kind === 'textbook').length && (
              <div className="caption" style={{ padding: 8 }}>
                还没有书本。拍课本入库后 AI 可当知识库用（政治/历史问答可直接翻书）
              </div>
            )}
          </div>

          <div className="row" style={{ marginTop: 8 }}>
            <div className="section-title" style={{ flex: 1 }}>📓 笔记本</div>
            <Btn variant="tonal" sm onClick={() => setShowBook('notebook')}>
              <IconPlus size={15} /> 添加
            </Btn>
          </div>
          <div className="row-wrap">
            {ov.books.filter((b: any) => b.kind === 'notebook').map((b: any) => (
              <CardView key={b.id} variant="outlined" onClick={() => nav(`/library/book/${b.id}`)}
                        style={{ width: 140, padding: 10, textAlign: 'center' }}>
                <div style={{ fontSize: 32 }}>📓</div>
                <div className="text-ellipsis" style={{ fontWeight: 650 }}>{b.name}</div>
              </CardView>
            ))}
          </div>

          {/* 板块区 */}
          <div className="row" style={{ marginTop: 8 }}>
            <div className="section-title" style={{ flex: 1 }}>🗂 板块区</div>
            <Btn variant="tonal" sm onClick={() => setShowBoard(true)}>
              <IconPlus size={15} /> 新建板块
            </Btn>
          </div>
          <div className="col">
            {boardTree.map((b: any) => (
              <CardView key={b.id} variant="filled">
                <div className="row">
                  <IconBook size={18} />
                  <div className="title-strong" style={{ flex: 1 }}>{b.name}</div>
                  <Badge>{b.subject || '综合'}</Badge>
                  <Badge>{b.item_count} 项</Badge>
                </div>
                {childBoards(b.id).length > 0 && (
                  <div className="row-wrap" style={{ marginTop: 8 }}>
                    {childBoards(b.id).map((c: any) => (
                      <ChipFilter key={c.id} label={`${c.name}（${c.item_count}）`}
                                  onClick={() => setQuery(c.name)} />
                    ))}
                  </div>
                )}
                <div className="row" style={{ marginTop: 8, gap: 6 }}>
                  <Btn variant="text" sm onClick={async () => {
                    await libraryApi.boardTemplates(b.id)
                    toast('已生成分板块：题目版/答案版/解析版/知识点版/订正版')
                    reload()
                  }}>
                    生成分板块
                  </Btn>
                  <Btn variant="text" sm onClick={() => {
                    setUploadBoard(b.id)
                    setPendingKind('image')
                    toast('选择要加入该板块的文件')
                    fileRef.current?.click()
                  }}>
                    加入内容
                  </Btn>
                  <Btn variant="text" sm onClick={async () => {
                    if (!confirm(`删除板块「${b.name}」？内容会回到图片库`)) return
                    await libraryApi.deleteBoard(b.id)
                    reload()
                  }}>
                    删除
                  </Btn>
                </div>
              </CardView>
            ))}
            {!boardTree.length && (
              <div className="caption" style={{ padding: 8 }}>
                板块用来组织一次作业/任务（如「第一次物理作业 → 题目版/答案版」）
              </div>
            )}
          </div>
        </>
      )}

      {/* 图片库 / 附件 / 其他：搜索结果列表 */}
      <div className="row" style={{ marginTop: 8 }}>
        <div className="section-title" style={{ flex: 1 }}>
          {query ? `搜索结果（${items?.total || 0}）` : '🗂 资料库（图片库 / 附件 / 文字）'}
        </div>
      </div>
      {itemsLoading && <Loading />}
      {!itemsLoading && !(items?.items || []).length && (
        <Empty icon="🗂" title="暂无资料" desc="拍照上传错题/作业/课本，或手动录入文字" />
      )}
      <div className="col">
        {(items?.items || []).map((it: any) => (
          <CardView key={it.id} variant="filled" onClick={async () => {
            const full = await libraryApi.getItem(it.id)
            setItem(full)
          }}>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              <Badge tone="primary">{it.kind === 'wrong_question' ? '错题图' : it.kind === 'attachment' ? '附件' : it.kind === 'review' ? '复习资料' : it.kind === 'text' ? '文字' : '图片'}</Badge>
              {it.subject && <Badge>{it.subject}</Badge>}
              {it.page_no ? <Badge>第 {it.page_no} 页</Badge> : null}
              <span className="spacer" />
              <span className="caption">{(it.created_at || '').slice(0, 10)}</span>
            </div>
            <div className="text-ellipsis" style={{ fontWeight: 600, margin: '6px 0' }}>{it.title}</div>
            {(it.ocr_preview || it.content_preview) && (
              <div className="caption clamp-2">{it.ocr_preview || it.content_preview}</div>
            )}
          </CardView>
        ))}
      </div>

      {/* 条目详情 */}
      <Sheet open={!!item} onClose={() => setItem(null)} title={item?.title}>
        {item && (
          <div className="col">
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              <Badge tone="primary">{item.kind}</Badge>
              {item.subject && <Badge>{item.subject}</Badge>}
              {item.page_no ? <Badge>第 {item.page_no} 页</Badge> : null}
              <Badge>{item.source}</Badge>
            </div>
            {item.file_path && item.file_type !== 'image/jpeg' ? (
              <div className="caption">📎 {item.file_name}（{item.file_type}）</div>
            ) : null}
            {item.file_path && (item.kind === 'image' || item.kind === 'wrong_question' || item.kind === 'review') && (
              <div className="img-cell" style={{ aspectRatio: '4/3' }}
                   onClick={() => setViewImg(`/api/images/${item.file_path}`)}>
                <img src={`/api/images/${item.file_path}`} alt="" />
              </div>
            )}
            {item.content && (
              <div>
                <div className="caption">内容</div>
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{item.content}</div>
              </div>
            )}
            {item.ocr_text && (
              <div>
                <div className="caption">图片文字（OCR）</div>
                <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{item.ocr_text}</div>
              </div>
            )}
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              {item.file_path && (
                <Btn variant="tonal" sm onClick={() => libraryApi.download(item.id, item.file_name || 'file')}>
                  下载
                </Btn>
              )}
              <Btn variant="tonal" sm onClick={async () => {
                await libraryApi.addBookmark({
                  target_type: 'library_item',
                  target_id: item.id,
                  label: item.title,
                })
                toast('已加书签')
              }}>
                加书签
              </Btn>
              <Btn variant="outlined" sm onClick={async () => {
                const boardName = prompt('移动到哪个板块？（输入板块名，留空移出到图片库）')
                if (boardName === null) return
                const target = (boards || []).find((b: any) => b.name === boardName)
                await libraryApi.moveItem(item.id, { board_id: target ? target.id : 0 })
                toast('已移动')
                setItem(null)
                reloadItems()
              }}>
                移动
              </Btn>
              <Btn variant="danger" sm onClick={async () => {
                if (!confirm('删除该条目？')) return
                await libraryApi.deleteItem(item.id)
                setItem(null)
                toast('已删除')
                reload()
                reloadItems()
              }}>
                <IconDelete size={15} /> 删除
              </Btn>
            </div>
          </div>
        )}
      </Sheet>

      {/* 新建书本 */}
      <DialogBox open={!!showBook} onClose={() => setShowBook('')} title="添加书本 / 笔记本">
        <div className="col">
          <Field label="名称" value={newBook.name} onChange={(v) => setNewBook({ ...newBook, name: v })}
                 placeholder="如 物理八年级上·人教版" />
          <Field label="学科（可留空）" value={newBook.subject} onChange={(v) => setNewBook({ ...newBook, subject: v })} />
          <div className="row">
            <Btn variant="text" onClick={() => setShowBook('')}>取消</Btn>
            <span className="spacer" />
            <Btn variant="filled" onClick={async () => {
              if (!newBook.name.trim()) return toast('请输入名称')
              await libraryApi.createBook({
                name: newBook.name,
                subject: newBook.subject,
                kind: showBook || 'textbook',
              })
              setNewBook({ name: '', subject: '' })
              setShowBook('')
              toast('已创建，点进书本可拍照上传页面')
              reload()
            }}>
              创建
            </Btn>
          </div>
        </div>
      </DialogBox>

      {/* 新建板块 */}
      <DialogBox open={showBoard} onClose={() => setShowBoard(false)} title="新建板块">
        <div className="col">
          <Field label="板块名（大板块）" value={newBoard.name} onChange={(v) => setNewBoard({ ...newBoard, name: v })}
                 placeholder="如 第一次物理作业" />
          <Field label="学科（可留空）" value={newBoard.subject} onChange={(v) => setNewBoard({ ...newBoard, subject: v })} />
          <div className="row">
            <Btn variant="text" onClick={() => setShowBoard(false)}>取消</Btn>
            <span className="spacer" />
            <Btn variant="filled" onClick={async () => {
              if (!newBoard.name.trim()) return toast('请输入板块名')
              await libraryApi.createBoard({ name: newBoard.name, subject: newBoard.subject })
              setNewBoard({ name: '', parent: 0, subject: '' })
              setShowBoard(false)
              toast('已创建，可点「生成分板块」快速建题目版/答案版')
              reload()
            }}>
              创建
            </Btn>
          </div>
        </div>
      </DialogBox>

      {/* 文字录入 */}
      <Sheet open={showUpload === 'text'} onClose={() => setShowUpload('')} title="录入文字资料">
        <div className="col">
          <Field label="标题" value={textForm.title} onChange={(v) => setTextForm({ ...textForm, title: v })} />
          <Field label="内容" value={textForm.content} onChange={(v) => setTextForm({ ...textForm, content: v })}
                 multiline rows={6} />
          <Btn variant="filled" block onClick={async () => {
            if (!textForm.content.trim()) return toast('请输入内容')
            await libraryApi.createTextItem({
              title: textForm.title || '文字笔记',
              content: textForm.content,
              subject,
              board_id: textForm.board_id || undefined,
            })
            setTextForm({ title: '', content: '', board_id: 0 })
            setShowUpload('')
            toast('已保存')
            reload()
            reloadItems()
          }}>
            保存
          </Btn>
        </div>
      </Sheet>

      {viewImg && (
        <ImageViewer
          src={viewImg}
          onClose={() => setViewImg(null)}
          onDownload={() => item && libraryApi.download(item.id, item.file_name || 'file')}
          onBookmark={async () => {
            await libraryApi.addBookmark({
              target_type: 'library_item',
              target_id: item?.id || 0,
              label: item?.title || '资料图片',
            })
            toast('已加书签')
          }}
        />
      )}
    </div>
  )
}
