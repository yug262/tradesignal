# Design Brief: Premium Dark Intelligence Terminal

## Overview
Serious financial intelligence command center. Bloomberg Terminal meets modern dark UI. Data-driven, zero friction, authoritative, ruthlessly efficient.

## Tone & Purpose
High-stakes trading decisions demand precision over decoration. Every visual element serves information delivery. Professional, sharp, no playfulness.

## Color Palette

| Role | OKLCH | Usage |
|------|-------|-------|
| Background | `0.12 0 0` | Deep charcoal, main canvas |
| Card/Surface | `0.17 0 0` | Elevated content layers |
| Border | `0.22 0 0` | Subtle separators, minimal visual weight |
| Muted Text | `0.40 0 0` | Secondary info, metadata |
| Foreground | `0.96 0 0` | Body text, high contrast |
| Primary/Accent | `0.68 0.15 61` | Amber highlights, active states, signals |
| Success (Buy) | `0.65 0.22 142` | Green, buy signals, confirmed setups |
| Destructive (Reject) | `0.62 0.22 30` | Red, rejections, stops, losses |

## Typography

| Layer | Font | Usage |
|-------|------|-------|
| Display | Space Grotesk | Headers, page titles, data labels |
| Body | Inter | Body text, descriptions, UI copy |
| Mono | Geist Mono | Price feeds, tables, code, configuration |

## Elevation & Depth

| Layer | Shadow | Background | Usage |
|-------|--------|-----------|-------|
| Base | none | `--background` | Main canvas |
| Card | `shadow-card` | `--card` | Content zones, trade cards, modals |
| Elevated | `shadow-elevated` | `--card` | Floating panels, dropdowns |
| Subtle | `shadow-subtle` | `--card` | Gentle lift, secondary cards |

## Structural Zones

| Zone | Background | Border | Purpose |
|------|-----------|--------|---------|
| Header | `--card` | `border-b border-border/30` | Market status, mode badge, refresh time |
| Sidebar | `--background` | `border-r border-border/30` | Icon nav, active indicator (primary) |
| Main Content | `--background` | none | Full-width content grid |
| Trade Cards | `--card` | `border-subtle` | Opportunity, rejection reason, data zones |
| Data Table | `--card` | `border-subtle` | Dense rows, alternating `--card`/`--muted` |

## Spacing & Rhythm

- Grid: 4px increments (4, 8, 12, 16, 20, 24, 32)
- Sidebar width: 64px (compact icons) or 240px (expanded text)
- Card padding: 16px (compact) or 20px (spacious)
- Gap between cards: 12px

## Component Patterns

- **Trade Card**: Header (ticker + status), metrics grid, reason (if rejection), action buttons
- **Data Row**: Monospace values left-aligned, status indicator right, hover: `--muted/50` background
- **Status Badge**: Pill shape (radius: 4px), semantic color (green/red/amber), no background fill
- **Rejection Reason**: Icon + bold label + explanation, full-width card, `--destructive` accent
- **Active State**: Primary accent color, no animation, instant feedback

## Motion & Transitions

- Default transition: `cubic-bezier(0.4, 0, 0.2, 1)` 300ms
- Entrance: `fade-in` 200ms (opacity 0→1)
- Slide: `slide-in-right` 250ms (translateX 8px→0, opacity 0→1)
- Avoid: bounce, elastic, or decorative easing

## Constraints

- No generative gradients or glassmorphism
- No random color usage (green/red/amber only)
- No shadows above `shadow-elevated`
- Minimum 4px corner radius (sharp) or 0px for borders
- No outline strokes on buttons — use background + text color only
- No background images or textures

## Signature Detail

**Micro-contrast hierarchy**: Multiple greys (background, card, border, muted) create density without chaos. Semantic color (amber/green/red) appears only when it means something. Data tables use background layers instead of lines. Every zone has deliberate elevation/depth treatment.

## Differentiation

Terminal UI for financial intelligence. Not a dashboard, not a generic SaaS app. Bloomberg-grade information density, modern dark palette, geometric sans-serif headers paired with refined body type, monospace data values, minimal borders, semantic color discipline.
