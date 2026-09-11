/**
 * Ingestion status presentation.
 *
 * Status semantics are owned by the backend only (`DocumentResponse.fileState`
 * and `IngestionJobResponse.stage/status`); this module just maps them to
 * Chinese labels, icons, and token-driven colors.  Unknown values fall back to
 * the raw server string and a neutral tone — never to a fake "ready".
 */

export type DocStatusTone = 'pending' | 'ready' | 'failed' | 'unknown'

export interface DocStatusView {
  tone: DocStatusTone
  label: string
  icon: string
  color: string
}

const FILE_STATE_VIEWS: Record<'pending' | 'ready' | 'failed', Omit<DocStatusView, 'tone'>> = {
  pending: { label: '处理中', icon: 'sym_o_pending', color: 'var(--tk-warning)' },
  ready: { label: '已就绪', icon: 'sym_o_task_alt', color: 'var(--tk-success)' },
  failed: { label: '处理失败', icon: 'sym_o_error', color: 'var(--tk-danger)' },
}

export function fileStateView(state?: string | null): DocStatusView {
  if (state === 'pending' || state === 'ready' || state === 'failed') {
    return { tone: state, ...FILE_STATE_VIEWS[state] }
  }
  return {
    tone: 'unknown',
    label: state ?? '',
    icon: 'sym_o_help',
    color: 'var(--tk-text-tertiary)',
  }
}

const STAGE_LABELS: Record<string, string> = {
  parse: '解析',
  chunk: '切分',
  embed: '向量化',
}

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage
}

const JOB_STATUS_LABELS: Record<string, string> = {
  queued: '排队中',
  running: '处理中',
  retryable: '重试中',
  blocked: '等待中',
  cancel_requested: '取消中',
  succeeded: '已完成',
  cancelled: '已取消',
  failed: '处理失败',
  dead_letter: '处理失败',
}

export function jobStatusLabel(status: string): string {
  return JOB_STATUS_LABELS[status] ?? status
}

const JOB_STATUS_COLORS: Record<string, string> = {
  queued: 'var(--tk-text-tertiary)',
  running: 'var(--tk-accent)',
  retryable: 'var(--tk-warning)',
  blocked: 'var(--tk-warning)',
  cancel_requested: 'var(--tk-warning)',
  succeeded: 'var(--tk-success)',
  cancelled: 'var(--tk-text-tertiary)',
  failed: 'var(--tk-danger)',
  dead_letter: 'var(--tk-danger)',
}

export function jobStatusColor(status: string): string {
  return JOB_STATUS_COLORS[status] ?? 'var(--tk-text-tertiary)'
}
