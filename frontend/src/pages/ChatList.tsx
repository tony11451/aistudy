import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Empty, Loading, useAsync } from '../components'
import { useAuth } from '../store'

export default function ChatList() {
  const nav = useNavigate()
  const { user } = useAuth()
  const { data, loading, reload } = useAsync(() => api.get<any[]>('/api/chat/conversations'), [])

  const create = async (kind: 'normal' = 'normal') => {
    const conv = await api.post<any>('/api/chat/conversations', {
      title: '新对话',
      grade: user?.grade || '',
    })
    nav(`/chat/${conv.id}`)
  }

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: 12 }}>
        <div className="md-topbar-title" style={{ fontSize: '1.3rem' }}>AI 对话</div>
        <button className="md-btn md-btn-filled md-btn-sm" onClick={() => create()}>
          ＋ 新对话
        </button>
      </div>

      {loading && <Loading />}
      {!loading && !data?.length && (
        <Empty
          icon="💬"
          title="开始第一次学习对话"
          desc="可以问学习方法、讨论难题、聊备考规划，AI 记得你的弱点和进度"
          action={
            <button className="md-btn md-btn-filled" onClick={() => create()}>
              新建对话
            </button>
          }
        />
      )}

      <div className="col">
        {(data || []).map((c: any) => (
          <div
            key={c.id}
            className="md-card md-card-tappable row"
            onClick={() => nav(`/chat/${c.id}`)}
          >
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: 'var(--md-shape-md)',
                background: 'var(--md-primary-container)',
                color: 'var(--md-on-primary-container)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 20,
                flex: 'none',
              }}
            >
              {c.context_kind === 'knowledge' ? '🧠' : c.context_kind === 'wrong_question' ? '📝' : '💬'}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="text-ellipsis" style={{ fontWeight: 600 }}>{c.title}</div>
              <div className="caption text-ellipsis">
                {c.subject || '综合'}
                {c.context_ref ? ` · ${c.context_ref}` : ''} ·{' '}
                {(c.updated_at || '').slice(0, 10)}
              </div>
            </div>
            <button
              className="md-iconbtn"
              onClick={async (e) => {
                e.stopPropagation()
                if (!confirm('删除这个对话？')) return
                await api.del(`/api/chat/conversations/${c.id}`)
                reload()
              }}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
