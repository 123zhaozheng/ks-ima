import { unzipSync, strFromU8 } from 'fflate'
import { t } from './i18n'

export interface ParseTextResult {
  text?: string
  language?: string
}

export interface ParseResult extends ParseTextResult {
  name: string
  blob?: Blob
}

export interface FileParser {
  label: string
  caption?: string
  rangeInput?: {
    label?: string
    placeholder?: string
    mask?: string
  }
  acceptTypes: string[]
  execute(file: File, options: {
    withFile: boolean
    range?: string | null
  }): Promise<ParseResult[]>
}

async function parseDocx(file: File, { withFile, withImages }: {
  withFile: boolean
  withImages: boolean
}): Promise<ParseResult[]> {
  const mammoth = await import('mammoth')
  const arrayBuffer = await file.arrayBuffer()
  const images: ParseResult[] = []
  let count = 0
  const result = await mammoth.convertToHtml({ arrayBuffer }, {
    convertImage: mammoth.images.imgElement(async (image) => {
      count++
      withImages && images.push({
        name: ` ${file.name} - image ${count}.${image.contentType.split('/')[1]}`,
        blob: new Blob([await image.readAsArrayBuffer()], { type: image.contentType }),
      })
      return { src: '#', title: `image-${count}` }
    }),
  })
  return [{
    name: file.name,
    text: result.value,
    language: 'html',
    blob: withFile ? file : undefined,
  }, ...images]
}
async function parseDocxText(file: Blob): Promise<ParseTextResult> {
  const mammoth = await import('mammoth')
  const arrayBuffer = await file.arrayBuffer()
  const result = await mammoth.convertToHtml({ arrayBuffer })
  return {
    text: result.value,
    language: 'html',
  }
}

function rowsToMarkdown(rows) {
  if (!rows.length) return ''
  const head = rows[0].map(c => c == null ? '' : String(c))
  const body = rows.slice(1).map(r =>
    r.map(c => c == null ? '' : String(c)),
  )
  const headerLine = '| ' + head.join(' | ') + ' |'
  const sepLine = '| ' + head.map(() => '---').join(' | ') + ' |'
  const bodyLines = body.map(r => '| ' + r.join(' | ') + ' |')
  return [headerLine, sepLine].concat(bodyLines).join('\n')
}
async function parseXlsx(file: Blob): Promise<ParseTextResult> {
  const { read, utils } = await import('xlsx-republish')
  const workbook = read(await file.arrayBuffer())
  const result = workbook.SheetNames.map(name => {
    const markdown = rowsToMarkdown(utils.sheet_to_json(workbook.Sheets[name], { header: 1 }))
    return `**${name}:**\n${markdown}`
  }).join('\n\n')
  return {
    text: result,
    language: 'markdown',
  }
}

async function parsePptx(file: Blob, pages?: number[]): Promise<ParseTextResult> {
  const uint8 = new Uint8Array(await file.arrayBuffer())
  const files = unzipSync(uint8)

  const slideFileNames = Object.keys(files).filter(name =>
    /^ppt\/slides\/slide\d+\.xml$/.test(name),
  ).sort((a, b) => parseInt(a.match(/\d+/)![0]) - parseInt(b.match(/\d+/)![0]))

  const texts = slideFileNames.map(name => {
    const xmlStr = strFromU8(files[name])
    const doc = new DOMParser().parseFromString(xmlStr, 'application/xml')
    const textNodes = Array.from(doc.getElementsByTagName('a:p'))
    return textNodes.map(node => node.textContent).join('\n')
  })

  return {
    text: (pages ? pages.map(i => texts[i]) : texts).join('\n\n---\n\n'),
    language: 'text',
  }
}

async function extractPdfText(file: Blob, pages?: number[]): Promise<ParseTextResult> {
  const { extractText } = await import('./pdf')
  const { text } = await extractText(await file.arrayBuffer())
  return {
    text: (pages ? pages.map(i => text[i]) : text).join('\n\n'),
    language: 'text',
  }
}

async function renderPdfImages(file: Blob, pages?: number[]) {
  const { getDocumentProxy, renderPageAsImage } = await import('./pdf')
  const pdf = await getDocumentProxy(await file.arrayBuffer())
  pages ??= Array.from({ length: pdf.numPages }, (_, i) => i)
  return await Promise.all(pages.map(async i => ({
    page: i + 1,
    image: await renderPageAsImage(pdf, i + 1, { height: 1440 }),
  })))
}

function parsePageRange(range: string) {
  return range.split(',').map(r => {
    const [start, end = start] = r.split('-').map(Number)
    const pages: number[] = []
    for (let i = start; i <= end; i++) {
      pages.push(i)
    }
    return pages
  }).flat().map(p => p - 1)
}

const pageRangeInput = {
  label: t('Page Range'),
  placeholder: 'e.g. 1-3,5',
}
const mimeTypes = {
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  pdf: 'application/pdf',
}
export const fileParsers: FileParser[] = [
  {
    label: t('Docx parsing'),
    acceptTypes: [mimeTypes.docx],
    async execute(file, { withFile }) {
      return await parseDocx(file, { withFile, withImages: true })
    },
  },
  {
    label: t('PPTX parsing'),
    acceptTypes: [mimeTypes.pptx],
    rangeInput: pageRangeInput,
    async execute(file, { withFile, range }) {
      return [{
        name: file.name,
        blob: withFile ? file : undefined,
        ...await parsePptx(file, range ? parsePageRange(range) : undefined),
      }]
    },
  },
  {
    label: t('XLSX parsing'),
    acceptTypes: [mimeTypes.xlsx],
    async execute(file, { withFile }) {
      return [{
        name: file.name,
        blob: withFile ? file : undefined,
        ...await parseXlsx(file),
      }]
    },
  },
  {
    label: t('Extract PDF Text'),
    caption: t('Extract text content from PDF'),
    acceptTypes: [mimeTypes.pdf],
    rangeInput: pageRangeInput,
    async execute(file, { withFile, range }) {
      return [{
        name: file.name,
        blob: withFile ? file : undefined,
        ...await extractPdfText(file, range ? parsePageRange(range) : undefined),
      }]
    },
  },
  {
    label: t('PDF Screenshot'),
    caption: t('Screenshot PDF content as images'),
    acceptTypes: [mimeTypes.pdf],
    rangeInput: pageRangeInput,
    async execute(file, { withFile, range }) {
      const images = await renderPdfImages(file, range ? parsePageRange(range) : undefined)
      const res = images.map(({ page, image }) => ({
        name: `${file.name} - ${page}`,
        blob: image,
      }))
      if (withFile) {
        res.unshift({
          name: file.name,
          blob: file,
        })
      }
      return res
    },
  },
]

function mimeFromName(name?: string) {
  const ext = name?.split('.').pop()?.toLowerCase()
  if (ext === 'docx') return mimeTypes.docx
  if (ext === 'pptx') return mimeTypes.pptx
  if (ext === 'xlsx' || ext === 'xls') return mimeTypes.xlsx
  if (ext === 'pdf') return mimeTypes.pdf
  if (ext === 'md' || ext === 'markdown') return 'text/markdown'
  if (ext === 'txt' || ext === 'csv' || ext === 'json' || ext === 'xml' || ext === 'html') return 'text/plain'
}

export async function parseText(file: Blob & { name?: string }): Promise<ParseTextResult | undefined> {
  const type = file.type || mimeFromName(file.name) || ''
  if (type === mimeTypes.docx) return parseDocxText(file)
  if (type === mimeTypes.pptx) return parsePptx(file)
  if (type === mimeTypes.xlsx) return parseXlsx(file)
  if (type === mimeTypes.pdf) return extractPdfText(file)
  if (type.startsWith('text/') || type === 'application/json') {
    const text = await file.text()
    return { text, language: 'text' as const }
  }
}
