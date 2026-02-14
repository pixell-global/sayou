# sayou Brand Guidelines

**사유 (思惟)** — Deep contemplation. The act of quiet, focused thought.

Inspired by the 사유의 방 (Room of Quiet Contemplation) at the National Museum of Korea, designed by architect Choi Wook of ONE O ONE architects. A 439 sqm space where visitors sit with two Pensive Bodhisattva statues in near-darkness, surrounded by walls of soil, charcoal, and lacquer, beneath a shimmering ceiling of distant light.

sayou is a space for agents to store, retrieve, and reflect on knowledge. The brand embodies the same philosophy: strip away noise, create space for meaning.

---

## Brand Philosophy

### Core Concepts

**비움 (Bium)** — Emptiness as presence, not absence. The unfilled space holds meaning precisely because it is unfilled. Every element in sayou's design must earn its place. What we remove matters more than what we add.

**여백 (Yeobaek)** — The beauty of empty space. In Korean ink painting, the unpainted area is the most important element. In sayou's interfaces, whitespace is not wasted space — it is where the user's thought completes the experience.

**터 (Tuh)** — The memory and character of a place. From Choi Wook's architectural philosophy. sayou's digital surfaces should have warmth and presence, not be neutral containers.

### Design Positioning

```
Calm/Headspace ———— sayou ———————— Linear/Vercel
(soft, wellness)    (contemplative,   (cold, technical)
                     clear)

Aesop ————————————— sayou ———————— Notion
(luxury, material)  (warm,            (neutral, functional)
                     intellectual)
```

sayou lives at the intersection of developer-tool clarity and contemplative warmth. It should feel like a well-designed library in a Korean hanok — architecturally precise, materially warm, full of quiet intelligence.

### The Critical Distinction

- Headspace/Calm = "stop thinking, relax"
- sayou = "think more deeply, with clarity"

sayou's design should feel **alert and clear** rather than sleepy and soft. A quiet library at dawn, not a spa treatment room.

---

## Typography

### System: "Museum Silence"

The contrast between contemplative serifs and technical sans-serif mirrors the brand's core tension — ancient Korean contemplative practice meets modern developer tooling.

### Font Stack

| Role | Font | Weight | Fallback |
|------|------|--------|----------|
| Display / Brand | Cormorant Garamond | Light (300) | Georgia, serif |
| Korean Display | Noto Serif KR | Light (300) | serif |
| Headings | Cormorant Garamond | Regular (400) | Georgia, serif |
| Body / UI | IBM Plex Sans | Regular (400), Medium (500) | system-ui, sans-serif |
| Korean Body | Pretendard | Regular (400), Medium (500) | system-ui, sans-serif |
| Code / Data | IBM Plex Mono | Regular (400) | monospace |

### Why These Fonts

**Cormorant Garamond** — A display serif inspired by Claude Garamond's 16th-century types. High stroke contrast and refined details that feel meditative at large sizes. The hairline strokes create visual breathing room that mirrors the 사유의 방's use of space. Open source (SIL OFL), available on Google Fonts.

**IBM Plex Sans** — Designed for developer-facing products with critical character disambiguation (seriffed uppercase I, tailed lowercase l — essential for a data platform where `I`, `l`, and `1` must be instantly distinguishable). Has a subtle warmth inherited from Franklin Gothic that prevents the jarring contrast when paired with old-style serifs. The Plex superfamily (Sans + Mono) shares design DNA, creating seamless transitions between prose and code.

**IBM Plex Mono** — Matched companion to Plex Sans. Slightly wider letterforms compared to JetBrains Mono give it a more relaxed, contemplative rhythm. Consistent visual language across the interface.

**Pretendard** — A neo-grotesque built on Inter + Source Han Sans foundations, specifically optimized for Korean language contexts. Adopted by the Korean government's UI/UX design system. Handles mixed Korean-English text seamlessly because it was designed for this purpose from the ground up.

**Noto Serif KR** — The premier serif font for Korean text. Designed to harmonize with Latin serif typefaces. For displaying "사유" alongside the English brand name, this provides calligraphic warmth that echoes brush-based origins of Korean calligraphy without being decorative.

### Type Scale

```
Display:    48px / 56px line-height  — Cormorant Garamond Light
H1:         36px / 44px line-height  — Cormorant Garamond Regular
H2:         28px / 36px line-height  — Cormorant Garamond Regular
H3:         22px / 30px line-height  — IBM Plex Sans Medium
H4:         18px / 26px line-height  — IBM Plex Sans Medium
Body:       16px / 26px line-height  — IBM Plex Sans Regular
Body Small: 14px / 22px line-height  — IBM Plex Sans Regular
Caption:    12px / 18px line-height  — IBM Plex Sans Regular
Code:       14px / 22px line-height  — IBM Plex Mono Regular
```

### Typography Rules

**Weight restraint.** Use no more than 3 weights across the entire design system:
- Light (300) for display text
- Regular (400) for body text
- Medium (500) for emphasis — avoid Bold wherever possible

**Dark mode adjustment.** On dark backgrounds, use slightly thinner weights than on light backgrounds. Light (300) rather than Regular (400) for display text.

**Letter spacing.** +0.02em to +0.05em for headings at display sizes. Normal for body text. The extra space creates the "air" quality of Korean 여백.

**Line height.** 1.6x–1.7x for body text, more generous than the typical 1.5x. Text should breathe rather than simply talk.

**Korean-English harmony.** When "사유" appears alongside "sayou", use the serif pair (Cormorant + Noto Serif KR). Korean characters may need 1–2px size adjustment to match optical weight of Latin companions.

### Font Sources

| Font | Source | License |
|------|--------|---------|
| Cormorant Garamond | [Google Fonts](https://fonts.google.com/specimen/Cormorant+Garamond) | SIL OFL |
| Noto Serif KR | [Google Fonts](https://fonts.google.com/noto/specimen/Noto+Serif+KR) | SIL OFL |
| IBM Plex Sans | [Google Fonts](https://fonts.google.com/specimen/IBM+Plex+Sans) | SIL OFL |
| IBM Plex Mono | [Google Fonts](https://fonts.google.com/specimen/IBM+Plex+Mono) | SIL OFL |
| Pretendard | [GitHub](https://github.com/orioncactus/pretendard) | SIL OFL |

---

## Color System

### Design Philosophy

The palette draws from three sources:
1. **The Room** — Deep darkness, warm golden focal light, natural earth materials
2. **Korean Tradition** — Hwangto earth, hanji paper warmth, celadon subtlety
3. **Developer Tool Craft** — Systematic scales, layered surfaces, functional clarity

The fundamental principle: **Darkness is the canvas. Warmth is the accent. Restraint is the method.**

### Brand Colors

| Name | Hex | Reference | Usage |
|------|-----|-----------|-------|
| **Sayou Gold** | `#C4A46E` | Aged gilt-bronze patina of the Pensive Bodhisattva | Primary actions, brand mark, links |
| **Sayou Gold Light** | `#D4B97E` | Bright gilt surface catching light | Hover states, highlights |
| **Sayou Gold Dark** | `#A68B55` | Deep bronze in shadow | Active/pressed states |
| **Bisaek** | `#8FB5A3` | Korean celadon (비색), muted | Secondary accent, data viz, tags |
| **Hwangto** | `#B08968` | Korean yellow-earth (황토) | Warm tertiary, illustrations |
| **Hanji** | `#E8DFD0` | Korean handmade paper (한지) | Light mode backgrounds, cards |

**Why Sayou Gold (`#C4A46E`):** A muted, warm gold referencing the 1,400-year-old gilt-bronze statues receiving soft light in a dark room. Not bright metallic gold but the quiet, time-worn warmth of patina. Distinctive in the developer tool space — no major tool uses warm gold as primary. It avoids the cold blues and purples that dominate (Linear's indigo, Vercel's blue, GitHub's blue).

**Why Bisaek (`#8FB5A3`):** Muted and grayed compared to raw celadon (`#ACE1AF`). References Korean ceramic heritage without being garish. Serves as complement to the gold for categorization, badges, or alternate emphasis.

### Dark Mode

Dark mode is the primary theme. Following the 사유의 방's design — charcoal walls, earth finishes, light-absorbing surfaces.

#### Backgrounds

| Token | Hex | Usage |
|-------|-----|-------|
| `bg-app` | `#0C0B0A` | Root application background — the dark corridor |
| `bg-primary` | `#141310` | Main content area |
| `bg-secondary` | `#1A1916` | Sidebar, navigation panels |
| `bg-surface` | `#21201C` | Cards, panels, modals |
| `bg-elevated` | `#2A2823` | Dropdowns, popovers, tooltips |
| `bg-hover` | `#33312B` | Interactive hover states |
| `bg-active` | `#3D3A33` | Active/selected states |
| `bg-overlay` | `rgba(12, 11, 10, 0.8)` | Modal overlays, backdrops |

`#0C0B0A` is not pure black — it is a very dark warm tone, like the dark corridor entering 사유의 방. The warm brown undertone comes from R slightly > G > B, giving all surfaces a subtle earthy temperature.

#### Text

| Token | Hex | Usage |
|-------|-----|-------|
| `text-primary` | `#E8E3D8` | Headings, emphasis |
| `text-secondary` | `#B0AA9D` | Body text |
| `text-tertiary` | `#8A8579` | Secondary information |
| `text-muted` | `#625E53` | Placeholders, disabled |

#### Borders

| Token | Hex | Usage |
|-------|-----|-------|
| `border-default` | `#2A2823` | Standard borders |
| `border-subtle` | `#21201C` | Subtle separators |

### Light Mode

Light mode avoids cold `#FFFFFF` white. The lightest value has the warmth of hanji paper — cream, not clinical.

#### Backgrounds

| Token | Hex | Usage |
|-------|-----|-------|
| `bg-app` | `#FAF8F4` | Root application background — hanji warmth |
| `bg-primary` | `#F2EEE7` | Main content area |
| `bg-secondary` | `#E8E3D8` | Sidebar, navigation panels |
| `bg-surface` | `#FFFFFF` | Cards, panels (true white for elevation contrast) |
| `bg-elevated` | `#FFFFFF` | Dropdowns, popovers |
| `bg-hover` | `#F2EEE7` | Interactive hover states |
| `bg-active` | `#E8E3D8` | Active/selected states |
| `bg-overlay` | `rgba(26, 23, 19, 0.4)` | Modal overlays |

#### Text

| Token | Hex | Usage |
|-------|-----|-------|
| `text-primary` | `#3D3832` | Headings, body text |
| `text-secondary` | `#5C564C` | Secondary information |
| `text-tertiary` | `#7D766A` | Tertiary text |
| `text-muted` | `#A49C8C` | Placeholders, disabled |

#### Borders

| Token | Hex | Usage |
|-------|-----|-------|
| `border-default` | `#D1CBBD` | Standard borders |
| `border-subtle` | `#DDD7CA` | Subtle separators |

### Semantic Colors

Slightly desaturated compared to typical UI defaults, avoiding the "neon on dark" problem.

#### Dark Mode

| Token | Hex | Background | Usage |
|-------|-----|------------|-------|
| `success` | `#5DAD7B` | `#1A2E22` | Confirmations, completion |
| `warning` | `#D4A248` | `#2E2515` | Caution states |
| `error` | `#D4645C` | `#2E1A18` | Errors, destructive actions |
| `info` | `#6BA3BE` | `#172A33` | Informational, neutral alerts |

#### Light Mode

| Token | Hex | Background | Usage |
|-------|-----|------------|-------|
| `success` | `#2E7D4F` | `#E8F5EC` | Confirmations, completion |
| `warning` | `#A67A1A` | `#FEF5E0` | Caution states |
| `error` | `#C4382E` | `#FDE8E6` | Errors, destructive actions |
| `info` | `#337EA9` | `#E7F3F8` | Informational, neutral alerts |

**Design notes:**
- Warning (`#D4A248`) deliberately sits close to the gold primary — warnings should feel like a more urgent version of the brand color, not a completely different hue
- Error (`#D4645C`) is desaturated compared to typical reds, giving it a warm, terracotta quality aligned with the contemplative aesthetic
- Success (`#5DAD7B`) has a slight teal shift toward celadon, connecting it to the bisaek accent
- Info (`#6BA3BE`) is muted and grayish, avoiding bright electric blues

### Full Gray Scale

#### Dark Mode (warm-tinted)

| Token | Hex |
|-------|-----|
| `gray-950` | `#0C0B0A` |
| `gray-900` | `#141310` |
| `gray-850` | `#1A1916` |
| `gray-800` | `#21201C` |
| `gray-750` | `#2A2823` |
| `gray-700` | `#33312B` |
| `gray-600` | `#49463D` |
| `gray-500` | `#625E53` |
| `gray-400` | `#8A8579` |
| `gray-300` | `#B0AA9D` |
| `gray-200` | `#D1CBBD` |
| `gray-100` | `#E8E3D8` |
| `gray-50` | `#F5F2EB` |

#### Light Mode (warm-tinted)

| Token | Hex |
|-------|-----|
| `gray-50` | `#FAF8F4` |
| `gray-100` | `#F2EEE7` |
| `gray-150` | `#E8E3D8` |
| `gray-200` | `#DDD7CA` |
| `gray-250` | `#D1CBBD` |
| `gray-300` | `#C4BCAC` |
| `gray-400` | `#A49C8C` |
| `gray-500` | `#7D766A` |
| `gray-600` | `#5C564C` |
| `gray-700` | `#3D3832` |
| `gray-800` | `#2A2621` |
| `gray-900` | `#1A1713` |

---

## Spacing

### Philosophy

Macro spacing follows the 여백 principle — generous emptiness between sections. Each thought gets room to breathe. Micro spacing follows a systematic scale for predictability.

### Scale

```
4px   — Tight internal spacing
8px   — Default internal spacing
12px  — Compact element gaps
16px  — Standard element spacing
24px  — Group spacing
32px  — Section internal padding
48px  — Section gaps
64px  — Major section separation
96px  — Page-level breathing room
128px — Hero / display spacing
```

### The 1-Degree Incline Principle

The 사유의 방 tilts its floor 1 degree upward, causing visitors to naturally slow their steps without noticing. Apply this to the interface:

- Scroll behavior should feel slightly decelerated
- Content reveals itself at a contemplative pace
- Transition easing curves should decelerate naturally — ease-out, not ease-in-out
- Information density should be low: a thought-per-screen rather than data-per-screen

---

## Border Radius

| Element | Radius | Rationale |
|---------|--------|-----------|
| Cards / containers | 8–12px | Not sharp (too cold), not round (too soft). The gentle curve of a ceramic tea bowl. |
| Buttons | 6–8px | Functional, not playful |
| Inputs | 6–8px | Matching buttons |
| Avatars / icons | 50% | Standard convention |
| Modals | 12–16px | Slightly softer than cards, suggesting overlay atmosphere |

---

## Animation

Directly inspired by the spatial experience of the 사유의 방.

### Transitions

- **Duration:** 300–500ms for most transitions. Deliberate, never instant.
- **Easing:** Ease-out curves that decelerate naturally, like footsteps slowing on an inclined floor.
- **Page transitions:** Fade + subtle vertical shift. The feeling of walking from one room into another through a dark corridor.

### Ambient Motion

- Optional subtle background animation — slow, organic, almost imperceptible
- The visual equivalent of flowing water: always present, never distracting
- Breathing/pulsing rhythm for loading states rather than spinners

### Interaction Feedback

- Immediate but gentle. No bounces, no overshoots.
- Elements appear to settle into place.
- Hover states emerge slowly (200ms fade), like light gradually falling on a surface.

### What to Avoid

- Bouncy/elastic animations (signals playfulness, not contemplation)
- Spinners (mechanical, anxious energy)
- Rapid transitions under 150ms (feels jarring)
- Animation for animation's sake

---

## Voice & Tone

### Principles

**Quiet confidence.** sayou does not shout, persuade, or perform urgency. It states clearly and trusts the reader.

**Intellectual warmth.** Technical precision paired with human sensibility. Never cold or corporate, never casual or chatty.

**Restraint.** Say less. Every word should earn its place, like every element in the 사유의 방.

### Examples

| Context | Do | Don't |
|---------|-------|-----------|
| CTA | "Begin" | "Get started now!" |
| Empty state | "Nothing here yet." | "Looks like you haven't added anything! 🎉" |
| Success | "Saved." | "Awesome! Your changes have been saved successfully! ✅" |
| Error | "Could not connect to the database." | "Oops! Something went wrong. Please try again later." |
| Onboarding | "sayou stores and surfaces knowledge for your agents." | "Welcome to sayou! 🚀 The ultimate knowledge platform for AI agents!" |

### Language Rules

- No exclamation marks in UI copy
- No emoji in product interfaces
- No "please" in error messages (be direct)
- No urgency language ("now", "hurry", "don't miss")
- Lowercase brand name: **sayou**, never "Sayou" or "SAYOU" in running text
- Korean: **사유** in serif (Noto Serif KR) when displayed alongside the brand name

---

## Logo Usage

### Wordmark

The sayou wordmark is set in **Cormorant Garamond Light** (300 weight), lowercase.

```
sayou
```

When paired with the Korean name:

```
sayou  사유
```

The Korean text uses **Noto Serif KR Light** at a matched optical size.

### Spacing

- Minimum clear space around the wordmark: 1x the height of the lowercase "s"
- The wordmark should never be crowded by other elements

### Color Usage

| Context | Wordmark Color |
|---------|---------------|
| Dark background | `#E8E3D8` (text-primary dark) |
| Light background | `#3D3832` (text-primary light) |
| Brand accent | `#C4A46E` (sayou gold) |

### Restrictions

- Never set the wordmark in bold or heavy weights
- Never add effects (shadow, glow, gradient) to the wordmark
- Never rotate or skew the wordmark
- Never use the wordmark on busy or low-contrast backgrounds

---

## Design References

### Primary Inspirations

| Source | What to Borrow |
|--------|---------------|
| 사유의 방 (Choi Wook) | Dark corridor transitions, 1-degree deceleration, sound-absorbing material quality, non-central focus |
| Korean 여백/비움 | Emptiness as presence. Space full of potential thought. |
| Aesop | Warm monochrome palette, humanist typography, material restraint |
| Linear | Dark mode philosophy (never pure black), text color hierarchy, systematic tokens |
| Notion | "Canvas for thought" principle, generous line-height, serif for intellectual warmth |
| read.cv | Editorial spacing, print-design sensibility, typographic restraint |
| Stripe | Slow organic ambient animation, vertical rhythm, spacing-as-confidence |

### What to Avoid

| Pattern | Why |
|---------|-----|
| Pure black `#000` or pure white `#FFF` | Too harsh, no warmth, no 터 (character) |
| Bright saturated accents | Break contemplative atmosphere |
| Bouncy/elastic animations | Signal playfulness, not contemplation |
| Rounded bubbly UI (16px+ radius on small elements) | Signals wellness app, not intellectual tool |
| Dense information layouts | Contradicts 여백 principle |
| Aggressive CTAs, urgency language | The antithesis of 사유 |
| Cookie-cutter dark SaaS aesthetic | sayou needs its own identity |
| Emoji or illustration-heavy visual language | Too consumer-wellness |

---

## CSS Custom Properties Reference

```css
:root {
  /* Brand */
  --sayou-gold: #C4A46E;
  --sayou-gold-light: #D4B97E;
  --sayou-gold-dark: #A68B55;
  --sayou-bisaek: #8FB5A3;
  --sayou-hwangto: #B08968;
  --sayou-hanji: #E8DFD0;

  /* Typography */
  --font-display: 'Cormorant Garamond', Georgia, serif;
  --font-display-kr: 'Noto Serif KR', serif;
  --font-body: 'IBM Plex Sans', system-ui, sans-serif;
  --font-body-kr: 'Pretendard', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', monospace;

  /* Border Radius */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 50%;

  /* Transitions */
  --duration-fast: 200ms;
  --duration-normal: 300ms;
  --duration-slow: 500ms;
  --easing-default: cubic-bezier(0.16, 1, 0.3, 1);
}

/* Dark Mode (default) */
[data-theme="dark"] {
  --bg-app: #0C0B0A;
  --bg-primary: #141310;
  --bg-secondary: #1A1916;
  --bg-surface: #21201C;
  --bg-elevated: #2A2823;
  --bg-hover: #33312B;
  --bg-active: #3D3A33;
  --bg-overlay: rgba(12, 11, 10, 0.8);

  --text-primary: #E8E3D8;
  --text-secondary: #B0AA9D;
  --text-tertiary: #8A8579;
  --text-muted: #625E53;

  --border-default: #2A2823;
  --border-subtle: #21201C;

  --color-success: #5DAD7B;
  --color-success-bg: #1A2E22;
  --color-warning: #D4A248;
  --color-warning-bg: #2E2515;
  --color-error: #D4645C;
  --color-error-bg: #2E1A18;
  --color-info: #6BA3BE;
  --color-info-bg: #172A33;
}

/* Light Mode */
[data-theme="light"] {
  --bg-app: #FAF8F4;
  --bg-primary: #F2EEE7;
  --bg-secondary: #E8E3D8;
  --bg-surface: #FFFFFF;
  --bg-elevated: #FFFFFF;
  --bg-hover: #F2EEE7;
  --bg-active: #E8E3D8;
  --bg-overlay: rgba(26, 23, 19, 0.4);

  --text-primary: #3D3832;
  --text-secondary: #5C564C;
  --text-tertiary: #7D766A;
  --text-muted: #A49C8C;

  --border-default: #D1CBBD;
  --border-subtle: #DDD7CA;

  --color-success: #2E7D4F;
  --color-success-bg: #E8F5EC;
  --color-warning: #A67A1A;
  --color-warning-bg: #FEF5E0;
  --color-error: #C4382E;
  --color-error-bg: #FDE8E6;
  --color-info: #337EA9;
  --color-info-bg: #E7F3F8;
}
```

---

## Research Sources

### Architecture & Space
- [사유의 방 - Korea Times](https://www.koreatimes.co.kr/lifestyle/arts-theater/20211112/room-of-quiet-contemplation-designs-space-for-viewers-to-reflect-on-thinking-bodhisattvas)
- [사유의 방 - Korea.net](https://www.korea.net/NewsFocus/Culture/view?articleId=206319)
- [Choi Wook / ONE O ONE architects - Metalocus](https://www.metalocus.es/en/author/one-o-one-architects)
- [Mak and Bium - Architectural Review](https://www.architectural-review.com/essays/mak-and-bium-imperfection-and-emptiness-in-korean-aethetics)

### Korean Aesthetics & Color
- [Obangsaek - Wikipedia](https://en.wikipedia.org/wiki/Obangsaek)
- [Dancheong Temple Colours](https://koreantempleguide.com/dancheong-temple-colours/)
- [Korean Traditional Color Palette - Octet Design](https://octet.design/colors/palette/korean-traditional-color-palette-1732427778/)
- [Colors in Korean Culture - HashtagHankuk](https://www.hashtaghankuk.com/en/colors-and-their-meanings)

### Typography
- [Aesop typography - Fonts In Use](https://fontsinuse.com/uses/20234/aesop-logo-website-and-packaging)
- [IBM Plex Design Language](https://www.ibm.com/design/language/typography/typeface/)
- [Pretendard - GitHub](https://github.com/orioncactus/pretendard)
- [Spectral - Google Design](https://design.google/library/spectral-new-screen-first-typeface)

### Design Systems
- [Linear Brand](https://linear.app/brand)
- [Vercel Geist](https://vercel.com/geist/introduction)
- [Stripe Accessible Color Systems](https://stripe.com/blog/accessible-color-systems)
- [50 Shades of Dark Mode Gray](https://blog.karenying.com/posts/50-shades-of-dark-mode-gray/)

### Contemplative Design
- [Korean Minimalism - Medium](https://medium.com/@SerenoWaves/korean-minimalism-in-design-and-lifestyle-b6ac5966cd11)
- [Wabi-Sabi in Digital Design - Orizon](https://www.orizon.co/blog/the-beauty-of-wabi-sabi-design-in-the-digital-age)
- [Headspace Design System - Standards](https://standards.site/case-studies/headspace/)
- [Calm Brand Colors - Mobbin](https://mobbin.com/colors/brand/calm-com)
