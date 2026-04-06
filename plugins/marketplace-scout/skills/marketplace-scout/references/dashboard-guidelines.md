# Dashboard Compatibility Guidelines

Rules for modifying the marketplace-scout dashboard (`assets/dashboard/`).

## Data Validation

The dashboard performs runtime validation on CSV and JSON data — malformed data will surface warnings to the user. Ensure CSV schema and `grade_breakdown` JSON shape conform exactly to the specifications in SKILL.md Step 7.

## Accessibility

- All interactive elements must have keyboard navigation: `role="button"` (or appropriate ARIA role), `tabIndex={0}`, and `onKeyDown` handler for Enter/Space activation
- Respect `prefers-reduced-motion` — do not add new animations or transitions without wrapping them in a `@media (prefers-reduced-motion: no-preference)` guard

## Styling

- Use CSS classes defined in `global.css` (`.card`, `.chip`, `.badge`, `.btn`, `.mono-label`, `.input`, etc.) — do not use inline `style={{}}` objects
- All features must work at 320px viewport width minimum
- Test responsive behavior before finalizing
