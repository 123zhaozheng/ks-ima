# Research: Apple Design Language for the Frontend UX Overhaul

- **Query**: Produce an actionable Apple-style ("高端大气": calm, spacious, refined) design-language spec for the Vue3+Quasar intranet knowledge assistant, mappable to `--tk-*` CSS tokens, Chrome 109 compatible.
- **Scope**: external (Apple HIG, apple.com teardowns, caniuse) + internal (`src/styles/tokens.css`, `.trellis/spec/frontend/ux-design-language.md`)
- **Date**: 2025-05-18

---

## 0. Positioning: marketing apple.com vs. a product web app

apple.com is a photography-first marketing site (near-zero chrome, alternating
light/dark full-bleed tiles). Our app is a **product tool** (iCloud/Mail-like),
so we take the *grammar* — whitespace, hairlines, restrained accent, tight
display type, pill CTAs — and apply it with HIG product patterns (lists,
sidebars, toolbars). Rule of thumb: **apple.com decides color/type/button
vocabulary; the HIG decides density, layout and component behavior.**

The current theme (Semi-inspired: `#0077fa` accent, rgba(0,0,0,.85) text,
4/6/8px radii, boxed bordered cards — `src/styles/tokens.css`) reads flat and
slightly saturated. The Apple move is: warmer near-white grounds, true-neutral
ink text (`#1d1d1f`), one action-blue used sparingly, larger radii, depth via
whitespace + hairlines instead of borders on everything.

---

## 1. Typography

### Font stack (SF Pro characteristics → web-safe)

SF Pro is a neo-grotesque (Helvetica/DIN lineage) with variable optical sizes:
SF Pro Text ≤ 19px, SF Pro Display ≥ 20px (developer.apple.com/fonts;
learnui.design). It cannot be licensed for a web app, so use the system stack
(what apple.com properties fall back to on Windows):

```css
--tk-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
  "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB",
  "Microsoft YaHei", sans-serif;
```

`Segoe UI` on Windows is the workhorse; it behaves like SF Pro at UI sizes.
Keep ONE family; hierarchy comes from weight/size/color, never a second face.

### Size ramp (px for web; HIG pt values 1:1 at 1x)

From apple.com teardown + HIG text styles (eonist gist; HIG typography page):

| Token | Size | Weight | Line-height | Letter-spacing | Use |
|---|---|---|---|---|---|
| `--tk-font-large-title` | 28px (up to 34px on roomy pages) | 600 | 1.15–1.2 | -0.022em (-0.6px) | Page "large title" (macOS/iOS style) |
| `--tk-font-title-1` | 22px | 600 | 1.25 | -0.018em | Section titles |
| `--tk-font-title-2` | 17px | 600 | 1.3 | -0.022em | Card/panel headers, HIG Headline |
| `--tk-font-body` | 17px (14px in dense lists/tables) | 400 | 1.47 (apple.com body) | -0.022em | Reading text; apple.com runs 17/1.47, NOT 16 |
| `--tk-font-callout` | 14px | 400 | 1.4 | -0.01em | Secondary descriptions, form labels |
| `--tk-font-caption` | 12px | 400 | 1.33 | 0 | Metadata, timestamps, nav labels |

Key Apple behaviors:

- **Negative tracking at ≥ 17px only** ("Apple tight" headline cadence,
  -0.12 → -0.374px ≈ -0.022em). Never tighten ≤ 12px (VoltAgent DESIGN.md).
- **Weight ladder 400/600, occasional 300/700. Skip 500.** Body always 400,
  emphasis 600; 700 reserved for OS chrome, rarely marketing. Headings are
  **semibold (600)**, not bold.
- HIG iOS reference: Large Title 34pt, Title1 28pt, Title2 22pt, Title3 20pt
  (semibold), Headline 17pt semibold, Body 17pt, Footnote 13pt, Caption 12pt.
- Min body/legible text 12px; target ≥ 4.5:1 contrast (HIG checklist).
- Tabular numerals (`font-variant-numeric: tabular-nums`) for prices/times —
  supported everywhere, Chrome 109 fine.

---

## 2. Color

Apple's web palette (mobbin.com/colors/brand/apple; webdesignhot DESIGN.md;
apple.com computed styles):

| Role | Apple value | Notes |
|---|---|---|
| Page ground | `#fbfbfd` | Near-white with the faintest cool lift; also `#ffffff` |
| Alternate ground / insets | `#f5f5f7` | "Athens Gray" — panels, input fills, hover base |
| Feature card fill | `#fafafc` | Barely-there card fill instead of stroke/shadow |
| Primary text | `#1d1d1f` | "Shark" — near-black, NOT pure black |
| Secondary text | `#6e6e73` | Subtitles, descriptions |
| Tertiary text | `#86868b` (on light), `#a1a1a6` | Footnotes, placeholders |
| Hairline | `#d2d2d7` solid 1px or `rgba(0,0,0,0.08–0.12)` | Inputs use `#d2d2d7`; dividers often rgba |
| Action blue | `#0071e3` (`--sk-fill-blue`) | Buttons only; hover `#0077ed`, pressed `#006edb` |
| Link blue | `#0066cc` | Inline "Learn more ›" links on light grounds |
| Link blue on dark | `#2997ff` | Not needed for our light app |

Semantic (HIG system colors, light): red `#ff3b30` (errors), orange `#ff9500`
(warning), green `#34c759` fill / `#248a3d` text-on-light (success), blue
`#007aff` (system). For an intranet tool prefer the darker text-legible
variants: danger `#d70015`/`#ff3b30`, success `#248a3d`, warning `#b25000`
for text, `#ff9500` for fills.

**Accent discipline**: ONE blue. It appears on primary CTAs, active nav item,
focus rings, and the occasional meaningful link. Never as background washes,
headers, or icon decoration. "Color never carries meaning alone" (HIG).

---

## 3. Shape & depth

### Radii (upgrade from current 4/6/8)

| Token | Value | Use |
|---|---|---|
| `--tk-radius-sm` | 8px | Small controls, chips, tags |
| `--tk-radius` | 12px | Inputs, list cards, dialogs (small) |
| `--tk-radius-lg` | 18px | Feature cards, panels (Apple TV+ tiles use 12–18px) |
| `--tk-radius-pill` | 980px | Primary CTA buttons (Apple's literal value — finite so wide buttons soften instead of stadium-shaping), search fields, pill chips |

### Shadows — "depth is in the gutter"

apple.com uses **near-zero shadow**; panels separate by ground-color change
alone (`#fafafc` between `#ffffff` panels). The only chrome shadow is the
search overlay. Product imagery gets one signature shadow
(`rgba(0,0,0,0.22) 3px 5px 30px`) — never cards/buttons/text.

For a product app, keep shadows whisper-quiet and layered:

```css
--tk-shadow-sm: 0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.03);
--tk-shadow-md: 0 2px 8px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06); /* popovers, dialogs */
--tk-shadow-lg: 0 4px 12px rgba(0,0,0,0.05), 0 16px 40px rgba(0,0,0,0.08); /* floating panels */
```

Prefer **ground-color alternation + hairlines** over shadows for separation.

### Translucency / blur

Where Apple uses it: global nav (`rgba(22,22,23,0.8)` + `backdrop-filter:
saturate(180%) blur(20px)`), macOS sidebars/toolbars (translucent gray
materials), overlays. For us: optional frosted header on scroll
(`rgba(251,251,253,0.8)` + `blur(20px) saturate(180%)`) and dialogs.
**`backdrop-filter` is supported unprefixed since Chrome 76** (caniuse,
web.dev) — safe on Chrome 109. Always pair with a semi-transparent background
(opaque bg makes the effect invisible); keep blur areas few (perf).

### Borderless sections

Separate with whitespace (24–80px gutters) and 1px hairlines, not boxes.
"Don't box everything in cards" is the core Apple move.

---

## 4. Components

### Buttons

- **Primary CTA (the apple.com "Buy" pill)**: `#0071e3` fill, white text,
  14–17px/400, padding `11px 21px`, height ~40–44px, radius **980px**.
  Hover: fill → `#0077ed`. Pressed: fill → `#006edb`. **No transform, no
  shadow** on marketing pills; for a product app an optional
  `transform: scale(0.98)` press is acceptable (DESIGN.md cites scale(0.95)
  as the system-wide micro-interaction) — pick one language and stay
  consistent. Transition 200ms.
  Quasar: `q-btn` with `unelevated` + `rounded` + custom class; override
  Quasar's default radius.
- **Secondary**: hairline border `#d2d2d7` on white, radius 980px, text
  `#1d1d1f`; hover fill `#f5f5f7`.
- **Tertiary / borderless**: text-only `#0066cc` link buttons ("Learn more ›"
  with chevron); underline appears/grows only on hover over ~200ms. Icon-only
  buttons: no border, hover = `rgba(0,0,0,0.04)` round fill.
- One primary action per view; targets ≥ 44px hit area (HIG).
- Disabled: opacity ~0.4 or `rgba(0,0,0,0.12)` fill, never a new hue.

### Inputs

- Height 44–48px, radius 10–12px (product-app adaptation; apple.com account
  forms use sharper 1px `#d2d2d7` borders — fine but less "premium" at app
  density). Two good skins, pick one per surface and stay consistent:
  1. **Fill**: background `#f5f5f7`, transparent border; focus → white bg +
     accent ring.
  2. **Outline**: white bg, 1px `#d2d2d7`; hover border darkens to `#b0b0b5`.
- **Focus ring**: `box-shadow: 0 0 0 3-4px rgba(0,113,227,0.25)` + border
  `#0071e3` (macOS-style). Never rely on `outline` removal only — replace it.
- Labels above field, 14px `#6e6e73`; helper/error text 12px below.
  Quasar: `q-input` `outlined` + `dense` off; set via `.q-field__control`
  overrides.

### Cards

- White card on `#f5f5f7` ground with hairline, **or** `#fafafc`/`#f5f5f7`
  fill card on white ground with NO border and NO shadow. Radius 12–18px.
  Padding generous (20–28px). Hover (if interactive): slightly darker fill or
  the faintest shadow-sm — never a border color change.

### Lists

- Roomy rows: 44–56px (up from our 36–40px). Row content: leading icon in a
  soft squircle tint (optional), title 14–17px `#1d1d1f`, subtitle 12–13px
  `#6e6e73`, trailing metadata `#86868b`.
- **Hover = subtle fill** (`rgba(0,0,0,0.03–0.05)` or `#f5f5f7`), radius the
  row or inset 8px. NEVER hover with border/outline. Selected =
  `rgba(0,113,227,0.08)` tint or accent-soft.
- Dividers: inset hairlines `rgba(0,0,0,0.08)` starting after the leading
  icon (iOS style); or no dividers + 8px gaps (most Apple).

### Nav sidebar / rail

macOS Finder-style: translucent neutral ground
(`rgba(246,246,246,0.8)` + `backdrop-filter: blur(20px)` over content, or
solid `#f5f5f7` fallback), width 220–260px. Items: 36–40px rows, 13–14px
labels `#1d1d1f`, icons 18–20px in `#6e6e73` (weight-matched to text),
radius 8px. Active item: `rgba(0,0,0,0.05–0.08)` fill (macOS) or
accent-soft + accent text (iOS Settings style) — pick one; macOS gray is the
calmer, more "premium" choice, accent for wayfinding. Section labels: 11px
uppercase or semibold `#86868b`. Hairline `rgba(0,0,0,0.08)` between rail and
content — no shadow.

### Toolbar / header ("large title")

- **Large title pattern** (iOS/macOS): page title 28–34px semibold, tight
  tracking, left-aligned, 24–32px top padding; actions right. On scroll it can
  collapse into a compact 44–52px frosted bar (`rgba(251,251,253,0.8)` +
  blur) with a 17px semibold title.
- Headers have NO bottom border unless compacted; whitespace separates.
- Global top bar (if any) 44–48px, like apple.com global nav: quiet 12–14px
  links ~20px apart.

---

## 5. Motion & micro-interactions

- Durations **200–300ms** (hover color swaps ~150–200ms; dialogs/panels
  250–350ms). No bounce, no overshoot, no rotation.
- Easing (from apple.com teardown):
  - Standard: `cubic-bezier(0.4, 0, 0.2, 1)` — hovers, dropdown reveal.
  - Emphasized/decelerate: `cubic-bezier(0.16, 1, 0.3, 1)` — modal/panel
    entry (Apple's signature curve).
  - Exit: `cubic-bezier(0, 0, 0.2, 1)`.
- Press feedback: color shift (primary) or `transform: scale(0.95–0.98)` on
  press, spring back on release.
- Underlines grow in over ~200ms; chevrons translate-x 2px on hover.
- Honor `prefers-reduced-motion` (Chrome 74+) — HIG requires reduce-motion
  respect.

---

## 6. Empty states & first-run

HIG-aligned (brilworks checklist: "empty states include a clear next action"):

- Layout: vertically centered, max-width ~360–420px, generous padding.
- Anatomy: one calm icon or illustration (48–64px, monochrome `#86868b` or
  soft accent tint — not multicolored clip-art) → title 17–22px semibold
  `#1d1d1f` → one subtitle line 14px `#6e6e73` explaining the value →
  **single** pill CTA.
- Copy tone: welcoming, plain, second person, no jargon: "Start your first
  conversation" / "Ask anything in your workspace" / "Your notes will appear
  here." Short, optimistic, zero blame ("No results yet" not "Failed to
  find"). Never an empty white box with no guidance.

---

## 7. Token table (drop-in values for `src/styles/tokens.css`)

```css
:root {
  /* Surfaces */
  --tk-bg: #fbfbfd;              /* page ground */
  --tk-surface: #f5f5f7;         /* rail, insets, header base, input fill */
  --tk-surface-deep: #fafafc;    /* feature card fill on white */
  --tk-surface-white: #ffffff;   /* cards, dialogs, inputs-outline */

  /* Lines and text */
  --tk-border: rgba(0, 0, 0, 0.08);        /* hairlines, dividers */
  --tk-border-strong: #d2d2d7;             /* input/outline borders */
  --tk-text: #1d1d1f;
  --tk-text-secondary: #6e6e73;
  --tk-text-tertiary: #86868b;

  /* Accent (used sparingly) */
  --tk-accent: #0071e3;
  --tk-accent-hover: #0077ed;
  --tk-accent-active: #006edb;
  --tk-accent-soft: rgba(0, 113, 227, 0.08);
  --tk-link: #0066cc;
  --tk-focus-ring: rgba(0, 113, 227, 0.25);

  /* Status (HIG-derived, text-legible on light) */
  --tk-danger: #d70015;  --tk-danger-fill: #ff3b30;  --tk-danger-soft: rgba(255, 59, 48, 0.08);
  --tk-success: #248a3d; --tk-success-fill: #34c759;
  --tk-warning: #b25000; --tk-warning-fill: #ff9500; --tk-warning-soft: rgba(255, 149, 0, 0.1);

  /* Shape */
  --tk-radius-sm: 8px;
  --tk-radius: 12px;
  --tk-radius-lg: 18px;
  --tk-radius-pill: 980px;

  /* Spacing (keep 4/8pt scale; add roomier page-level steps) */
  --tk-space-1..8: 4/8/12/16/20/24/32px (unchanged);
  --tk-space-10: 40px;  --tk-space-12: 48px;  --tk-space-16: 64px;

  /* Shadows — whisper-light, layered */
  --tk-shadow-sm: 0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.03);
  --tk-shadow-md: 0 2px 8px rgba(0,0,0,0.04), 0 8px 24px rgba(0,0,0,0.06);
  --tk-shadow-lg: 0 4px 12px rgba(0,0,0,0.05), 0 16px 40px rgba(0,0,0,0.08);

  /* Type */
  --tk-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
  --tk-font-size-xs: 12px;   /* caption, nav */
  --tk-font-size-sm: 14px;   /* callout, labels, dense lists */
  --tk-font-size-md: 17px;   /* body, HIG Body/Headline */
  --tk-font-size-lg: 22px;   /* Title 1 */
  --tk-font-size-xl: 28px;   /* large title (up to 34px) */
  --tk-weight-regular: 400; --tk-weight-semibold: 600;  /* skip 500 */
  --tk-lh-tight: 1.2; --tk-lh-body: 1.47;
  --tk-tracking-display: -0.022em;  /* apply at ≥17px only */

  /* Controls */
  --tk-control-h: 40px;      /* buttons (44–48px for inputs) */
  --tk-row-h: 48px;          /* list rows (was 36–40px) */

  /* Motion */
  --tk-ease: cubic-bezier(0.4, 0, 0.2, 1);
  --tk-ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --tk-dur: 200ms; --tk-dur-slow: 300ms;
}
```

Quasar wiring (implementer notes): map `$primary: #0071e3`, `$dark`,
`$separator-color` to rgba(0,0,0,0.08); override `.q-btn` radius (pill for
primary via class), `.q-field__control` height/radius, `.q-item` min-height
48px + hover fill, `QHeader` frosted class. Keep all values in tokens.css,
reference tokens from the Quasar overrides — per existing spec §1, no
hardcoded palette colors in components.

---

## 8. Chrome 109 compatibility notes

| Feature | Status on Chrome 109 | Verdict |
|---|---|---|
| `backdrop-filter` (unprefixed) | **Chrome 76+** (caniuse; web.dev) | OK — no prefix needed; keep `-webkit-` copy only if Safari parity wanted |
| `:has()` | Chrome 105 | Technically OK, but repo spec keeps it out of app CSS (non-critical enhancement only) |
| `color-mix()`, `oklch()` | Chrome 111 | FORBIDDEN — pre-compute all tints as rgba tokens (as in table above) |
| CSS nesting | Chrome 112 | FORBIDDEN — flat selectors only |
| Container queries | Chrome 105 | Repo spec forbids; keep forbidden |
| `unprefixed background-clip: text` | needs `-webkit-` | keep existing policy |
| CSS custom properties, rgba(), letter-spacing, `tabular-nums`, `position: sticky` (76+), flex `gap` (84+), `:focus-visible` (86+), `prefers-reduced-motion` (74+), transform/transition, `aspect-ratio` (88+) | all fine | OK |
| JS `Array.toSorted/toReversed/toSpliced` | Chrome 110 | FORBIDDEN (existing policy) |

Everything proposed in §1–§7 is Chrome-109-safe: it uses only custom
properties, rgba tints, flat selectors, transform/transition, and
backdrop-filter (76+). The existing build gate grep
(`toSorted|toReversed|toSpliced|color-mix|@container|oklch`) stays valid.

---

## 9. DO / DON'T checklist (Quasar → Apple-grade)

**DO**
- DO use whitespace as the primary separator (24–64px between sections).
- DO keep one accent (`#0071e3`) for actions/focus/active nav only.
- DO set headings semibold 600 with -0.022em tracking at ≥17px.
- DO use body 17px/1.47 for reading surfaces; `#1d1d1f` ink, `#6e6e73` secondaries.
- DO prefer pill (980px) primary CTAs and borderless `#0066cc` text actions.
- DO hover lists/rows with a subtle fill (`rgba(0,0,0,0.03–0.05)`), rounded.
- DO separate with hairlines `rgba(0,0,0,0.08)` + ground alternation
  (`#fbfbfd` / `#f5f5f7` / white cards).
- DO give every empty state icon + title + subtitle + one CTA.
- DO keep motion 200–300ms, decelerating curves, press = color or scale 0.98.
- DO pre-compute tints as rgba tokens (no color-mix on Chrome 109).

**DON'T**
- DON'T use saturated blue everywhere (no blue headers, blue-tinted panels,
  blue icons); the old `#0077fa`-heavy look is what we're removing.
- DON'T box everything in bordered cards; most sections need no container.
- DON'T add shadows to chrome — shadow is for popovers/dialogs only, faintly.
- DON'T use weight 500 or bold-700 headlines; don't use pure `#000` text.
- DON'T add bouncy/springy animations, gradients, or decorative illustrations.
- DON'T hover with borders/outlines; don't change layout on hover.
- DON'T use multiple font families or icon weights mismatched with text.
- DON'T introduce a second accent or status hue beyond the semantic set.

---

## Files Found (internal)

| File Path | Description |
|---|---|
| `src/styles/tokens.css` | Current `--tk-*` token definitions to be re-valued |
| `.trellis/spec/frontend/ux-design-language.md` | Current design-language spec (Semi-inspired) that this research supersedes visually; Chrome 109 contract in §5 still binds |

## External References

- [HIG Typography](https://developer.apple.com/design/human-interface-guidelines/typography) — text style sizes/weights/leading/tracking
- [HIG Buttons](https://developer.apple.com/design/human-interface-guidelines/buttons) — 44pt targets, press states, fill guidance
- [Apple Fonts](https://developer.apple.com/fonts) — SF Pro Text/Display optical split
- [Apple · DESIGN.md teardown (webdesignhot)](https://www.webdesignhot.com/design.md/apple) — button `#0071e3/980px`, hover/pressed hexes, shadow philosophy, easing curves, DO/DON'Ts
- [VoltAgent awesome-design-md apple/DESIGN.md](https://github.com/VoltAgent/awesome-design-md/blob/main/design-md/apple/DESIGN.md) — typography ramp, weight ladder (no 500), hairline `#e0e0e0`, nav details
- [Mobbin Apple Colors](https://mobbin.com/colors/brand/apple) — `#0066cc`, `#f5f5f7`, `#1d1d1f` brand palette
- [Can I use: CSS Backdrop Filter](https://caniuse.com/css-backdrop-filter) — Chrome 76+ unprefixed
- [web.dev backdrop-filter](https://web.dev/articles/backdrop-filter) — Chrome 76 launch, usage patterns
- [Apple HIG best-practices checklist (Brilworks)](https://www.brilworks.com/blog/apple-human-interface-guidelines) — 44pt targets, contrast, empty states, reduce motion
- [HIG typography Figma guide (eonist gist)](https://gist.github.com/eonist/b9c180a67980c6e18a5184f19bff68fa) — Large Title 34/-1.05px tracking table
- [learnui iOS font guidelines](https://www.learnui.design/blog/ios-font-size-guidelines.html) — SF Pro Text ≤19 / Display ≥20
- [Chrome for Developers: CSS Nesting](https://developer.chrome.com/docs/css-ui/css-nesting) — nesting ships Chrome 112 (hence forbidden)

## Caveats / Not Found

- SF Pro itself is not web-licensable; the system stack is the only legal path
  (and what apple.com serves to non-Apple devices). Segoe UI is the Windows
  rendering reality for our intranet — verify CJK fallback (PingFang SC is
  macOS-only; Microsoft YaHei covers Windows zh-CN).
- apple.com values are from third-party teardowns, not an official Apple web
  style guide (Apple publishes none); the `--sk-*` token namespace details are
  teardown-derived. Treat hexes as accurate-as-of-source but not canonical.
- iCloud.com / Apple Music web were not separately crawled; their patterns
  (compact toolbars, dense lists) are reflected via HIG product guidance.
- No dark-mode values gathered (out of scope per repo spec).
