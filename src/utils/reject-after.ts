export function rejectAfter(ms: number, message = 'timeout'): Promise<never> {
  return new Promise((resolve, reject) => {
    setTimeout(() => reject(new Error(message)), ms)
  })
}
