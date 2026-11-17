import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, dataApi, providersApi } from '../api'
import {
  Btn,
  CardView,
  ChipFilter,
  ChipRow,
  DialogBox,
  Field,
  Loading,
  SelectField,
  Sheet,
  TabsBar,
  TopBar,
  Badge,
} from '../ui'
import { GRADES, SUBJECTS } from '../constants'
import { useAuth, useToast } from '../store'
import { useThemeMode } from '../ui'
import { IconClose, IconPlus } from '../icons'

type Tab = 'personal' | 'global' | 'providers' | 'subjects' | 'data' | 'users' | 'zhixue'

export default function Settings() {
  const nav = useNavigate()
  const toast = useToast()
  const { user } = useAuth()
  const { mode: themeMode, setMode: setThemeMode } = useThemeMode()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>(user?.role === 'admin' ? 'providers' : 'personal')
  const [g, setG] = useState<any>({})
  const [p, setP] = useState<any>({})
  const [users, setUsers] = useState<any[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', grade: '初一', display_name: '' })
  const [subjects, setSubjects] = useState<string[]>([...SUBJECTS])
  const [customSubject, setCustomSubject] = useState('')
  // 供应商
  const [providers, setProviders] = useState<any[]>([])
  const [currentRef, setCurrentRef] = useState('')
  const [showProvider, setShowProvider] = useState(false)
  const [editProvider, setEditProvider] = useState<any>(null)
  const [provForm, setProvForm] = useState({
    name: '', base_url: '', api_key: '', models: '', vision_models: '', max_images: '5',
  })
  // 数据
  const importRef = useRef<HTMLInputElement>(null)
  const [importScope, setImportScope] = useState<'personal' | 'full'>('personal')
  const [busy, setBusy] = useState('')
  const [nightlyTime, setNightlyTime] = useState('23:00')
  const [showGradeUp, setShowGradeUp] = useState(false)
  const [gradeInfo, setGradeInfo] = useState<any>(null)
  const [newSubjects, setNewSubjects] = useState<string[]>([])
  const [keepWeak, setKeepWeak] = useState(true)
  const [gradeBusy, setGradeBusy] = useState(false)
  const [zxw, setZxw] = useState<any>(null)
  const [zxwCookie, setZxwCookie] = useState('')
  const [zxwBooklet, setZxwBooklet] = useState('')
  const [zxwBusy, setZxwBusy] = useState('')
  const [zxwRuns, setZxwRuns] = useState<any[]>([])
  const [nightlyMode, setNightlyMode] = useState('ai_smart')
  const [autoApprove, setAutoApprove] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.get<any>('/api/settings')
      setData(res)
      setG({
        api_base_url: res.global?.api_base_url || '',
        api_key: '',
        chat_model: res.global?.chat_model || '',
        vision_model: res.global?.vision_model || '',
        temperature: res.global?.temperature ?? 0.7,
        system_extra_prompt: res.global?.system_extra_prompt || '',
      })
      setP({
        api_base_url: res.personal?.api_base_url || '',
        api_key: '',
        chat_model: res.personal?.chat_model || '',
        vision_model: res.personal?.vision_model || '',
        grade: res.personal?.grade || user?.grade || '初一',
      })
      setSubjects(res.subjects || [...SUBJECTS])
      const prov = await providersApi.list()
      setProviders(prov.providers || [])
      setCurrentRef(prov.current_model_ref || '')
      api
        .get<any>('/api/settings/nightly')
        .then((n) => {
          setNightlyTime(n.nightly_time || '23:00')
          setNightlyMode(n.nightly_mode || 'ai_smart')
          setAutoApprove(!!n.auto_approve_nightly)
        })
        .catch(() => {})
      api.get<any>('/api/zhixue').then(setZxw).catch(() => {})
      api.get<any>('/api/zhixue/bookmarklet').then((b) => setZxwBooklet(b.bookmarklet || '')).catch(() => {})
      api.get<any[]>('/api/zhixue/sync-runs').then(setZxwRuns).catch(() => {})
      if (user?.role === 'admin') {
        setUsers(await api.get<any[]>('/api/auth/users'))
      }
    } catch (e: any) {
      toast(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const saveGlobal = async () => {
    await api.put('/api/settings/global', g)
    toast('全局 AI 配置已保存')
    load()
  }

  const savePersonal = async () => {
    await api.put('/api/settings/personal', p)
    toast('个人配置已保存')
    load()
  }

  const saveSubjects = async () => {
    await api.put('/api/settings/subjects', { subjects })
    toast('学科列表已保存')
  }

  const openProvider = (prov?: any) => {
    setEditProvider(prov || null)
    setProvForm(
      prov
        ? {
            name: prov.name,
            base_url: prov.base_url,
            api_key: '',
            models: (prov.model_names || []).join(', '),
            vision_models: (prov.vision_models || []).join(', '),
            max_images: String(prov.models?.[0]?.max_images || 5),
          }
        : { name: '', base_url: '', api_key: '', models: '', vision_models: '', max_images: '5' },
    )
    setShowProvider(true)
  }

  const saveProvider = async () => {
    const models = provForm.models
      .split(/[,，\s]+/)
      .map((m) => m.trim())
      .filter(Boolean)
    const visionModels = (provForm.vision_models || '')
      .split(/[,，\s]+/)
      .map((m) => m.trim())
      .filter(Boolean)
    const maxImages = parseInt(provForm.max_images || '5', 10) || 5
    try {
      if (editProvider) {
        await providersApi.update(editProvider.id, {
          name: provForm.name,
          base_url: provForm.base_url,
          api_key: provForm.api_key,
          models,
          vision_models: visionModels,
          max_images: maxImages,
        })
      } else {
        await providersApi.create({
          name: provForm.name,
          base_url: provForm.base_url,
          api_key: provForm.api_key,
          models,
          vision_models: visionModels,
          max_images: maxImages,
        })
      }
      toast('供应商已保存')
      setShowProvider(false)
      load()
    } catch (e: any) {
      toast(e.message || '保存失败')
    }
  }

  const addUser = async () => {
    try {
      await api.post('/api/auth/users', newUser)
      toast('用户创建成功')
      setShowAdd(false)
      setNewUser({ username: '', password: '', grade: '初一', display_name: '' })
      load()
    } catch (e: any) {
      toast(e.message || '创建失败')
    }
  }

  const doExport = async (scope: 'personal' | 'full') => {
    setBusy(scope)
    try {
      const blob = await dataApi.exportDownload(scope)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `backup_${scope}_${new Date().toISOString().slice(0, 10)}.zip`
      a.click()
      URL.revokeObjectURL(url)
      toast('导出完成')
    } catch (e: any) {
      toast(e.message || '导出失败')
    } finally {
      setBusy('')
    }
  }

  const doImport = async (file: File) => {
    if (
      !confirm(
        `导入为「覆盖式」：将清空${importScope === 'full' ? '整机所有' : '你的'}现有数据后恢复备份。确定继续？`,
      )
    )
      return
    setBusy('import')
    try {
      const res = await dataApi.importFile(importScope, file)
      toast(`导入成功：${JSON.stringify(res.counts)}`)
      load()
    } catch (e: any) {
      toast(e.message || '导入失败')
    } finally {
      setBusy('')
    }
  }

  if (loading) return <Loading />

  return (
    <div className="page" style={{ paddingTop: 0 }}>
      <TopBar title="设置" back={() => nav('/', { replace: true })} />

      <TabsBar<Tab>
        tabs={[
          ...(user?.role === 'admin'
            ? [
                { value: 'providers' as Tab, label: '供应商' },
                { value: 'global' as Tab, label: '旧版配置' },
              ]
            : []),
          { value: 'personal' as Tab, label: '个人' },
          { value: 'subjects' as Tab, label: '学科' },
          { value: 'zhixue' as Tab, label: '智学网' },
          { value: 'data' as Tab, label: '数据' },
          ...(user?.role === 'admin' ? [{ value: 'users' as Tab, label: '用户' }] : []),
        ]}
        value={tab}
        onChange={setTab}
      />

      <CardView variant="filled" style={{ marginTop: 12 }}>
        <div className="row">
          <div style={{ flex: 1 }}>
            <div className="title-strong">外观</div>
            <div className="caption">Material You 跟随系统质感</div>
          </div>
          <ChipRow>
            {(['light', 'dark', 'system'] as const).map((m) => (
              <ChipFilter
                key={m}
                label={m === 'light' ? '浅色' : m === 'dark' ? '深色' : '跟随系统'}
                selected={themeMode === m}
                onClick={() => setThemeMode(m)}
              />
            ))}
          </ChipRow>
        </div>
      </CardView>


      {tab === 'zhixue' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">📚 智学网集成</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              启用后自动把智学网的作业、考试成绩、错题本、原卷同步进档案库与错题本。
              登录用 Cookie（推荐，NAS 可用）：登录智学网网页端后用书签脚本复制 Cookie。
            </p>
            <div className="row" style={{ marginTop: 8 }}>
              <ChipFilter label={zxw?.enabled ? '✓ 已启用' : '启用集成'}
                          selected={!!zxw?.enabled}
                          onClick={async () => {
                            await api.put('/api/zhixue', { enabled: !zxw?.enabled })
                            const z = await api.get('/api/zhixue')
                            setZxw(z)
                          }} />
              {zxw?.status && <Badge tone={zxw.status === 'ok' ? 'mastered' : 'weak'}>状态：{zxw.status}</Badge>}
              {zxw?.last_sync_summary && <span className="caption">上次同步 {zxw.last_sync_summary}</span>}
            </div>
          </CardView>

          <CardView variant="outlined">
            <div className="title-strong">第 1 步：安装「复制 Cookie」书签</div>
            <div className="caption" style={{ lineHeight: 1.7, margin: '6px 0' }}>
              这个脚本<b>不在智学网里</b>——它是给浏览器<b>书签栏</b>用的小工具（一次安装，长期使用）：
            </div>
            {zxwBooklet && (
              <>
                <a
                  href={zxwBooklet}
                  className="badge badge-primary"
                  style={{ minHeight: 44, fontSize: 15, justifyContent: 'center', textDecoration: 'none' }}
                  onClick={(e) => {
                    e.preventDefault()
                    toast('请按住这个按钮，拖到浏览器的书签栏上')
                  }}
                >
                  📌 按住我，拖到浏览器书签栏
                </a>
                <div className="row" style={{ marginTop: 8 }}>
                  <Btn variant="tonal" sm onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(zxwBooklet)
                      toast('脚本已复制，去书签管理器新建书签并粘贴到网址栏')
                    } catch {
                      toast('复制失败，请手动选中下方代码复制')
                    }
                  }}>
                    复制脚本代码
                  </Btn>
                </div>
                <details style={{ marginTop: 8 }}>
                  <summary className="caption" style={{ cursor: 'pointer' }}>查看脚本代码</summary>
                  <div className="caption" style={{ wordBreak: 'break-all', lineHeight: 1.5, marginTop: 6 }}>
                    {zxwBooklet}
                  </div>
                </details>
              </>
            )}
            <div className="caption" style={{ lineHeight: 1.7, margin: '10px 0 6px' }}>
              <b>第 2 步：获取 Cookie</b><br />
              1. 浏览器打开 edc.zhixue.com/login.html 并登录<br />
              2. 点击书签栏里的「复制 Cookie」书签 → 自动复制<br />
              3. 粘贴到下方保存<br />
              <b>没有书签栏？</b>在智学网页面按 F12 → Application → Cookies →
              全选复制 name=value 拼接，或直接用上面的复制脚本按钮。
            </div>
            <Field label="Cookie" value={zxwCookie} onChange={setZxwCookie} multiline
                   placeholder="粘贴 document.cookie 内容" />
            <Btn variant="filled" block disabled={zxwBusy === 'login'} onClick={async () => {
              setZxwBusy('login')
              try {
                const r = await api.post<any>('/api/zhixue/login', { cookie: zxwCookie })
                toast(r.message)
                const z = await api.get('/api/zhixue')
                setZxw(z)
              } catch (e: any) {
                toast(e.message || '登录失败')
              } finally {
                setZxwBusy('')
              }
            }}>
              {zxwBusy === 'login' ? '验证中…' : '保存并验证 Cookie'}
            </Btn>
          </CardView>

          <CardView variant="outlined">
            <div className="title-strong">同步</div>
            <div className="row" style={{ marginTop: 8, gap: 8, flexWrap: 'wrap' }}>
              <Btn variant="tonal" sm disabled={zxwBusy === 'sync'} onClick={async () => {
                setZxwBusy('sync')
                try {
                  const r = await api.post<any>('/api/zhixue/sync', { scope: 'all' })
                  toast(`同步完成：新增 ${r.added} 更新 ${r.updated} 失败 ${r.failed}`)
                  setZxwRuns(await api.get('/api/zhixue/sync-runs'))
                  const z = await api.get('/api/zhixue')
                  setZxw(z)
                } catch (e: any) {
                  toast(e.message || '同步失败')
                } finally {
                  setZxwBusy('')
                }
              }}>
                {zxwBusy === 'sync' ? '同步中…' : '立即同步全部'}
              </Btn>
              <Btn variant="outlined" sm disabled={!!zxwBusy} onClick={async () => {
                setZxwBusy('tidy')
                try {
                  const r = await api.post<any>('/api/zhixue/tidy', {})
                  toast(`整理完成：修图 ${r.images_fixed} · 清坏图 ${r.images_dropped} · 清无效 ${r.junk_removed} · 去重 ${r.dup_removed}`)
                } catch (e: any) {
                  toast(e.message || '整理失败')
                } finally {
                  setZxwBusy('')
                }
              }}>
                {zxwBusy === 'tidy' ? '整理中…' : '快速整理（免费）'}
              </Btn>
              <Btn variant="filled" sm disabled={!!zxwBusy} onClick={async () => {
                if (!confirm('AI 深度整理会逐条清洗/补全资料（如“略”补全为真实解法），消耗一定 AI 额度，继续？')) return
                setZxwBusy('ai-tidy')
                try {
                  const r = await api.post<any>('/api/zhixue/tidy', { ai: true })
                  toast(`AI 整理完成：清洗 ${r.ai_cleaned || 0} · 补解法 ${r.ai_solutions_filled || 0} · 判无效 ${r.ai_junk_removed || 0}`)
                } catch (e: any) {
                  toast(e.message || '整理失败')
                } finally {
                  setZxwBusy('')
                }
              }}>
                {zxwBusy === 'ai-tidy' ? 'AI 整理中…' : 'AI 深度整理'}
              </Btn>
              {['homework', 'exam', 'errorbook'].map((sc) => (
                <Btn key={sc} variant="outlined" sm disabled={!!zxwBusy} onClick={async () => {
                  setZxwBusy(sc)
                  try {
                    const r = await api.post<any>('/api/zhixue/sync', { scope: sc })
                    toast(`${sc}：+${r.added}/~${r.updated}`)
                    setZxwRuns(await api.get('/api/zhixue/sync-runs'))
                  } catch (e: any) {
                    toast(e.message || '同步失败')
                  } finally {
                    setZxwBusy('')
                  }
                }}>
                  同步{sc === 'homework' ? '作业' : sc === 'exam' ? '考试' : '错题本'}
                </Btn>
              ))}
            </div>
          </CardView>

          <div className="section-title" style={{ fontSize: '1.05rem' }}>同步记录</div>
          {(zxwRuns || []).map((r: any) => (
            <CardView key={r.id} variant="filled">
              <div className="row">
                <Badge tone="primary">{r.scope}</Badge>
                <span className="caption">+{r.added} / ~{r.updated} / ✗{r.failed}</span>
                <span className="spacer" />
                <span className="caption">{(r.created_at || '').slice(0, 16).replace('T', ' ')}</span>
              </div>
              {r.message && <div className="caption clamp-2">{r.message}</div>}
            </CardView>
          ))}
          {!zxwRuns?.length && <div className="caption">还没有同步记录</div>}
        </div>
      )}

      {/* ===== 供应商（v4 核心） ===== */}
      {tab === 'providers' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">供应商与模型</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              可同时添加多个供应商（如小米 MiMo、DeepSeek），每个供应商下填多个模型名；
              在对话页顶栏随时切换。图片识别跟随当前选中的模型。
            </p>
            <div className="caption" style={{ marginTop: 6 }}>
              当前模型：{currentRef ? currentRef.replace('::', ' · ') : '未选择'}
            </div>
          </CardView>

          <Btn variant="filled" onClick={() => openProvider()} leadingIcon={<IconPlus size={16} />}>
            添加供应商
          </Btn>

          {providers.map((prov) => (
            <CardView key={prov.id} variant="elevated">
              <div className="row">
                <div style={{ flex: 1 }}>
                  <div className="title-strong">
                    {prov.name}
                    {currentRef.startsWith(`${prov.id}::`) && (
                      <Badge tone="primary" >使用中</Badge>
                    )}
                  </div>
                  <div className="caption">{prov.base_url}</div>
                </div>
                <Btn variant="text" sm onClick={() => openProvider(prov)}>编辑</Btn>
                <Btn
                  variant="text"
                  sm
                  onClick={async () => {
                    if (!confirm(`删除供应商「${prov.name}」？`)) return
                    await providersApi.remove(prov.id)
                    load()
                  }}
                >
                  删除
                </Btn>
              </div>
              <ChipRow>
                {(prov.model_names || []).map((m: string) => {
                  const ref = `${prov.id}::${m}`
                  const isVision = (prov.vision_models || []).includes(m)
                  return (
                    <ChipFilter
                      key={ref}
                      label={isVision ? `${m} 👁` : m}
                      selected={currentRef === ref}
                      onClick={async () => {
                        await providersApi.setCurrent(ref)
                        setCurrentRef(ref)
                        toast(`全局默认模型：${prov.name} · ${m}`)
                      }}
                    />
                  )
                })}
              </ChipRow>
            </CardView>
          ))}
        </div>
      )}

      {/* ===== 旧版全局配置（兼容保留） ===== */}
      {tab === 'global' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">旧版全局配置（兼容）</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              推荐使用「供应商」管理。此页保留旧式单一接口配置，作为未配置供应商时的兜底。
            </p>
          </CardView>
          <Field label="Base URL" value={g.api_base_url} onChange={(v) => setG({ ...g, api_base_url: v })} />
          <Field
            label={data?.global?.api_key_masked ? `API Key（已保存：${data.global.api_key_masked}）` : 'API Key'}
            value={g.api_key}
            onChange={(v) => setG({ ...g, api_key: v })}
            type="password"
          />
          <Field label="对话模型" value={g.chat_model} onChange={(v) => setG({ ...g, chat_model: v })} />
          <Field label="视觉模型" value={g.vision_model} onChange={(v) => setG({ ...g, vision_model: v })} />
          <Field label="全局附加提示词（可选）" value={g.system_extra_prompt} onChange={(v) => setG({ ...g, system_extra_prompt: v })} multiline />
          <Btn variant="filled" block onClick={saveGlobal}>保存</Btn>
        </div>
      )}

      {tab === 'personal' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">个人覆盖配置</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              留空表示使用全局供应商配置；填写后只对你自己生效（用自己的 API 额度）。
            </p>
          </CardView>
          <SelectField label="我的年级" value={p.grade} options={GRADES} onChange={(v) => setP({ ...p, grade: v })} />
          <Field label="Base URL（留空用全局）" value={p.api_base_url} onChange={(v) => setP({ ...p, api_base_url: v })} />
          <Field
            label={data?.personal?.api_key_masked ? `API Key（已保存：${data.personal.api_key_masked}）` : 'API Key（留空用全局）'}
            value={p.api_key}
            onChange={(v) => setP({ ...p, api_key: v })}
            type="password"
          />
          <Field label="对话模型（留空用全局）" value={p.chat_model} onChange={(v) => setP({ ...p, chat_model: v })} />
          <Btn variant="filled" block onClick={savePersonal}>保存个人配置</Btn>

          <CardView variant="filled">
            <div className="title-strong">📈 升年级</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              学年结束后一键升级：AI 生成学年总结存入档案库，旧图谱内容归档（可查），
              按新年级调整学科。薄弱知识点可选择带入继续攻克。
            </p>
            <Btn variant="tonal" block style={{ marginTop: 10 }} onClick={async () => {
              const info = await api.get<any>('/api/auth/grade-options')
              setGradeInfo(info)
              setNewSubjects(info.next_subjects || [])
              setShowGradeUp(true)
            }}>
              开始升年级向导
            </Btn>
          </CardView>
        </div>
      )}

      {tab === 'subjects' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">学科管理</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              点击学科可隐藏/恢复（例如初三没有地理、生物）。隐藏后错题录入和图谱中不再显示。
            </p>
          </CardView>
          <ChipRow>
            {SUBJECTS.map((s) => (
              <ChipFilter
                key={s}
                label={subjects.includes(s) ? `✓ ${s}` : `${s}（已隐藏）`}
                selected={subjects.includes(s)}
                onClick={() =>
                  setSubjects(
                    subjects.includes(s) ? subjects.filter((x) => x !== s) : [...subjects, s],
                  )
                }
              />
            ))}
          </ChipRow>
          <div className="row" style={{ gap: 8 }}>
            <div style={{ flex: 1 }}>
              <Field label="添加自定义学科" value={customSubject} onChange={setCustomSubject} placeholder="如 综合实践" />
            </div>
            <Btn
              variant="tonal"
              onClick={() => {
                const name = customSubject.trim()
                if (name && !subjects.includes(name)) setSubjects([...subjects, name])
                setCustomSubject('')
              }}
            >
              <IconPlus size={16} /> 添加
            </Btn>
          </div>
          <Btn variant="filled" block onClick={saveSubjects}>保存学科列表</Btn>
        </div>
      )}

      {/* ===== 数据：导出 / 导入（v4） ===== */}
      {tab === 'data' && (
        <div className="col" style={{ marginTop: 12 }}>
          <CardView variant="filled">
            <div className="title-strong">🌙 夜间自动整理</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              每天在设定时间自动：OCR 提取新照片文字 → 归档 → 识别学习进度 → 生成当晚简报。
            </p>
            <div className="row" style={{ marginTop: 8 }}>
              <div style={{ flex: 1 }}>
                <Field label="整理时间（HH:MM）" value={nightlyTime}
                       onChange={setNightlyTime} placeholder="23:00" />
              </div>
              <Btn variant="tonal" sm onClick={async () => {
                await api.put('/api/settings/nightly', {
                  nightly_time: nightlyTime,
                  nightly_enabled: true,
                })
                toast('夜间整理时间已保存')
              }}>
                保存
              </Btn>
            </div>
          </CardView>

          <CardView variant="filled">
            <div className="title-strong">数据导出 / 导入</div>
            <p className="muted" style={{ lineHeight: 1.6 }}>
              备份为 ZIP（含错题、图谱、档案、对话、目标、方法、报告与图片），
              可用于迁移服务器。导入为<b>覆盖式</b>——先清空对应范围再恢复。
            </p>
          </CardView>

          <Btn variant="filled" block disabled={busy === 'personal'} onClick={() => doExport('personal')}>
            {busy === 'personal' ? '导出中…' : '导出我的数据（个人）'}
          </Btn>
          {user?.role === 'admin' && (
            <Btn variant="tonal" block disabled={busy === 'full'} onClick={() => doExport('full')}>
              {busy === 'full' ? '导出中…' : '导出整机数据（全部用户+设置）'}
            </Btn>
          )}

          <div className="divider" />
          <div className="title-strong">导入备份（覆盖式）</div>
          {user?.role === 'admin' && (
            <ChipRow>
              <ChipFilter label="恢复到我的账号" selected={importScope === 'personal'}
                          onClick={() => setImportScope('personal')} />
              <ChipFilter label="恢复整机（全部用户）" selected={importScope === 'full'}
                          onClick={() => setImportScope('full')} />
            </ChipRow>
          )}
          <input
            ref={importRef}
            type="file"
            accept=".zip"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) doImport(f)
              e.target.value = ''
            }}
          />
          <Btn variant="outlined" block disabled={busy === 'import'}
               onClick={() => importRef.current?.click()}>
            {busy === 'import' ? '导入中…' : '选择备份 ZIP 导入'}
          </Btn>
        </div>
      )}

      {tab === 'users' && (
        <div className="col" style={{ marginTop: 12 }}>
          <Btn variant="filled" onClick={() => setShowAdd(true)}>
            <IconPlus size={16} /> 创建用户
          </Btn>
          {(users || []).map((u) => (
            <CardView key={u.id} variant="filled">
              <div className="row">
                <div style={{ flex: 1 }}>
                  <div className="title-strong">
                    {u.display_name || u.username}
                    {u.role === 'admin' && <Badge tone="primary">管理员</Badge>}
                    {!u.is_active && <Badge tone="weak">已停用</Badge>}
                  </div>
                  <div className="caption">
                    {u.username} · {u.grade || '—'}
                  </div>
                </div>
                <Btn
                  variant="tonal"
                  sm
                  onClick={async () => {
                    await api.put(`/api/auth/users/${u.id}`, { is_active: !u.is_active })
                    load()
                  }}
                >
                  {u.is_active ? '停用' : '启用'}
                </Btn>
                <Btn
                  variant="text"
                  sm
                  onClick={async () => {
                    const pwd = prompt(`为 ${u.username} 设置新密码（至少 6 位）`)
                    if (!pwd) return
                    if (pwd.length < 6) return toast('密码至少 6 位')
                    await api.put(`/api/auth/users/${u.id}`, { password: pwd })
                    toast('密码已重置')
                  }}
                >
                  重置密码
                </Btn>
              </div>
            </CardView>
          ))}
        </div>
      )}


      <Sheet open={showGradeUp} onClose={() => setShowGradeUp(false)} title="升年级向导">
        <div className="col">
          <div className="caption">
            当前年级：{gradeInfo?.current_grade || '—'} → 目标年级：{gradeInfo?.next_grade || '高三（无下一档）'}
          </div>
          {!gradeInfo?.next_grade && <div className="muted">已经最高年级，无需升级。</div>}
          {gradeInfo?.next_grade && (
            <>
              <div className="caption">新年级学科（可增减）：</div>
              <ChipRow>
                {GRADES.length > 0 &&
                  Array.from(new Set([...(gradeInfo.next_subjects || []), ...SUBJECTS])).map((sub: any) => (
                    <ChipFilter
                      key={sub}
                      label={newSubjects.includes(sub) ? `✓ ${sub}` : sub}
                      selected={newSubjects.includes(sub)}
                      onClick={() =>
                        setNewSubjects(
                          newSubjects.includes(sub)
                            ? newSubjects.filter((x) => x !== sub)
                            : [...newSubjects, sub],
                        )
                      }
                    />
                  ))}
              </ChipRow>
              <ChipFilter
                label={keepWeak ? '✓ 薄弱知识点带入新年级继续攻克' : '薄弱知识点也一并归档'}
                selected={keepWeak}
                onClick={() => setKeepWeak(!keepWeak)}
              />
              <Btn variant="filled" block disabled={gradeBusy} onClick={async () => {
                if (!confirm('确认升年级？旧内容将归档（保留可查），AI 会生成学年总结。')) return
                setGradeBusy(true)
                try {
                  const res = await api.post<any>('/api/auth/grade-up', {
                    new_grade: gradeInfo.next_grade,
                    subjects: newSubjects,
                    keep_weak: keepWeak,
                  })
                  toast(`已升级到 ${res.new_grade}：归档 ${res.archived_nodes} 个节点${res.summary_saved ? '，学年总结已入库' : ''}`)
                  setShowGradeUp(false)
                  load()
                } catch (e: any) {
                  toast(e.message || '升级失败')
                } finally {
                  setGradeBusy(false)
                }
              }}>
                {gradeBusy ? 'AI 总结中…' : `确认升级到 ${gradeInfo?.next_grade}`}
              </Btn>
            </>
          )}
        </div>
      </Sheet>

      {/* 供应商编辑对话框 */}
      <DialogBox
        open={showProvider}
        onClose={() => setShowProvider(false)}
        title={editProvider ? '编辑供应商' : '添加供应商'}
      >
        <div className="col">
          <Field label="名称（如 小米MiMo / DeepSeek）" value={provForm.name}
                 onChange={(v) => setProvForm({ ...provForm, name: v })} />
          <Field label="Base URL（含 /v1）" value={provForm.base_url}
                 onChange={(v) => setProvForm({ ...provForm, base_url: v })}
                 placeholder="https://api.example.com/v1" />
          <Field
            label={editProvider?.has_key ? `API Key（已保存：${editProvider.api_key_masked}，留空不改）` : 'API Key'}
            value={provForm.api_key}
            onChange={(v) => setProvForm({ ...provForm, api_key: v })}
            type="password"
          />
          <Field label="模型名（逗号/空格分隔）" value={provForm.models}
                 onChange={(v) => setProvForm({ ...provForm, models: v })}
                 placeholder="mimo-a, mimo-b" />
          <Field label="支持视觉的模型（逗号分隔，拍照/OCR 用）" value={provForm.vision_models}
                 onChange={(v) => setProvForm({ ...provForm, vision_models: v })}
                 placeholder="如 mimo-vl；纯文本模型请留空" />
          <Field label="单次最大图片数" value={provForm.max_images}
                 onChange={(v) => setProvForm({ ...provForm, max_images: v })}
                 placeholder="5" />
          <div className="row">
            <Btn variant="text" onClick={() => setShowProvider(false)}>
              <IconClose size={16} /> 取消
            </Btn>
            <span className="spacer" />
            <Btn variant="filled" onClick={saveProvider}>保存</Btn>
          </div>
        </div>
      </DialogBox>

      <DialogBox open={showAdd} onClose={() => setShowAdd(false)} title="创建用户">
        <div className="col">
          <Field label="用户名" value={newUser.username} onChange={(v) => setNewUser({ ...newUser, username: v })} />
          <Field label="昵称（可选）" value={newUser.display_name} onChange={(v) => setNewUser({ ...newUser, display_name: v })} />
          <Field label="密码（至少 6 位）" value={newUser.password} onChange={(v) => setNewUser({ ...newUser, password: v })} type="password" />
          <SelectField label="年级" value={newUser.grade} options={GRADES} onChange={(v) => setNewUser({ ...newUser, grade: v })} />
          <div className="row">
            <Btn variant="text" onClick={() => setShowAdd(false)}>取消</Btn>
            <span className="spacer" />
            <Btn variant="filled" onClick={addUser}>创建</Btn>
          </div>
        </div>
      </DialogBox>
    </div>
  )
}
