# FinQuery design system

The product's look, extracted for Claude Design so that decks and mockups match the app.

Rules that define the look:

1. One dark canvas. Sidebar, tabs and page bars sit on `--background`; cards, the composer and
   popovers sit one step lighter on `--card`; hairlines (`--border`, 10 percent white) separate.
2. One accent. The green `--primary` is for the brand mark, the primary action and positive
   deltas only. Never for navigation states, which use a faint tint (`--sidebar-accent`).
3. Three semantic colours besides the accent: `--warning` (amber) for undecided or in progress,
   `--destructive` (red) for negative, `--muted-foreground` for everything secondary.
4. Type is Geist. Titles tight (letter-spacing -0.02em), body 14 to 16 px, labels 12 to 13 px
   uppercase with 0.06 to 0.12em tracking, figures with tabular numerals.
5. Radius scale from 0.625rem: cards `--radius-lg`, nested rows one step down, buttons
   `--radius-md`. Nothing inside a chart is rounded: bars, slices and legend swatches are square.
6. Charts use the six `--chart-*` colours in order, a light horizontal grid only, short euro
   ticks, and a legend only when there is more than one series.
7. Diagrams (for talks) use three box colours: blue for "a model writes", amber for "code
   checks", gray for "code executes or stores". See `previews/flow.html`.

Files: `tokens.css` (the variables, both themes), `previews/*.html` (one card per component,
dark by default; the first line of each is the `@dsCard` marker Claude Design reads).
