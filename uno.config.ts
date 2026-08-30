import { Hct, hexFromArgb } from '@material/material-color-utilities'
import presetRemToPx from '@unocss/preset-rem-to-px'
import { defineConfig, presetAttributify, presetWind3, transformerDirectives, transformerVariantGroup } from 'unocss'

// UnoCSS palette mapped onto the fixed design tokens in src/styles/tokens.css.
// Utility names keep their legacy --a-* era spelling; only the variables moved.
const textColors = {
  pri: 'var(--tk-accent)',
  sec: 'var(--tk-text-secondary)',
  ter: 'var(--tk-accent)',
  err: 'var(--tk-danger)',
  suc: 'var(--tk-success)',
  warn: 'var(--tk-warning)',
  'pri-var': 'var(--tk-accent-hover)',
  'on-pri': '#ffffff',
  'on-sec': '#ffffff',
  'on-ter': '#ffffff',
  'on-err': '#ffffff',
  'on-pri-c': 'var(--tk-accent)',
  'on-sec-c': 'var(--tk-accent)',
  'on-ter-c': 'var(--tk-accent)',
  'on-err-c': 'var(--tk-danger)',
  'on-sur': 'var(--tk-text)',
  'on-sur-var': 'var(--tk-text-secondary)',
  out: 'var(--tk-border-strong)',
  'out-var': 'var(--tk-border)',
  'inv-on-sur': '#ffffff',
  'inv-pri': 'var(--tk-accent-hover)',
}

const bgColors = {
  pri: 'var(--tk-accent)',
  sec: 'var(--tk-text-secondary)',
  ter: 'var(--tk-accent)',
  err: 'var(--tk-danger)',
  'pri-c': 'var(--tk-accent-soft)',
  'sec-c': 'var(--tk-accent-soft)',
  'ter-c': 'var(--tk-accent-soft)',
  'err-c': 'var(--tk-danger-soft)',
  'sur-dim': 'var(--tk-surface-deep)',
  sur: 'var(--tk-bg)',
  'sur-bri': 'var(--tk-bg)',
  'sur-c-lowest': 'var(--tk-bg)',
  'sur-c-low': 'var(--tk-surface)',
  'sur-c': 'var(--tk-surface)',
  'sur-c-high': 'var(--tk-surface-deep)',
  'sur-c-highest': 'var(--tk-surface-deep)',
  out: 'var(--tk-border-strong)',
  'out-var': 'var(--tk-border)',
  'inv-sur': 'var(--tk-text)',
  'inv-pri': 'var(--tk-accent-hover)',
}

export default defineConfig({
  theme: {
    colors: {
      ...textColors,
      ...bgColors,
    },
    breakpoints: {
      xs: '0px',
      sm: '600px',
      md: '1024px',
      lg: '1440px',
      xl: '1920px',
    },
  },
  presets: [
    presetWind3({ dark: { light: '.body--light', dark: '.body--dark' } }),
    presetAttributify(),
    presetRemToPx(),
  ],
  rules: [
    ['icon-fill', { 'font-variation-settings': "'FILL' 1" }],
    ['icon-unfill', { 'font-variation-settings': "'FILL' 0" }],
    ['break-word', { 'word-break': 'break-word' }],
    [/^(text|bg)-(\d+)-(\d+)-(\d+)$/, ([, type, h, c, t]) => ({
      [type === 'text' ? 'color' : 'background-color']: hexFromArgb(Hct.from(+h, +c, +t).toInt()),
    })],
    [/^bg-gradient-(top|bottom|left|right)-(w|b)$/, ([, pos, color]) => {
      const rgb = color === 'w' ? '255 255 255' : '0 0 0'
      return {
        background: `linear-gradient(to ${pos}, rgb(${rgb} / 0%) 0%, rgb(${rgb} / 5%) 20%, rgb(${rgb} / 30%) 100%)`,
      }
    }],
  ],
  shortcuts: [
    [
      /^(text|bg)-(\d+)-(\d+)-(\d+)-a$/,
      ([, type, h, c, t]) => `light:${type}-${h}-${c}-${t} dark:${type}-${h}-${c}-${Math.min(110 - +t, 100)}`,
    ],
    [
      /^bg-gradient-(top|bottom|left|right)-a$/,
      ([, pos]) => `light:bg-gradient-${pos}-w dark:bg-gradient-${pos}-b`,
    ],
    ['item-rd', 'rd my-1 of-hidden'],
    ['pri-link', 'text-pri decoration-none transition-color duration-250 hover:text-pri-var cursor-pointer'],
    ['route-active', 'bg-sec-c text-on-sec-c icon-fill'],
    ['view-styles', 'h-full flex-1 min-w-0'],
    ['shadow-default', 'shadow-md shadow-black shadow-op-20'],
  ],
  safelist: [
    ...Object.keys(textColors).map(x => `text-${x}`),
    ...Object.keys(bgColors).map(x => `bg-${x}`),
  ],
  transformers: [
    transformerDirectives(),
    transformerVariantGroup(),
  ],
})
