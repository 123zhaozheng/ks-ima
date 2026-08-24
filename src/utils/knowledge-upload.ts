import { mutators } from 'app/src-shared/mutators'
import { genId } from 'app/src-shared/utils/id'
import { Notify } from 'quasar'
import { t } from './i18n'
import { upload } from './blob-cache'
import { mutate } from './zero-session'

type Dropped = { file: File, relativePath: string }

function dirname(path: string) {
  const normalized = path.replace(/\\/g, '/')
  const i = normalized.lastIndexOf('/')
  return i <= 0 ? '' : normalized.slice(0, i)
}

async function walkEntry(entry: FileSystemEntry, prefix: string, out: Dropped[]): Promise<void> {
  const path = prefix ? `${prefix}/${entry.name}` : entry.name
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => {
      (entry as FileSystemFileEntry).file(resolve, reject)
    })
    out.push({ file, relativePath: path })
    return
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader()
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject)
    })
    for (const child of batch) await walkEntry(child, path, out)
  }
}

export async function filesFromDrop(dataTransfer: DataTransfer): Promise<Dropped[]> {
  const items = Array.from(dataTransfer.items)
  const canWalk = items.some(item => typeof item.webkitGetAsEntry === 'function' && item.webkitGetAsEntry())
  if (canWalk) {
    const out: Dropped[] = []
    for (const item of items) {
      const entry = item.webkitGetAsEntry()
      if (entry) await walkEntry(entry, '', out)
    }
    if (out.length) return out
  }
  return Array.from(dataTransfer.files).map(file => ({
    file,
    relativePath: file.webkitRelativePath || file.name,
  }))
}

export function selectFolder(callback: (files: Dropped[]) => void) {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.setAttribute('webkitdirectory', '')
  input.onchange = (e: Event) => {
    const files = Array.from((e.target as HTMLInputElement).files ?? [])
    callback(files.map(file => ({
      file,
      relativePath: file.webkitRelativePath || file.name,
    })))
  }
  input.click()
}

async function ensureFolderPath(rootParentId: string, relativePath: string, cache: Map<string, string>) {
  const dir = dirname(relativePath)
  if (!dir) return rootParentId
  if (cache.has(dir)) return cache.get(dir)!
  let parentId = rootParentId
  let acc = ''
  for (const name of dir.split('/').filter(Boolean)) {
    acc = acc ? `${acc}/${name}` : name
    const cached = cache.get(acc)
    if (cached) {
      parentId = cached
      continue
    }
    const id = genId()
    await mutate(mutators.createFolder({
      id,
      parentId,
      name,
    })).client
    cache.set(acc, id)
    parentId = id
  }
  return parentId
}

export async function uploadKnowledge(parentId: string, dropped: Dropped[]) {
  if (!dropped.length) return
  const folderCache = new Map<string, string>()
  for (const { file, relativePath } of dropped) {
    const id = genId()
    const folderId = await ensureFolderPath(parentId, relativePath, folderCache)
    const wait = mutate(mutators.createItem({
      id,
      parentId: folderId,
      name: file.name,
      mimeType: file.type || undefined,
    })).server
    upload(id, file, file.name, wait)
  }
  Notify.create(t('Added {p0 file}; parsing starts automatically. Check progress under Tasks in the sidebar.', dropped.length))
}
