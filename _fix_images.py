"""批量修复：①全部图片入口补「相册」选择 ②ImageViewer 接线书签/下载。"""
import io

def patch(path, edits, required=True):
    s = io.open(path, encoding='utf-8', newline='').read()
    for old, new in edits:
        if old not in s:
            if required:
                raise AssertionError((path, old[:70]))
            continue
        s = s.replace(old, new)
    io.open(path, 'w', encoding='utf-8', newline='').write(s)
    print('patched', path.split('/')[-1])


# ============ 1) ChatRoom：相册按钮 + 双输入 ============
patch('frontend/src/pages/ChatRoom.tsx', [
    # 双 ref
    ("  const fileRef = useRef<HTMLInputElement>(null)",
     "  const fileRef = useRef<HTMLInputElement>(null)\n  const albumRef = useRef<HTMLInputElement>(null)"),
    # 输入行加相册按钮 + 第二个 input
    ('          <IconBtn icon={<IconCamera size={20} />} label="拍照提问" onClick={() => fileRef.current?.click()} />',
     '          <IconBtn icon={<IconCamera size={20} />} label="拍照提问" onClick={() => fileRef.current?.click()} />\n'
     '          <IconBtn icon={<IconImage size={20} />} label="相册选图" onClick={() => albumRef.current?.click()} />'),
    # 相册 input（无 capture），复用同一 handler
    ("          <input\n            ref={fileRef}\n            type=\"file\"\n            accept=\"image/*\"\n            capture=\"environment\"\n            multiple\n            hidden",
     "          <input\n            ref={albumRef}\n            type=\"file\"\n            accept=\"image/*\"\n            multiple\n            hidden\n            onChange={async (e) => {\n              if (!e.target.files) return\n              const arr = await Promise.all(\n                Array.from(e.target.files).slice(0, 9).map((f) => compressImage(f)),\n              )\n              setImages((prev) => [...prev, ...arr].slice(0, 9))\n              e.target.value = ''\n            }}\n          />\n          <input\n            ref={fileRef}\n            type=\"file\"\n            accept=\"image/*\"\n            capture=\"environment\"\n            multiple\n            hidden"),
])

# ChatRoom：查看器接线（聊天图片：下载+书签）
patch('frontend/src/pages/ChatRoom.tsx', [
    ("      {viewImg && <ImageViewer src={viewImg} onClose={() => setViewImg(null)} />}",
     "      {viewImg && (\n"
     "        <ImageViewer\n"
     "          src={viewImg}\n"
     "          onClose={() => setViewImg(null)}\n"
     "          onDownload={() => {\n"
     "            const a = document.createElement('a')\n"
     "            a.href = viewImg\n"
     "            a.download = 'chat-image.jpg'\n"
     "            a.click()\n"
     "          }}\n"
     "          onBookmark={async () => {\n"
     "            await libraryApi.addBookmark({ target_type: 'image', target_id: 0, label: '聊天图片' })\n"
     "            toast('已加书签')\n"
     "          }}\n"
     "        />\n"
     "      )}"),
])

# ============ 2) BookDetail：相册按钮 + 查看器接线 ============
patch('frontend/src/pages/BookDetail.tsx', [
    ("  const fileRef = useRef<HTMLInputElement>(null)",
     "  const fileRef = useRef<HTMLInputElement>(null)\n  const albumRef = useRef<HTMLInputElement>(null)"),
    ("        right={\n          <IconBtn icon={<IconPlus size={20} />} label=\"添加页面\" onClick={() => fileRef.current?.click()} />\n        }",
     "        right={\n          <div className=\"row\" style={{ gap: 2 }}>\n            <IconBtn icon={<IconImage size={20} />} label=\"相册选图\" onClick={() => albumRef.current?.click()} />\n            <IconBtn icon={<IconPlus size={20} />} label=\"拍照加页\" onClick={() => fileRef.current?.click()} />\n          </div>\n        }"),
    ("      <input\n        ref={fileRef}\n        type=\"file\"\n        accept=\"image/*\"\n        capture=\"environment\"\n        multiple\n        hidden",
     "      <input\n        ref={albumRef}\n        type=\"file\"\n        accept=\"image/*\"\n        multiple\n        hidden\n        onChange={(e) => {\n          addPage(e.target.files)\n          e.target.value = ''\n        }}\n      />\n      <input\n        ref={fileRef}\n        type=\"file\"\n        accept=\"image/*\"\n        capture=\"environment\"\n        multiple\n        hidden"),
    # 查看器接线（书页：书签+下载）
    ("      {viewImg && <ImageViewer src={viewImg} onClose={() => setViewImg(null)} />}",
     "      {viewImg && (\n"
     "        <ImageViewer\n"
     "          src={viewImg}\n"
     "          onClose={() => setViewImg(null)}\n"
     "          onDownload={() => page && libraryApi.download(Number(id), page.image_path)}\n"
     "          onBookmark={async () => {\n"
     "            await libraryApi.addBookmark({\n"
     "              target_type: 'book_page',\n"
     "              target_id: page?.id || 0,\n"
     "              label: `${data?.book?.name || '书'} P${page?.page_no || ''}`,\n"
     "            })\n"
     "            toast('已加书签')\n"
     "          }}\n"
     "        />\n"
     "      )}"),
    ("import { IconCamera, IconDelete, IconPlus, IconImage } from '../icons'",
     "import { IconCamera, IconPlus, IconImage } from '../icons'"),
])

# ============ 3) Library：相册不强制相机 + 查看器接线 ============
patch('frontend/src/pages/Library.tsx', [
    ("  const fileRef = useRef<HTMLInputElement>(null)",
     "  const fileRef = useRef<HTMLInputElement>(null)\n  const albumRef = useRef<HTMLInputElement>(null)"),
    ("        <Btn variant=\"tonal\" sm leadingIcon={<IconImage size={16} />} onClick={() => openUpload('image')}>\n          相册\n        </Btn>",
     "        <Btn variant=\"tonal\" sm leadingIcon={<IconImage size={16} />} onClick={() => {\n          setPendingKind('image')\n          setUploadSubject(subject)\n          albumRef.current?.click()\n        }}>\n          相册\n        </Btn>"),
    ("        <input\n          ref={fileRef}\n          type=\"file\"\n          accept={pendingKind === 'image' ? 'image/*' : '.pdf,.docx,.txt,.md,.csv,.json,image/*'}\n          capture={pendingKind === 'image' ? 'environment' : undefined}\n          multiple\n          hidden",
     "        <input\n          ref={albumRef}\n          type=\"file\"\n          accept=\"image/*\"\n          multiple\n          hidden\n          onChange={(e) => {\n            doUpload(e.target.files)\n            e.target.value = ''\n          }}\n        />\n        <input\n          ref={fileRef}\n          type=\"file\"\n          accept={pendingKind === 'image' ? 'image/*' : '.pdf,.docx,.txt,.md,.csv,.json,image/*'}\n          capture={pendingKind === 'image' ? 'environment' : undefined}\n          multiple\n          hidden"),
    # 查看器接线（档案条目：书签+下载）
    ("      {viewImg && <ImageViewer src={viewImg} onClose={() => setViewImg(null)} />}",
     "      {viewImg && (\n"
     "        <ImageViewer\n"
     "          src={viewImg}\n"
     "          onClose={() => setViewImg(null)}\n"
     "          onDownload={() => item && libraryApi.download(item.id, item.file_name || 'file')}\n"
     "          onBookmark={async () => {\n"
     "            await libraryApi.addBookmark({\n"
     "              target_type: 'library_item',\n"
     "              target_id: item?.id || 0,\n"
     "              label: item?.title || '资料图片',\n"
     "            })\n"
     "            toast('已加书签')\n"
     "          }}\n"
     "        />\n"
     "      )}"),
])

# ============ 4) WrongDetail：查看器接线（错题图：书签+下载） ============
patch('frontend/src/pages/WrongDetail.tsx', [
    ("      {viewImg && <ImageViewer src={viewImg} onClose={() => setViewImg(null)} />}",
     "      {viewImg && (\n"
     "        <ImageViewer\n"
     "          src={viewImg}\n"
     "          onClose={() => setViewImg(null)}\n"
     "          onDownload={() => {\n"
     "            const a = document.createElement('a')\n"
     "            a.href = viewImg\n"
     "            a.download = 'wrong-question.jpg'\n"
     "            a.click()\n"
     "          }}\n"
     "          onBookmark={async () => {\n"
     "            await api.post('/api/library/bookmarks', {\n"
     "              target_type: 'wrong_question',\n"
     "              target_id: Number(id),\n"
     "              label: (w.question_text || '错题图片').slice(0, 30),\n"
     "            })\n"
     "            toast('已加书签')\n"
     "          }}\n"
     "        />\n"
     "      )}"),
])

print('ALL PATCHED')
