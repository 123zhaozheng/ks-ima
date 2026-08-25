import { mutators } from 'app/src-shared/mutators'
import type { FullChat } from 'app/src-shared/queries'
import { mutate } from 'src/utils/zero-session'

export function getNameAvatar(text: string) {
  const [emoji, ...rest] = text.split(' ')
  if ([...emoji].length === 1) {
    return { name: rest.join(' '), avatar: { type: 'text' as const, text: emoji } }
  }
  return { name: text }
}

function titleMessages(chat: FullChat) {
  return chat.messages.slice(-6).filter(message => message.text?.trim()).map(message => ({
    role: message.type === 'chat:assistant' ? 'assistant' as const : 'user' as const,
    content: message.text ?? '',
  }))
}

/** Title generation is a centrally assigned server workflow, never a browser SDK call. */
export async function generateChatTitle({ chat }: { chat: FullChat, conf: unknown }) {
  const response = await fetch('/api/v1/chat/titles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Workspace-Id': chat.rootId },
    credentials: 'include',
    body: JSON.stringify({
      stream: false,
      messages: [
        { role: 'system', content: 'Return only a concise title for this conversation.' },
        ...titleMessages(chat),
      ],
    }),
  })
  if (!response.ok) throw new Error('Managed title capability is unavailable')
  const payload = await response.json() as { choices?: Array<{ message?: { content?: string } }> }
  const title = payload.choices?.[0]?.message?.content?.trim()
  if (!title) return
  await mutate(mutators.updateEntity({ id: chat.id, name: title.slice(0, 160) })).client
}
