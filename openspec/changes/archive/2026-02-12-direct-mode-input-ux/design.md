## Context

Direct mode in ControlPanel lets users type coordinates and click "Go" to set device location. Currently the input and button are side-by-side with an 8px gap, which visually separates them. The `parseCoordinates()` regex only accepts bare `lat, lng` — not the `(lat, lng)` format common from copy-pasting coordinates from Google Maps or code.

## Goals / Non-Goals

**Goals:**
- Make the Go button visually attached to the input field (input-group pattern)
- Accept parenthesized coordinates `(lat, lng)` in addition to bare `lat, lng`

**Non-Goals:**
- No changes to coordinate validation logic (bounds remain [-90,90] / [-180,180])
- No changes to backend location setting
- No support for other formats (DMS, UTM, etc.)

## Decisions

### 1. Input-group styling approach
Join the input and Go button by removing the gap, giving the input `border-radius: 6px 0 0 6px` and the button `border-radius: 0 6px 6px 0`. This is a standard input-group pattern that visually communicates the button acts on the input.

### 2. Parentheses stripping vs. regex expansion
Strip parentheses from the trimmed input before applying the existing regex, rather than making the regex more complex. This keeps the parsing logic readable and handles edge cases like extra whitespace inside parentheses naturally.

## Risks / Trade-offs

- Minimal risk. Both changes are purely frontend, isolated to ControlPanel and its CSS.
