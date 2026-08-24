import { chunkText } from 'app/src-shared/kb-settings'

/** PRD: 400–800 chars per chunk, 50–100 overlap. Configurable per workspace. */
export function splitChunks(text: string, target = 600, overlap = 80): string[] {
  return chunkText(text, target, overlap)
}
