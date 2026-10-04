import { useCallback, useMemo, useState } from 'react'
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  NodeProps,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Loading, MASTERY_LABEL, Sheet, STATE_LABEL, useAsync } from '../components'
import { SUBJECTS } from '../constants'
import { useToast } from '../store'

function KpNode({ data }: NodeProps) {
  const d = data as any
  const isRoot = d.kind === 'root'
  const isUnit = d.kind === 'unit'
  const cls = isRoot
    ? 'kp-node root'
    : isUnit
      ? 'kp-node unit'
      : `kp-node kp-${d.mastery || 'unknown'}`
  return (
    <div className={cls} style={{ minWidth: isRoot ? 118 : 108 }}>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div className="text-ellipsis" style={{ fontWeight: isRoot || isUnit ? 700 : 600 }}>
        {d.label}
      </div>
      {!isRoot && !isUnit && (
        <div className="caption" style={{ marginTop: 2, display: 'flex', gap: 5, alignItems: 'center' }}>
          <span className={`mastery-dot mastery-${d.mastery || 'unknown'}`} />
          {MASTERY_LABEL[d.mastery] || '未评估'}
          {d.errorCount > 0 && <span>· {d.errorCount} 题</span>}
        </div>
      )}
      {isRoot && <div className="caption" style={{ opacity: 0.85, marginTop: 2 }}>薄弱点图谱</div>}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  )
}

const nodeTypes = { kp: KpNode }

export default function Mindmap() {
  const nav = useNavigate()
  const toast = useToast()
  const [subject, setSubject] = useState('数学')
  const [selected, setSelected] = useState<any>(null)
  const { data, loading, error, reload } = useAsync(
    () => api.get<any>(`/api/knowledge/mindmap?subject=${encodeURIComponent(subject)}`),
    [subject],
  )

  const flowNodes = useMemo(() => {
    if (!data?.nodes) return []
    return data.nodes.map((n: any) => ({
      id: n.id,
      type: 'kp',
      position: n.position,
      data: n,
      draggable: true,
    }))
  }, [data])

  const flowEdges = useMemo(() => (data?.edges || []).map((e: any) => ({ ...e, id: e.id })), [data])

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges)

  useMemo(() => {
    setNodes(flowNodes)
    setEdges(flowEdges)
  }, [flowNodes, flowEdges, setNodes, setEdges])

  const onNodeClick = useCallback((_: any, node: any) => {
    if (node.data?.kind === 'kp') setSelected(node.data)
  }, [])

  const startChat = () => {
    if (!selected) return
    nav(`/chat?kp=${encodeURIComponent(selected.label)}&subject=${encodeURIComponent(subject)}`)
  }

  return (
    <div
      className="page-full"
      style={{
        padding: 0,
        height: 'calc(100dvh - var(--md-nav-height) - env(safe-area-inset-bottom, 0px))',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div className="md-topbar">
        <div className="md-topbar-title">弱点图谱</div>
        <button className="md-iconbtn" onClick={reload} title="刷新">
          ⟳
        </button>
      </div>

      <div className="md-chip-row" style={{ padding: '10px 14px 2px' }}>
        {SUBJECTS.map((s) => (
          <button
            key={s}
            className={`md-chip ${subject === s ? 'active' : ''}`}
            onClick={() => setSubject(s)}
          >
            {s}
          </button>
        ))}
      </div>

      <div
        className="row"
        style={{ padding: '6px 16px 8px', gap: 14, flexWrap: 'wrap' }}
      >
        {['weak', 'improving', 'mastered', 'unknown'].map((m) => (
          <span key={m} className="caption row" style={{ gap: 5 }}>
            <span className={`mastery-dot mastery-${m}`} />
            {MASTERY_LABEL[m]}
          </span>
        ))}
        <span className="caption" style={{ marginLeft: 'auto' }}>
          点击知识点 → 深聊
        </span>
      </div>

      <div style={{ flex: 1, minHeight: 380 }}>
        {loading && <Loading text="图谱生成中…" />}
        {!loading && error && (
          <div className="col" style={{ alignItems: 'center', padding: 40 }}>
            <div className="muted">{error}</div>
            <button className="md-btn md-btn-tonal" onClick={reload}>重试</button>
          </div>
        )}
        {!loading && !error && (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            fitView
            minZoom={0.35}
            maxZoom={1.8}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="var(--md-outline-variant)" gap={22} size={1.6} />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              style={{ background: 'var(--md-surface-container)' }}
              maskColor="rgba(0,0,0,0.12)"
            />
          </ReactFlow>
        )}
      </div>

      <Sheet open={!!selected} onClose={() => setSelected(null)} title={selected?.label}>
        {selected && (
          <div className="col">
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <span className={`badge badge-${selected.mastery}`}>
                掌握度 · {MASTERY_LABEL[selected.mastery] || '未评估'}
              </span>
              <span className="badge">{STATE_LABEL[selected.learningState] || selected.learningState}</span>
              <span className="badge">错题 {selected.errorCount || 0} 道</span>
              {selected.unit && <span className="badge">{selected.unit}</span>}
            </div>
            {selected.note && <div className="muted">📌 {selected.note}</div>}
            <p className="muted" style={{ lineHeight: 1.6 }}>
              与 AI 深入讨论这个知识点：可以问概念、典型题型、易错点，AI 会结合你的错题档案讲解，
              并给出巩固练习方向。
            </p>
            <button className="md-btn md-btn-filled md-btn-block" onClick={startChat}>
              💬 就此知识点深聊
            </button>
            <button
              className="md-btn md-btn-tonal md-btn-block"
              onClick={() => {
                setSelected(null)
                nav(`/wrong?keyword=${encodeURIComponent(selected.label)}`)
              }}
            >
              📝 查看相关错题
            </button>
          </div>
        )}
      </Sheet>
    </div>
  )
}
