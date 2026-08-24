import { unzipSync, strFromU8 } from 'fflate'
import { log } from '../utils/functions'

export interface ParsedFile {
  text: string
  language: string
}

const mimeTypes = {
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  pdf: 'application/pdf',
}

function mimeFromName(name?: string | null) {
  const ext = name?.split('.').pop()?.toLowerCase()
  if (ext === 'docx') return mimeTypes.docx
  if (ext === 'pptx') return mimeTypes.pptx
  if (ext === 'xlsx' || ext === 'xls') return mimeTypes.xlsx
  if (ext === 'pdf') return mimeTypes.pdf
  if (ext === 'md' || ext === 'markdown') return 'text/markdown'
  if (ext === 'html' || ext === 'htm') return 'text/html'
  if (ext === 'txt' || ext === 'csv' || ext === 'json' || ext === 'xml') return 'text/plain'
}

function cellText(c: unknown) {
  if (typeof c === 'string' || typeof c === 'number' || typeof c === 'boolean') return String(c)
  return ''
}

function rowsToMarkdown(rows: unknown[][]) {
  if (!rows.length) return ''
  const head = rows[0].map(cellText)
  const body = rows.slice(1).map(r => r.map(cellText))
  const headerLine = '| ' + head.join(' | ') + ' |'
  const sepLine = '| ' + head.map(() => '---').join(' | ') + ' |'
  const bodyLines = body.map(r => '| ' + r.join(' | ') + ' |')
  return [headerLine, sepLine].concat(bodyLines).join('\n')
}

async function parseDocx(buf: ArrayBuffer) {
  const mammoth = await import('mammoth')
  const result = await mammoth.extractRawText({ buffer: Buffer.from(buf) })
  return { text: result.value, language: 'text' }
}

async function parseXlsx(buf: ArrayBuffer) {
  const { read, utils } = await import('xlsx-republish')
  const workbook = read(buf)
  const result = workbook.SheetNames.map(name => {
    const markdown = rowsToMarkdown(utils.sheet_to_json(workbook.Sheets[name], { header: 1 }))
    return `**${name}:**\n${markdown}`
  }).join('\n\n')
  return { text: result, language: 'markdown' }
}

function parsePptx(buf: ArrayBuffer) {
  const files = unzipSync(new Uint8Array(buf))
  const slideFileNames = Object.keys(files).filter(name =>
    /^ppt\/slides\/slide\d+\.xml$/.test(name),
  ).sort((a, b) => parseInt(a.match(/\d+/)![0]) - parseInt(b.match(/\d+/)![0]))
  const texts = slideFileNames.map(name => {
    const xmlStr = strFromU8(files[name])
    return [...xmlStr.matchAll(/<a:t[^>]*>([^<]*)<\/a:t>/g)].map(m => m[1]).join('')
  })
  return { text: texts.join('\n\n---\n\n'), language: 'text' }
}

async function parsePdf(buf: ArrayBuffer) {
  const pdfjs = await import('pdfjs-dist/legacy/build/pdf.mjs')
  pdfjs.GlobalWorkerOptions.workerSrc = import.meta.resolve('pdfjs-dist/legacy/build/pdf.worker.mjs')
  const doc = await pdfjs.getDocument({
    data: new Uint8Array(buf),
    isEvalSupported: false,
    useSystemFonts: true,
  }).promise
  const pages: string[] = []
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i)
    const content = await page.getTextContent()
    pages.push(content.items.map((item: any) => item.str ?? '').join(' '))
  }
  return { text: pages.join('\n\n'), language: 'text' }
}

export async function parseFileBytes(buf: ArrayBuffer, mimeType?: string | null, name?: string | null): Promise<ParsedFile | undefined> {
  const type = mimeType || mimeFromName(name) || ''
  try {
    if (type === mimeTypes.docx || name?.toLowerCase().endsWith('.docx')) return parseDocx(buf)
    if (type === mimeTypes.pptx || name?.toLowerCase().endsWith('.pptx')) return parsePptx(buf)
    if (type === mimeTypes.xlsx || type.includes('spreadsheet') || name?.toLowerCase().endsWith('.xlsx')) return parseXlsx(buf)
    if (type === mimeTypes.pdf || name?.toLowerCase().endsWith('.pdf')) return parsePdf(buf)
    if (type.startsWith('text/') || type === 'application/json' || type === 'text/markdown') {
      return { text: new TextDecoder().decode(buf), language: type.includes('markdown') ? 'markdown' : 'text' }
    }
    if (type.startsWith('image/') || type.startsWith('video/') || type.startsWith('audio/')) {
      return undefined
    }
    const decoded = new TextDecoder().decode(buf)
    if (decoded.trim()) return { text: decoded, language: 'text' }
  } catch (err) {
    log(`parseFileBytes failed for ${String(name)}: ${String(err)}`)
    throw err
  }
}
