/**
 * 模型厂商目录：厂商识别、品牌信息、能力推断与已知向量维度。
 *
 * 用于管理台「模型配置」页：为模型/服务商挑选真实 logo、能力标签和
 * 向量维度默认值，避免管理员手工逐项填写。
 */
import baaiLogo from 'src/assets/model-logos/baai.svg'
import baichuanLogo from 'src/assets/model-logos/baichuan.svg'
import claudeLogo from 'src/assets/model-logos/claude.svg'
import deepseekLogo from 'src/assets/model-logos/deepseek.svg'
import doubaoLogo from 'src/assets/model-logos/doubao.svg'
import geminiLogo from 'src/assets/model-logos/gemini.svg'
import groqLogo from 'src/assets/model-logos/groq.svg'
import hunyuanLogo from 'src/assets/model-logos/hunyuan.svg'
import metaLogo from 'src/assets/model-logos/meta.svg'
import minimaxLogo from 'src/assets/model-logos/minimax.svg'
import mistralLogo from 'src/assets/model-logos/mistral.svg'
import moonshotLogo from 'src/assets/model-logos/moonshot.svg'
import openaiLogo from 'src/assets/model-logos/openai.svg'
import perplexityLogo from 'src/assets/model-logos/perplexity.svg'
import qwenLogo from 'src/assets/model-logos/qwen.svg'
import sparkLogo from 'src/assets/model-logos/spark.svg'
import stepfunLogo from 'src/assets/model-logos/stepfun.svg'
import yiLogo from 'src/assets/model-logos/yi.svg'
import zhipuLogo from 'src/assets/model-logos/zhipu.svg'

export type VendorId =
  | 'openai'
  | 'deepseek'
  | 'qwen'
  | 'zhipu'
  | 'moonshot'
  | 'baichuan'
  | 'mistral'
  | 'claude'
  | 'gemini'
  | 'hunyuan'
  | 'spark'
  | 'yi'
  | 'minimax'
  | 'baai'
  | 'doubao'
  | 'stepfun'
  | 'meta'
  | 'groq'
  | 'perplexity'

export interface Vendor {
  id: VendorId
  /** 厂商中文名（附英文标识便于辨认） */
  name: string
  /** 品牌色，作为无 logo 时的圆底颜色 */
  color: string
  logo?: string
}

export const VENDORS: Vendor[] = [
  { id: 'openai', name: 'OpenAI', color: '#10a37f', logo: openaiLogo },
  { id: 'deepseek', name: '深度求索', color: '#4d6bfe', logo: deepseekLogo },
  { id: 'qwen', name: '通义千问', color: '#624aff', logo: qwenLogo },
  { id: 'zhipu', name: '智谱清言', color: '#3b62f6', logo: zhipuLogo },
  { id: 'moonshot', name: '月之暗面', color: '#0f4be0', logo: moonshotLogo },
  { id: 'baichuan', name: '百川智能', color: '#2f6bff', logo: baichuanLogo },
  { id: 'mistral', name: 'Mistral', color: '#fa520f', logo: mistralLogo },
  { id: 'claude', name: 'Claude', color: '#d97757', logo: claudeLogo },
  { id: 'gemini', name: 'Gemini', color: '#4285f4', logo: geminiLogo },
  { id: 'hunyuan', name: '腾讯混元', color: '#0052d9', logo: hunyuanLogo },
  { id: 'spark', name: '讯飞星火', color: '#0f9bff', logo: sparkLogo },
  { id: 'yi', name: '零一万物', color: '#2563eb', logo: yiLogo },
  { id: 'minimax', name: 'MiniMax', color: '#1677ff', logo: minimaxLogo },
  { id: 'baai', name: '北京智源', color: '#1f6feb', logo: baaiLogo },
  { id: 'doubao', name: '豆包', color: '#0078ff', logo: doubaoLogo },
  { id: 'stepfun', name: '阶跃星辰', color: '#2d7dff', logo: stepfunLogo },
  { id: 'meta', name: 'Meta', color: '#0866ff', logo: metaLogo },
  { id: 'groq', name: 'Groq', color: '#f55036', logo: groqLogo },
  { id: 'perplexity', name: 'Perplexity', color: '#20b8cd', logo: perplexityLogo },
]

const VENDOR_RULES: Array<{ vendor: VendorId, pattern: RegExp }> = [
  { vendor: 'openai', pattern: /gpt-|^o1(-|$)|-o1(-|$)|^o3(-|$)|-o3(-|$)|text-embedding|chatgpt|openai/ },
  { vendor: 'deepseek', pattern: /deepseek/ },
  { vendor: 'qwen', pattern: /qwen|tongyi|dashscope|aliyun/ },
  { vendor: 'zhipu', pattern: /glm|cogview|zhipu|bigmodel/ },
  { vendor: 'moonshot', pattern: /moonshot|kimi/ },
  { vendor: 'baichuan', pattern: /baichuan/ },
  { vendor: 'mistral', pattern: /mistral|mixtral/ },
  { vendor: 'claude', pattern: /claude|anthropic/ },
  { vendor: 'gemini', pattern: /gemini|google|generativelanguage/ },
  { vendor: 'hunyuan', pattern: /hunyuan/ },
  { vendor: 'spark', pattern: /spark|xfyun|iflytek/ },
  { vendor: 'yi', pattern: /(^|[^a-z0-9])yi-|01\.ai/ },
  { vendor: 'minimax', pattern: /minimax|hailuo/ },
  { vendor: 'baai', pattern: /(^|[^a-z0-9])bge(-|$)|baai/ },
  { vendor: 'doubao', pattern: /doubao|volc|bytedance/ },
  { vendor: 'stepfun', pattern: /stepfun|^step(-|$)/ },
  { vendor: 'meta', pattern: /llama|^meta(-|$)|meta\./ },
  { vendor: 'groq', pattern: /groq/ },
  { vendor: 'perplexity', pattern: /perplexity|pplx/ },
]

/**
 * 根据模型 ID 或服务商地址识别厂商。
 * 无法识别时返回 null（调用方用首字母/默认图标兜底）。
 */
export function detectVendor(modelIdOrUrl: string | null | undefined): VendorId | null {
  const value = (modelIdOrUrl ?? '').toLowerCase()
  if (!value) return null
  for (const rule of VENDOR_RULES) {
    if (rule.pattern.test(value)) return rule.vendor
  }
  return null
}

export function getVendor(id: string | null | undefined): Vendor | null {
  if (!id) return null
  return VENDORS.find(vendor => vendor.id === id) ?? null
}

export type Capability = 'chat' | 'embedding' | 'rerank'

/** 能力值的中文显示映射 */
export const CAPABILITY_LABELS: Record<Capability, string> = {
  chat: '对话',
  embedding: '向量化',
  rerank: '重排序',
}

/** 按模型 ID 猜测能力：含 embedding/bge → 向量化；含 rerank → 重排序；其余对话 */
export function guessCapability(modelId: string): Capability {
  const value = modelId.toLowerCase()
  if (value.includes('embedding') || value.includes('bge')) return 'embedding'
  if (value.includes('rerank')) return 'rerank'
  return 'chat'
}

/** 已知向量模型的维度，用于拉取模型时自动填充 */
export const KNOWN_DIMENSIONS: Record<string, number> = {
  'text-embedding-3-small': 1536,
  'text-embedding-3-large': 3072,
  'text-embedding-ada-002': 1536,
  'bge-m3': 1024,
  'bge-large-zh-v1.5': 1024,
  'bge-large-en-v1.5': 1024,
  'bge-base-zh-v1.5': 768,
  'embedding-3': 2048,
  'embedding-2': 1536,
  'text-embedding-v1': 1536,
  'text-embedding-v2': 1536,
  'text-embedding-v3': 1024,
}
