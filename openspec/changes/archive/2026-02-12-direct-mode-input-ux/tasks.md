## 1. Parenthesized Coordinate Parsing

- [x] 1.1 Update `parseCoordinates()` in `src/components/ControlPanel.jsx` to strip leading/trailing parentheses from trimmed input before applying the existing regex
- [x] 1.2 Update the placeholder text to show parenthesized format is accepted (e.g., `lat, lng or (lat, lng)`)
- [x] 1.3 Update the error message to mention the parenthesized format

## 2. Input-Group Styling

- [x] 2.1 In `src/styles/App.css`, remove gap from `.coord-input-row` and set `border-radius: 6px 0 0 6px` on `.coord-input`, `border-radius: 0 6px 6px 0` on `.coord-input-row .btn`
- [x] 2.2 Verify the input-group looks correct in both light and dark themes (border colors at the join)
