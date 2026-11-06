# Player app design: charcoal and Gulf orange

**Goal:** a flat, high-contrast look with no glows. This replaces the earlier liquid aqua design.

**Scope:** every Android screen gets the look through the shared tokens and components. iOS only picks up
the shared tokens, so its components keep their older shapes and shadows. The admin console does not change.

## Colour rules

| Role | Token | Value | Rule |
|---|---|---|---|
| Floor | `background` to `backgroundAccentAlt` | `#161719` to `#1E2024` | Vertical gradient behind every screen |
| Card surface | `glassFallback` | `#23262B` | With a 1px `glassBorder` of `#2F343B` |
| Primary action, key words | `accent` | `#FF5500` | Dark ink on top (`onAccent`): white on this orange is only 3.2:1 |
| Secondary accents | `accentAlt` | `#95B8C0` | Secondary buttons, badges, the quest ring's fill |
| Text | `textPrimary`, `textSecondary` | `#FFFFFF`, `#8E95A2` | |

`DesignTokensTest` pins these colours and checks text contrast on the floor and on cards.

Map lines and telemetry chart series keep their own colours, so the data stays readable.

## Components

- **Cards:** flat, 20dp radius, no shadow or glow (`Modifier.frost`, `FrostCard`). Insets use `Modifier.well`.
- **Primary button:** a solid orange pill with a trailing arrow (`KeyButton`).
- **Secondary button:** transparent with a 1.5dp powder blue outline and matching text (`RaisedButton`).
- **Headers:** bold capitals with the last word in orange (`headerText`). Used by the screen title bar,
  `SectionHeader` and Home's section headings.

Display type is Manrope ExtraBold.

## Tab bar

`FrostBar` floats over the screen, inset 32dp from each edge. Tab screens run the full height of the display
and pad the end of their scrolling content by `LocalTabBarInset`, so nothing gets stuck behind the bar.

The bar is liquid glass with no blur, drawn by an AGSL shader over a recording of the screen behind it. Content
stays sharp through the middle and bends inwards at the rim, under a thin specular edge. Below Android 13, which
cannot run the shader, the bar is a dark translucent fill.

The current tab shows its icon in orange with its name below, on a plain white highlight that slides between
tabs. A glass drop over the icons was tried and dropped because it made them unreadable, so icons are drawn on
top of the glass, not through it.

## Remaining work

1. Stock Material buttons have the new colours but not the trailing arrow or the secondary style.
2. Headings outside the components above still use the old style.
3. The light palette is unchanged, because the app only runs dark.
