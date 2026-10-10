import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Btn, CardView, Empty, Loading, IconBtn } from '../ui'
import { useAsync } from '../components'
import { useAuth, useToast } from '../store'
import { IconChat, IconPlus, IconClose, IconMap, IconBook } from '../icons'

export default function ChatList() {
  const nav = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const { data, loading, reload } = useAsync(() => api.get<any[]>('/api/chat/conversations'), [])

  const create = async () => {
    try {
      const conv = await api.post<any>('/api/chat/conversations', {
        title: '新对话',
        grade: user?.grade || '',
      })
      nav(`/chat/${conv.id}`)
    } catch (e: any) {
      toast(e.message || '创建失败')
    }
  }

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 12 }}>
        <div className="topbar-title" style={{ fontSize: '1.35rem' }}>提问 · 对话</div>
        <Btn variant="filled" sm onClick={create} leadingIcon={<IconPlus size={16} />}>
          新对话
        </Btn>
      </div>

      {loading && <Loading />}
      {!loading && !data?.length && (
        <Empty
          icon={<IconChat size={40} />}
          title="开始第一次学习对话"
          desc="可以问学习方法、讨论难题、聊备考规划；对话可随时「总结成知识点」沉淀进图谱"
          action={
            <Btn variant="filled" onClick={create}>
              新建对话
            </Btn>
          }
        />
      )}

      <div className="col">
        {(data || []).map((c: any) => (
          <CardView key={c.id} variant="filled" onClick={() => nav(`/chat/${c.id}`)}>
            <div className="row">
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 14,
                  background: 'var(--m3e-sys-color-primary-container)',
                  color: 'var(--m3e-sys-color-on-primary-container)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flex: 'none',
                }}
              >
                {c.context_kind === 'knowledge' ? (
                  <IconMap size={20} />
                ) : c.context_kind === 'wrong_question' ? (
                  <IconBook size={20} />
                ) : (
                  <IconChat size={20} />
                )}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="text-ellipsis" style={{ fontWeight: 600 }}>{c.title}</div>
                <div className="caption text-ellipsis">
                  {c.subject || '综合'}
                  {c.context_ref ? ` · ${c.context_ref}` : ''} · {(c.updated_at || '').slice(0, 10)}
                </div>
              </div>
              <IconBtn
                icon={<IconClose size={18} />}
                label="删除对话"
                onClick={async () => {
                  if (!confirm('删除这个对话？')) return
                  await api.del(`/api/chat/conversations/${c.id}`)
                  reload()
                }}
              />
            </div>
          </CardView>
        ))}
      </div>
    </div>
  )
}
