export type Avatar = {
  type: 'svg'
  name: string
  hue?: number
} | {
  type: 'text'
  text: string
  hue?: number
} | {
  type: 'icon'
  icon: string
  hue?: number
} | {
  type: 'url'
  url: string
  hue?: number
}
