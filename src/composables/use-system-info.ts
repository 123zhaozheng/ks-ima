import { useQuery } from '@tanstack/vue-query'
import { imaClient } from 'src/api/ima-client'

export function useSystemInfo() {
  return useQuery({
    queryKey: ['ima', 'system-info'],
    queryFn: ({ signal }) => imaClient.getSystemInfo(signal),
  })
}
