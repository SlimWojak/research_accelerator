# Calibration Visual Bible — Build Specification

## Purpose
Interactive HTML calibration tool for Olya (ICT trading strategist) to visually select parameter thresholds for primitive detection algorithms. She sees detections overlaid on real EURUSD 1m price data at multiple threshold values, and selects the view that matches her trading practice.

## Technical Stack
- **Charting:** TradingView Lightweight Charts v4 (CDN)
- **UI:** Vanilla HTML/CSS/JS, no frameworks
- **Data:** JSON files in same directory, loaded via fetch()
- **Design:** Dark theme (trading charts), clean controls, professional

## Shared Design Tokens
- Background: #0a0e17 (dark navy)
- Surface: #131722 (chart bg, same as TradingView)
- Surface 2: #1e222d (card/panel bg)
- Border: #2a2e39
- Text primary: #d1d4dc
- Text muted: #787b86
- Accent teal: #26a69a (bullish/positive)
- Accent red: #ef5350 (bearish/negative)  
- Accent blue: #2962ff (selection/active)
- Accent yellow: #f7c548 (warning/highlight)
- Accent purple: #9c27b0 (VI confluence / special)
- FVG bullish zone: rgba(38, 166, 154, 0.15) with #26a69a border
- FVG bearish zone: rgba(239, 83, 80, 0.15) with #ef5350 border
- Font: 'IBM Plex Sans', system-ui, sans-serif (via Google Fonts)
- Font mono: 'IBM Plex Mono' (for numbers)
- Font sizes: 11px labels, 13px body, 15px headings, 20px page title

## Shared UI Components

### Header Bar
- Page title + primitive name
- Navigation: links to other primitive pages + index
- Timeframe toggle: [1m] [5m] [15m] — default 5m

### Control Panel (left sidebar, 240px)
- Threshold selector (radio buttons or slider)
- Detection count summary per day
- Per-session breakdown
- Olya's task question (styled as a callout)

### Chart Area
- Full remaining width, min-height 500px
- TradingView Lightweight Charts candlestick series
- Overlay markers/shapes for detections
- Day navigation tabs at bottom

### Stats Panel (below chart)
- Summary table: count/day at current threshold
- Direction split (bullish/bearish)
- Per-session counts

## Timeframe Toggle Behavior
- Default: 5m (Olya's primary TF)
- 1m: full resolution drill-down
- 15m: structural context
- Detections always computed on 1m data
- When displaying 5m/15m candles, detection zones overlay at same price levels
- Detection markers placed at the aggregated candle that contains the 1m detection bar

## Day Navigation
- 5 tabs: Mon Jan 8 | Tue Jan 9 | Wed Jan 10 | Thu Jan 11 | Fri Jan 12
- Default: show Jan 9 (representative full day, not Monday open)
- Each day loads its own candle JSON file

## Data Files Available
- candles_{date}.json: {1m: [...], 5m: [...], 15m: [...]} with fields {t, o, h, l, c, atr, s}
- fvg_data.json: {fvgs: [...], thresholds: [...], stats: {...}}
- swing_data.json: {swings: [...], equal_highs: [...], equal_lows: [...], ...}
- asia_data.json: {ranges: [...], thresholds: [...]}
- displacement_data.json: {bars: [...], combos: {...}, ...}
- ny_windows_data.json: {window_a: [...], window_b: [...]}
- ob_data.json: {order_blocks: [...], staleness_bars: [...]}
- levels_data.json: PDH/PDL per day
- metadata.json: all config values

## Lightweight Charts v4 CDN
```html
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
```

## Timestamp Format for Lightweight Charts
Lightweight Charts expects Unix timestamps (seconds). Convert from the ISO-style strings in JSON:
```js
function toTimestamp(timeStr) {
    return Math.floor(new Date(timeStr.replace(' ', 'T') + 'Z').getTime() / 1000);
}
```

## Perplexity Attribution
Include in every HTML file's <head>:
```html
<!--
   ______                            __
  / ____/___  ____ ___  ____  __  __/ /____  _____
 / /   / __ \/ __ `__ \/ __ \/ / / / __/ _ \/ ___/
/ /___/ /_/ / / / / / / /_/ / /_/ / /_/  __/ /
\____/\____/_/ /_/ /_/ .___/\__,_/\__/\___/_/
                    /_/
        Created with Perplexity Computer
        https://www.perplexity.ai/computer
-->
<meta name="generator" content="Perplexity Computer">
<meta name="author" content="Perplexity Computer">
<meta property="og:see_also" content="https://www.perplexity.ai/computer">
<link rel="author" href="https://www.perplexity.ai/computer">
```

And in footer:
```html
<a href="https://www.perplexity.ai/computer" target="_blank" rel="noopener noreferrer">Created with Perplexity Computer</a>
```
