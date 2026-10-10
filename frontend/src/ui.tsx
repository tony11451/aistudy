/** UI 适配层：基于 @language-lit/material3-expressive（M3 Expressive 官方规范实现） */
import {
  BottomSheet,
  Button,
  Card,
  Chip,
  CircularProgress,
  Dialog,
  IconButton,
  Material3Provider,
  NavigationBar,
  Select,
  Snackbar,
  Tabs,
  TextArea,
  TextField,
  WavyProgress,
} from '@language-lit/material3-expressive'
import type { ReactNode } from 'react'
import { createContext, useContext, useState } from 'react'
import { IconArrowLeft, IconClose } from './icons'

/* ---------- 主题 ---------- */
type ThemeMode = 'light' | 'dark' | 'system'
const ThemeCtx = createContext<{ mode: ThemeMode; setMode: (m: ThemeMode) => void }>({
  mode: 'system',
  setMode: () => {},
})
export const useThemeMode = () => useContext(ThemeCtx)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>(
    (localStorage.getItem('st_theme') as ThemeMode) || 'system',
  )
  const setMode = (m: ThemeMode) => {
    localStorage.setItem('st_theme', m)
    setModeState(m)
  }
  return (
    <ThemeCtx.Provider value={{ mode, setMode }}>
      <Material3Provider colorMode={mode} preventColorSchemeFlash>
        {children}
      </Material3Provider>
    </ThemeCtx.Provider>
  )
}

/* ---------- 按钮 ---------- */
type BtnVariant = 'filled' | 'tonal' | 'outlined' | 'text' | 'danger'
const VARIANT_MAP: Record<BtnVariant, 'filled' | 'tonal' | 'outlined' | 'text'> = {
  filled: 'filled',
  tonal: 'tonal',
  outlined: 'outlined',
  text: 'text',
  danger: 'filled',
}

export function Btn({
  variant = 'filled',
  size = 'medium',
  block,
  sm,
  children,
  disabled,
  onClick,
  leadingIcon,
  type = 'button',
  style,
}: {
  variant?: BtnVariant
  size?: 'extra-small' | 'small' | 'medium' | 'large'
  block?: boolean
  sm?: boolean
  children: ReactNode
  disabled?: boolean
  onClick?: () => void
  leadingIcon?: ReactNode
  type?: 'button' | 'submit'
  style?: React.CSSProperties
}) {
  return (
    <Button
      variant={VARIANT_MAP[variant]}
      size={sm ? 'small' : size}
      width={block ? 'full' : 'fit'}
      disabled={disabled}
      onClick={onClick}
      leadingIcon={leadingIcon}
      type={type}
      style={variant === 'danger' ? { background: 'var(--m3e-sys-color-error)', color: 'var(--m3e-sys-color-on-error)', ...style } : style}
    >
      {children}
    </Button>
  )
}

export function IconBtn({
  icon,
  onClick,
  variant = 'standard',
  label,
}: {
  icon: ReactNode
  onClick?: () => void
  variant?: 'standard' | 'filled' | 'tonal' | 'outlined'
  label?: string
}) {
  return (
    <IconButton variant={variant} onClick={onClick} aria-label={label || '操作'}>
      {icon}
    </IconButton>
  )
}

/* ---------- 卡片 ---------- */
export function CardView({
  children,
  variant = 'filled',
  onClick,
  style,
  className,
}: {
  children: ReactNode
  variant?: 'filled' | 'elevated' | 'outlined'
  onClick?: () => void
  style?: React.CSSProperties
  className?: string
}) {
  const cardProps: any = {
    variant,
    as: 'div',
    style: { padding: 16, cursor: onClick ? 'pointer' : undefined, ...style },
    className,
  }
  if (onClick) {
    cardProps.interactive = true
    cardProps.onClick = onClick
  }
  return <Card {...cardProps}>{children}</Card>
}

/* ---------- Chip 筛选 ---------- */
export function ChipFilter({
  label,
  selected,
  onClick,
  leadingIcon,
}: {
  label: ReactNode
  selected?: boolean
  onClick?: () => void
  leadingIcon?: ReactNode
}) {
  return (
    <Chip
      kind="filter"
      variant={selected ? 'elevated' : 'flat'}
      shape="expressive"
      selected={!!selected}
      onSelectedChange={() => onClick?.()}
      leadingIcon={leadingIcon}
    >
      {label}
    </Chip>
  )
}

export function ChipRow({ children }: { children: ReactNode }) {
  return (
    <div className="chip-row" style={{ display: 'flex', gap: 8, overflowX: 'auto', padding: '4px 2px' }}>
      {children}
    </div>
  )
}

/* ---------- 表单 ---------- */
export function Field({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
  required,
  multiline,
  rows,
  supportingText,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  type?: 'text' | 'password'
  required?: boolean
  multiline?: boolean
  rows?: number
  supportingText?: string
}) {
  if (multiline) {
    return (
      <TextArea
        label={label}
        value={value}
        placeholder={placeholder}
        rows={rows ?? 3}
        supportingText={supportingText}
        required={required}
        onChange={(e: any) => onChange(e.target.value)}
        style={{ width: '100%' }}
      />
    )
  }
  return (
    <TextField
      label={label}
      type={type}
      value={value}
      placeholder={placeholder}
      required={required}
      supportingText={supportingText}
      onChange={(e: any) => onChange(e.target.value)}
      style={{ width: '100%' }}
    />
  )
}

export function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: readonly string[]
  onChange: (v: string) => void
}) {
  return (
    <Select
      label={label}
      value={value}
      options={options.map((o) => ({ value: o, label: o }))}
      onValueChange={onChange}
      style={{ width: '100%' }}
    />
  )
}

/* ---------- 顶栏 ---------- */
export function TopBar({
  title,
  back,
  right,
}: {
  title: ReactNode
  back?: () => void
  right?: ReactNode
}) {
  return (
    <div className="topbar">
      {back && <IconBtn icon={<IconArrowLeft size={22} />} onClick={back} label="返回" />}
      <div className="topbar-title">{title}</div>
      {right}
    </div>
  )
}

/* ---------- 底部面板 / 对话框 ---------- */
export function Sheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title?: ReactNode
  children: ReactNode
}) {
  return (
    <BottomSheet
      variant="modal"
      value={open ? 'expanded' : 'hidden'}
      onValueChange={(v: any) => {
        if (v === 'hidden') onClose()
      }}
      style={{ maxHeight: '86vh', overflowY: 'auto' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 2px 12px' }}>
        {title && <div className="title-strong" style={{ flex: 1 }}>{title}</div>}
        <IconBtn icon={<IconClose size={20} />} onClick={onClose} label="关闭" />
      </div>
      {children}
    </BottomSheet>
  )
}

export function DialogBox({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
}) {
  return (
    <Dialog
      open={open}
      onOpenChange={(o: boolean) => {
        if (!o) onClose()
      }}
      title={title}
      style={{ width: 'min(92vw, 440px)' }}
    >
      {children}
    </Dialog>
  )
}

/* ---------- Tabs ---------- */
export function TabsBar<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: ReactNode; icon?: ReactNode }[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <Tabs
      items={tabs.map((t) => ({ value: t.value, label: t.label, icon: t.icon }))}
      value={value}
      onValueChange={(v) => onChange(v as T)}
      scrollable
    />
  )
}

/* ---------- 底部导航 ---------- */
export function BottomNav({
  items,
  value,
  onChange,
}: {
  items: { value: string; label: string; icon: ReactNode }[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <NavigationBar
      items={items.map((i) => ({ value: i.value, label: i.label, icon: i.icon }))}
      value={value}
      onValueChange={onChange}
    />
  )
}

/* ---------- 提示 / 进度 ---------- */
export function useToastImpl() {
  const [msg, setMsg] = useState<{ id: number; text: string } | null>(null)
  const show = (text: string) => {
    const id = Date.now()
    setMsg({ id, text })
    setTimeout(() => setMsg((m) => (m && m.id === id ? null : m)), 2800)
  }
  const node = msg ? (
    <Snackbar open message={msg.text} onOpenChange={(o: boolean) => !o && setMsg(null)} />
  ) : null
  return { show, node }
}

export function Loading({ text = '加载中…' }: { text?: string }) {
  return (
    <div className="col" style={{ alignItems: 'center', padding: '40px 0', gap: 14 }}>
      <CircularProgress />
      <span className="muted">{text}</span>
    </div>
  )
}

export function ProgressBar({ value }: { value?: number }) {
  return value === undefined ? (
    <WavyProgress shape="circular" style={{ width: 36, height: 36 }} />
  ) : (
    <WavyProgress value={value} />
  )
}

export function Empty({
  icon = '🌙',
  title,
  desc,
  action,
}: {
  icon?: ReactNode
  title: string
  desc?: string
  action?: ReactNode
}) {
  return (
    <div className="col" style={{ alignItems: 'center', padding: '48px 20px', gap: 10 }}>
      <div style={{ fontSize: 44 }}>{icon}</div>
      <div className="title-strong">{title}</div>
      {desc && (
        <div className="muted" style={{ textAlign: 'center' }}>
          {desc}
        </div>
      )}
      {action}
    </div>
  )
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'primary' | 'weak' | 'improving' | 'mastered' }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}
