import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import {
  Btn,
  CardView,
  ChipFilter,
  ChipRow,
  Loading,
  Sheet,
  Field,
  TopBar,
  Badge,
  IconBtn,
} from '../ui'
import { CONFIDENCE_LABEL, MASTERY_LABEL, STATE_LABEL, masteryTone, useAsync } from '../components'
import { useToast, useSubjects } from '../store'
import {
  IconCheck,
  IconChat,
  IconClose,
  IconDelete,
  IconEdit,
  IconPlus,
  IconRefresh,
  IconSparkle,
} from '../icons'

type KindFilter = '' | 'knowledge' | 'weakness'

function KpNode({ data }: NodeProps) {
  const d = data as any
  const isRoot = !d.realId || d.label === d.subjectName
  const cls = isRoot
    ? 'kp-node root'
    : d.nodeType === 'weakness'
      ? 'kp-node kp-weakness kp-' + (d.mastery || 'unknown')
      : `kp-node kp-${d.mastery || 'unknown'}`
  return (
    <div className={cls} style={{ minWidth: isRoot ? 118 : 112 }}>
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div style={{ fontWeight: isRoot ? 700 : 650 }}>{d.label}</div>
      {!isRoot && (
        <div className="caption" style={{ marginTop: 2, display: 'flex', gap: 5, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className={`mastery-dot mastery-${d.mastery || 'unknown'}`} />
          {MASTERY_LABEL[d.mastery] || '未评估'}
          {d.nodeType === 'weakness' && <span>· 弱点</span>}
          {d.confidence === 'suspected' && <span>· 疑似</span>}
          {d.errorCount > 0 && <span>· {d.errorCount} 题</span>}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  )
}

const nodeTypes = { kp: KpNode }

export default function Mindmap() {
  const nav = useNavigate()
  const toast = useToast()
  const subjects = useSubjects()
  const [subject, setSubject] = useState('数学')
  const [kind, setKind] = useState<KindFilter>('')
  const [selected, setSelected] = useState<any>(null)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [showAdd, setShowAdd] = useState(false)
  const [newNode, setNewNode] = useState({ name: '', parent: '', type: 'knowledge' })
  const [busy, setBusy] = useState('')
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { data, loading, error, reload } = useAsync(
    () => api.get<any>(`/api/knowledge/mindmap?subject=${encodeURIComponent(subject)}&kind=${kind}`),
    [subject, kind],
  )

  const flowNodes = useMemo(() => {
    if (!data?.nodes) return []
    return data.nodes.map((n: any) => ({
      id: n.id,
      type: 'kp',
      position: n.position,
      data: { ...n, subjectName: subject },
      draggable: true,
    }))
  }, [data, subject])

  const flowEdges = useMemo(() => (data?.edges || []).map((e: any) => ({ ...e, id: e.id })), [data])

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges)

  useEffect(() => {
    setNodes(flowNodes)
    setEdges(flowEdges)
  }, [flowNodes, flowEdges, setNodes, setEdges])

  // 拖动结束持久化位置
  const persistPositions = useCallback(
    (nds: any[]) => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => {
        const positions = nds
          .filter((n: any) => n.data?.realId)
          .map((n: any) => ({ id: n.data.realId, x: Math.round(n.position.x), y: Math.round(n.position.y) }))
        if (positions.length) {
          api.post('/api/knowledge/nodes/positions', { positions }).catch(() => {})
        }
      }, 600)
    },
    [],
  )

  const handleNodesChange = useCallback(
    (changes: any[]) => {
      onNodesChange(changes)
      if (changes.some((c) => c.type === 'position' && c.dragging === false)) {
        setNodes((nds) => {
          persistPositions(nds as any[])
          return nds
        })
      }
    },
    [onNodesChange, setNodes, persistPositions],
  )

  const onNodeClick = useCallback((_: any, node: any) => {
    if (node.data?.realId) {
      setSelected(node.data)
      setEditName(node.data.label)
      setEditDesc(node.data.description || '')
    }
  }, [])

  const saveNode = async () => {
    if (!selected) return
    setBusy('save')
    try {
      await api.put(`/api/knowledge/nodes/${selected.realId}`, {
        name: editName,
        description: editDesc,
      })
      toast('已保存')
      setSelected(null)
      reload()
    } catch (e: any) {
      toast(e.message || '保存失败')
    } finally {
      setBusy('')
    }
  }

  const deleteNode = async () => {
    if (!selected) return
    if (!confirm(`删除「${selected.label}」及其子节点？`)) return
    setBusy('del')
    try {
      await api.del(`/api/knowledge/nodes/${selected.realId}`)
      toast('已删除')
      setSelected(null)
      reload()
    } finally {
      setBusy('')
    }
  }

  const resummarize = async () => {
    if (!selected) return
    setBusy('ai')
    try {
      const res = await api.post<any>(`/api/knowledge/nodes/${selected.realId}/resummarize`, {})
      toast('AI 已重新整理该节点')
      setSelected(null)
      setEditName(res.name)
      reload()
    } catch (e: any) {
      toast(e.message || 'AI 重总结失败')
    } finally {
      setBusy('')
    }
  }

  const addNode = async () => {
    const name = newNode.name.trim()
    if (!name) return toast('请输入名称')
    try {
      await api.post('/api/knowledge/nodes', {
        subject,
        name,
        node_type: newNode.type,
        parent_name: newNode.parent,
        parent_id: undefined,
      })
      toast('已添加')
      setShowAdd(false)
      setNewNode({ name: '', parent: '', type: 'knowledge' })
      reload()
    } catch (e: any) {
      toast(e.message || '添加失败')
    }
  }

  return (
    <div
      className="page-full"
      style={{
        padding: 0,
        height: 'calc(100dvh - var(--app-nav-height) - env(safe-area-inset-bottom, 0px))',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <TopBar
        title="知识图谱"
        back={undefined}
        right={
          <div className="row">
            <IconBtn icon={<IconPlus size={20} />} label="添加节点" onClick={() => setShowAdd(true)} />
            <IconBtn icon={<IconRefresh size={20} />} label="刷新" onClick={reload} />
          </div>
        }
      />

      <ChipRow>
        {subjects.map((s) => (
          <ChipFilter key={s} label={s} selected={subject === s} onClick={() => setSubject(s)} />
        ))}
      </ChipRow>

      <div className="row" style={{ padding: '4px 14px 6px', gap: 8 }}>
        <ChipFilter label="全部" selected={kind === ''} onClick={() => setKind('')} />
        <ChipFilter label="仅知识点" selected={kind === 'knowledge'} onClick={() => setKind('knowledge')} />
        <ChipFilter label="仅弱点" selected={kind === 'weakness'} onClick={() => setKind('weakness')} />
        <span className="spacer" />
        <span className="caption">点击节点编辑 · 拖动保存位置</span>
      </div>

      <div style={{ flex: 1, minHeight: 380 }}>
        {loading && <Loading text="图谱生成中…" />}
        {!loading && error && (
          <div className="col" style={{ alignItems: 'center', padding: 40 }}>
            <div className="muted">{error}</div>
            <Btn variant="tonal" onClick={reload}>重试</Btn>
          </div>
        )}
        {!loading && !error && (
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={handleNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            fitView
            minZoom={0.35}
            maxZoom={1.8}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="var(--m3e-sys-color-outline-variant)" gap={22} size={1.6} />
            <Controls showInteractive={false} />
            <MiniMap
              pannable
              zoomable
              style={{ background: 'var(--m3e-sys-color-surface-container)' }}
              maskColor="rgba(0,0,0,0.12)"
            />
          </ReactFlow>
        )}
      </div>

      {/* 节点编辑 */}
      <Sheet open={!!selected} onClose={() => setSelected(null)} title={selected?.label}>
        {selected && (
          <div className="col">
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <Badge tone={masteryTone(selected.mastery)}>
                掌握度 · {MASTERY_LABEL[selected.mastery] || '未评估'}
              </Badge>
              <Badge>{STATE_LABEL[selected.learningState] || selected.learningState}</Badge>
              <Badge tone={selected.nodeType === 'weakness' ? 'weak' : 'neutral'}>
                {selected.nodeType === 'weakness' ? '弱点' : '知识点'}
              </Badge>
              <Badge tone={selected.confidence === 'confirmed' ? 'mastered' : 'improving'}>
                {CONFIDENCE_LABEL[selected.confidence] || '疑似'}
              </Badge>
              <Badge>错题 {selected.errorCount || 0} 道</Badge>
            </div>
            {selected.note && <div className="caption">📌 {selected.note}</div>}

            <Field label="名称" value={editName} onChange={setEditName} />
            <Field label="说明 / 笔记" value={editDesc} onChange={setEditDesc} multiline rows={3} />

            <Btn variant="filled" block disabled={busy === 'save'} onClick={saveNode}>
              <IconCheck size={17} /> 保存修改
            </Btn>
            <Btn
              variant="tonal"
              block
              disabled={busy === 'ai'}
              onClick={resummarize}
              leadingIcon={<IconSparkle size={17} />}
            >
              {busy === 'ai' ? 'AI 重新整理中…' : 'AI 结合错题重新总结'}
            </Btn>
            <Btn
              variant="outlined"
              block
              onClick={() => {
                setSelected(null)
                nav(`/chat?kp=${encodeURIComponent(selected.label)}&subject=${encodeURIComponent(subject)}`)
              }}
              leadingIcon={<IconChat size={17} />}
            >
              就此知识点深聊
            </Btn>
            <Btn
              variant="outlined"
              block
              onClick={() => {
                setSelected(null)
                nav(`/wrong?keyword=${encodeURIComponent(selected.label)}`)
              }}
            >
              查看相关错题
            </Btn>
            <Btn variant="danger" block disabled={busy === 'del'} onClick={deleteNode} leadingIcon={<IconDelete size={17} />}>
              删除节点
            </Btn>
          </div>
        )}
      </Sheet>

      {/* 新增节点 */}
      <Sheet open={showAdd} onClose={() => setShowAdd(false)} title={`在「${subject}」添加节点`}>
        <div className="col">
          <Field label="名称" value={newNode.name} onChange={(v) => setNewNode({ ...newNode, name: v })} placeholder="如 二次函数" />
          <Field label="上级节点（可选）" value={newNode.parent} onChange={(v) => setNewNode({ ...newNode, parent: v })} placeholder="如 函数，留空为顶层" />
          <ChipRow>
            <ChipFilter
              label="知识点"
              selected={newNode.type === 'knowledge'}
              onClick={() => setNewNode({ ...newNode, type: 'knowledge' })}
            />
            <ChipFilter
              label="弱点"
              selected={newNode.type === 'weakness'}
              onClick={() => setNewNode({ ...newNode, type: 'weakness' })}
            />
          </ChipRow>
          <div className="row">
            <Btn variant="text" onClick={() => setShowAdd(false)}>
              <IconClose size={16} /> 取消
            </Btn>
            <span className="spacer" />
            <Btn variant="filled" onClick={addNode}>
              <IconPlus size={16} /> 添加
            </Btn>
          </div>
        </div>
      </Sheet>
    </div>
  )
}
