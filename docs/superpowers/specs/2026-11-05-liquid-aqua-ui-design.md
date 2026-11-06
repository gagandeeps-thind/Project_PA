# Liquid aqua UI

**Goal:** move the player app from a generic look to a modern, futuristic one, using neumorphism, liquid
glass and 3D inflated elements. The pitch-black background stays. `#A1F7F5` and white are the primary
colours, with a hint of `#F45B0D` for energy.

**Scope:** every Android screen gets the new look through the shared tokens and components. The five tabs
(Home, Arise, Start, Social, Profile) also get new layouts, Home first. iOS only picks up the shared tokens.
The admin console does not change.

## Colour rules

| Role | Token | Value | Rule |
|---|---|---|---|
| Floor | `background` | `#000000` | Unchanged |
| Primary | `accent` | `#A1F7F5` | Main actions, selection, progress. Dark ink on top (`onAccent`), never white |
| Primary | `textPrimary` | `#FFFFFF` | Text and numbers |
| Hint | `energy` | `#F45B0D` | See below. Dark ink on top (`onEnergy`): white on this orange is only 3.3:1 |

Orange is a hint, so it appears only as:
- the one action that starts effort on a screen (`KeyButton(energy = true)`)
- a streak
- the leading edge of live progress (`EnergyRing`)
- routes on bright map tiles, where aqua would vanish

`DesignTokensTest` pins these colours and checks text contrast on the brightest part of a glass pane.

## One job per style

- **Neumorphism:** surfaces. Panes are raised with a faint highlight opposite their shadow (`Modifier.depth`).
  Inputs, tracks and summaries sit in recesses (`Modifier.well`).
- **3D inflated:** anything pressable. `KeyButton`, `RaisedButton`, `IconOrb`, the active tab and filled week beads.
- **Liquid glass:** panes and the tab bar (`Modifier.frost`), with an icy rim that follows the phone's tilt.
  Each pane has an opaque base, because otherwise its own glow shows through and text loses contrast.

Display type is Manrope ExtraBold. Fraunces is removed.

## Layout rules

Each tab gets one focal element at the top and one orange action at most. Everything else sits below it,
quieter. Home now runs: greeting and streak, quest ring and Start, week beads, workout, shortcuts, challenge
deck, then people and posts. Copy and behaviour do not change.

Scrolling lists use `Modifier.softEdges()`. Carousels use `Modifier.bleed()` so glows reach the screen edge.

## Not in this design

There is no real background blur. The tab bar sits above the content, not over it, and blurring needs a new
dependency (Haze) plus content padding on all five tabs. Today the glass is drawn, not blurred.

## Remaining work

1. New layouts for Arise, Start, Social and Profile, applying the rules above.
2. On Start, cut the orange, gold and violet card tints down to the palette.
3. Restyle stock Material parts that still look out of place: `OutlinedTextField`, `FilterChip`,
   `LinearProgressIndicator`, sheets and dialogs.
