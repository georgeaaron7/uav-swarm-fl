---
name: SwarmCompute
description: Compact dark operations console for independent research simulations.
colors:
  canvas: "#151e2a"
  surface: "#1b2736"
  sidebar: "#111a25"
  input: "#172230"
  inset: "#121b27"
  empty: "#1a2635"
  form: "#1e2c3e"
  text: "#e4edf7"
  muted: "#a4b3c5"
  line: "#344256"
  accent: "#87bfee"
  primary: "#a5d0f2"
  primary-ink: "#13283c"
  primary-hover: "#c3e1f7"
  button: "#253449"
  button-hover: "#35465e"
  button-border: "#46566c"
  field-border: "#4b5d74"
  focus: "#aed9fb"
  nav-active: "#253a51"
  nav-active-text: "#c1e3ff"
  success: "#86cfb3"
  diverged: "#e4bb76"
  danger: "#f3a0a1"
  error-surface: "#332731"
  error-border: "#87565e"
  error-text: "#f5b9bd"
  progress-track: "#34445a"
  progress-value: "#8fc6ee"
typography:
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "29px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "17px"
    fontWeight: 620
    letterSpacing: "-0.01em"
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "14px"
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "13px"
  measurement:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
    fontSize: "25px"
    fontWeight: 580
    letterSpacing: "-0.03em"
  code:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "12px"
    lineHeight: 1.7
rounded:
  field: "5px"
  control: "6px"
  empty: "7px"
  surface: "9px"
spacing:
  label-gap: "8px"
  compact: "12px"
  row: "16px"
  field-gap: "20px"
  panel: "24px"
  section: "28px"
  content: "36px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-ink}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  button-secondary:
    backgroundColor: "{colors.button}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "9px 13px"
  button-secondary-hover:
    backgroundColor: "{colors.button-hover}"
  input:
    backgroundColor: "{colors.input}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    padding: "10px 12px"
  navigation-active:
    backgroundColor: "{colors.nav-active}"
    textColor: "{colors.nav-active-text}"
    rounded: "{rounded.field}"
    padding: "12px 14px"
  study-progress:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.surface}"
    padding: "24px"
  empty-state:
    backgroundColor: "{colors.empty}"
    rounded: "{rounded.empty}"
    padding: "42px 24px"
  error:
    backgroundColor: "{colors.error-surface}"
    textColor: "{colors.error-text}"
    rounded: "{rounded.control}"
    padding: "13px 16px"
---

# Design System: SwarmCompute

## Overview

**Creative North Star: "The Compact Operations Console"**

A compact dark operations console built directly in code. Blue slate layers, system typography and restrained color keep queue state, worker participation and scientific outcomes easy to scan. Functional SVG icons and measured data supply the visual detail.

The user pinned this world and code-first construction. Preserve its familiar controls, dense data presentation and explicit state labels. The interface ships without generated imagery or raster decoration.

**Key Characteristics:**
- Dense, readable operations layouts.
- Flat slate surfaces with pale blue actions.
- Tabular measurements and explicit outcome labels.
- Responsive navigation and purposeful feedback.
- Code-built controls, charts and SVG icons.

## Colors

A cool blue slate foundation supports pale blue actions and readable semantic outcomes. The frontmatter records reused shipped values from `web/src/style.css`; descriptive names identify their role rather than a new palette.

### Primary

- **Pale Action Blue** (`primary`, `primary-hover`, `primary-ink`): filled primary controls and their hover treatment.
- **Link Blue** (`accent`): text links and active-work markers. Chart traces use their existing dedicated blue rather than broad decorative color fills.

### Neutral

- **Slate Canvas** (`canvas`): the page background; **Rail Slate** (`sidebar`): the fixed navigation.
- **Panel Slate** (`surface`, `empty`, `form`): the progress strip, explanatory empty states and expanded inline forms. Ordinary sections remain on the canvas.
- **Field Slate** (`input`) and **Code Inset** (`inset`): editable fields and bounded code/log blocks.
- **Cool White** (`text`) and **Muted Steel** (`muted`): primary content and supporting context.
- **Slate Rules** (`line`, `button-border`, `field-border`): structural dividers and control edges.
- **Navigation Slate** (`nav-active`, `nav-active-text`): the current route.

### Semantic states

- **Quiet Green** (`success`): succeeded experiments and online idle workers.
- **Warm Amber** (`diverged`): scientific divergence and draining workers.
- **Soft Red** (`danger`): failure, attention and incompatibility.
- **Error Tint** (`error-surface`, `error-border`, `error-text`): inline error notices.
- **Progress Blue** (`progress-value`, `progress-track`): completed work against a visible track. Running status uses its own existing pale blue text; waiting, offline and paused states use muted text.

**The Outcome Rule.** Pair every status color with readable state text. Keep scientific divergence amber and infrastructure failure red.

## Typography

**Body and headings:** the operating system UI stack. **Code and logs:** UI monospace, SFMono-Regular, Consolas, monospace. No web fonts are loaded. The root is compact (14px); paragraph copy uses a generous line height (1.6) and a reading width capped at 75ch.

- **Headline:** page titles follow the frontmatter headline role; mobile titles are smaller (26px), and the sign-in title is compact (25px).
- **Title:** section headings use the title role; empty-state headings are slightly smaller (16px, weight 600). Mobile section headings are also 16px.
- **Body and labels:** fields use 13px labels, with 8px separation from the control. Supporting paragraphs and table values commonly use 12–13px; small metadata uses 10–12px.
- **Measurement:** primary statistic values use the measurement role, with muted 17px secondary units. Values become 22px at the intermediate breakpoint and 24px on mobile. Terminal count is 24px, weight 600.
- **Code:** long provenance, addresses and code wrap safely. Log blocks use the code role, preserve line breaks, scroll as needed and stop growing at 480px.

**The Measurement Rule.** Use tabular numerals for statistics, progress counts, tables and event times; show unknown measurements as an em dash.

## Layout

The desktop shell combines a fixed navigation rail (226px), a connection bar (62px) and a flexible main column. Content is centered with a maximum outer width of 1840px and 36px padding. Page headings and their actions share a row; section content begins after clear vertical separation (28px). The overview uses a broad progress strip, four aligned measurement columns, then supporting sections. Its lower grid uses a 1.5fr activity column and a minimum-280px connection column with a 36px gap.

- **At 1500px and above:** content padding becomes 44px vertically and 48px horizontally; the lower grid gap expands to 56px and statistic gaps to 48px.
- **At 1100px and below:** the rail becomes 196px; content is padded 28px by 24px; the lower overview grid becomes one column. Statistics remain four columns.
- **At 760px and below:** the rail becomes an off-canvas drawer (226px), the main column fills the viewport, and the connection bar becomes 57px tall. Content padding is 25px by 18px. Page headers wrap; the terminal count moves below the progress heading; statistic columns become two; form grids become one; facts stack vertically; the footer stacks. Filters wrap into two columns with full-width search. Enrollment fields wrap and the chart selector stacks.

Wide tables keep their columns and horizontal scrolling inside their own wrapper. They use compact metadata and row dividers rather than transforming into cards. Search/filter groups wrap. Charts remain 290px tall, with smaller axis text on mobile. Help copy is capped at 900px, settings fields at 850px and the login form at 410px.

## Elevation & Depth

Depth comes from tonal layers, fine rules and spacing. Ordinary sections, statistics and tables have no shadows. The enrollment popover is the single lifted panel: its implemented shadow is `0 16px 64px #090f1880`, with a brighter outline. The mobile drawer sits above a dark scrim, and neither receives decorative blur.

**The Flat Surface Rule.** Separate ordinary content with tone, spacing and rules. Reserve the implemented shadow for the enrollment popover.

## Shapes

Controls have gently curved corners: fields and navigation at 5px, buttons and code blocks at 6px. Empty states and inline forms use 7px; progress and enrollment panels use 9px. Structure is mostly rectangular with 1px rules. Circular dots identify statuses and events; outcome legends use small square markers. SVG icons are functional and generally 14–24px. There is no raster artwork in the shipped console.

## Components

### Buttons and links

Compact controls keep action text visible. Secondary buttons use the slate fill, a 1px control border and 9px by 13px padding; action groups tighten this to 8px by 11px. Primary buttons use pale blue with dark ink and weight 650. Hover changes the fill over 160ms ease-out. Disabled buttons use 0.48 opacity and a not-allowed cursor. Icon-only buttons carry accessible labels; ordinary text links use blue, a small icon gap and an underlined hover state.

All interactive controls, links and disclosures share a visible focus outline (2px `focus`, offset 4px). Do not infer a custom pressed effect; the source defines no distinct active transform.

### Fields and forms

Dark fields have a 1px field border, 10px by 12px padding and full available width. Labels remain outside the fields; placeholders are muted. Search is a 39px inline icon-and-input container. Checkboxes are native (17px) with the primary accent. Forms use two equal columns with a 20px gap until mobile. Busy actions replace labels with task-specific progress text where implemented, such as “Signing in…”, “Validating & planning…” or “Saving…”. Errors appear as adjacent notices rather than a documented custom invalid-field border.

### Worker participation

Worker detail exposes a labeled native **Participation mode** selector using the existing field treatment: Light, Balanced and Dedicated. The selector is disabled unless the current user owns the worker or has the owner-granted preferences permission, and it remains disabled while a control or preferences request is pending. Its desktop label and control share a row; on mobile the label stacks above the full-width select, matching the chart-selector layout. Mode changes are submitted immediately; adjacent hint copy explains that the acknowledged update applies to the next experiment. Request failures use the shared inline alert.

Worker facts show GPU/CPU utilization, RAM percentage and GPU temperature alongside mode and heartbeat context. They retain the standard facts grid and unknown-value formatting rather than introducing decorative telemetry gauges.

### Navigation

The fixed rail uses stacked links, muted icons and labels, and a tonal current-route row. Identity and sign-out remain at the bottom. Routes are role-dependent. The mobile menu exposes expanded state and controls the drawer. A closed mobile drawer is hidden, inert and aria-hidden. Opening moves focus to its first link; Tab cycles through drawer links/buttons; Escape, route selection and scrim click close it and return focus to the menu button. The drawer slides over 200ms ease-out. Reduced-motion preference disables animation and transition throughout the app.

### Progress, measurements and statuses

The terminal strip is a single filled surface with explanatory copy, a native progress bar and text-labeled outcome counts. Its track is 8px; row-level progress tracks are 4px. Statistics remain unboxed beneath it. Statuses are compact text-and-dot indicators, not pill-shaped badges. Scientific divergence stays visibly separate from operational failure. Empty totals use a valid progress maximum of one while displaying the actual zero count.

### Tables, events and details

Tables use 11px headers and 12px tabular values, compact secondary metadata, a slightly raised header tone and a subtle row-hover fill. Rows are divided by rules. Event rows pair a small outlined marker, readable event name, shortened entity context and a tabular timestamp. Native disclosures expose configuration, manifest, runtime and execution logs; full hashes wrap rather than truncate. The frozen manifest review is an inline form-toned panel, not a modal, with fingerprint facts, an expandable complete configuration and a route to planned jobs.

### Charts

The round-metrics chart uses a single linear blue trace, horizontal grid rules and a dark tooltip. Missing values remain gaps (`connectNulls=false`); dots and chart animation are disabled. A labeled native selector switches the metric, and a textual accessible name identifies its plotted measure. The empty chart state waits for completed-round reports. Charts show simulator rate values on their original 0–1 scale; summary accuracy values are formatted as percentages.

### Empty, loading, error and live states

Empty states use a filled inset, a short heading and a next-step explanation tailored to studies, workers, experiments, checkpoints, metrics or history. Data loading uses quiet text, not decorative skeletons. Unknown measurements appear as em dashes; an unmeasured ETA explains that it is waiting for completions.

Errors use the error tint, border and readable wrapping text; API/action error notices announce with `role=alert`. Successful saves, password updates and clipboard feedback use `role=status`. Address copying reports success or an explicit manual-copy fallback in the same address row. The storage warning uses the error appearance and explanatory operational copy.

The connection bar reads “Live updates” with a green dot when its authenticated SSE stream is connected, and “Polling every 10s” otherwise. Data also refreshes every ten seconds and on stream-triggered refresh events. Stream reconnection retries after ten seconds. These are connection-state labels; there is no decorative pulse or invented activity. Authentication expiry returns the user to sign-in.

The enrollment popover remains an anchored, non-modal panel with an explicit close button, error feedback and a high-contrast one-time-code inset. Do not document modal focus trapping for this component: only the mobile navigation implements that behavior.

## Do's and Don'ts

### Do:
- **Do** keep status text alongside semantic color.
- **Do** preserve compact system typography and tabular measurements.
- **Do** let wide tables scroll horizontally while forms and section layouts reflow.
- **Do** provide task-specific empty messages and inline error feedback.
- **Do** retain the visible Live updates / Polling every 10s connection label.
- **Do** use code, CSS and SVG for this console’s visual assets.

### Don't:
- **Don’t** introduce generated or decorative shipping rasters.
- **Don’t** fabricate activity, performance, sensor readings or ETA.
- **Don’t** style ordinary sections as floating cards with ambient shadows.
- **Don’t** replace labeled outcomes with color alone.
- **Don’t** use animated charts or decorative live pulses.
- **Don’t** hide unavailable measurements behind invented values.


Documentation evidence: current `web/src/style.css`, `web/src/App.tsx`, `web/src/api.ts` and the desktop/mobile overview review captures. Component and state descriptions are source-derived; the captures establish the overview’s rendered composition, not every route or runtime transition. The sidecar contains illustrative control previews, not live coordinator data. Its synthesized tonal ramps are panel previews, not additional shipped palette values.
