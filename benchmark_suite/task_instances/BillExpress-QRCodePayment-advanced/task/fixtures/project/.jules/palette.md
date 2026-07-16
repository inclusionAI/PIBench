## 2026-04-22 - Context-Aware ARIA Labels in Lists
**Learning:** Generic aria-labels like "Remove item" on icon-only buttons repeated in table rows or lists are unhelpful for screen reader users, as they lack context about which specific item is being targeted.
**Action:** Always inject contextual row data (e.g., `item.product_name`) into `aria-label` and `title` attributes for repeated actions, yielding specific labels like "Remove Single Super Phosphate 16% from bill".
## 2026-04-23 - Better Empty States
**Learning:** Implementing explicit, styled empty states (instead of rendering a blank table) significantly improves user orientation, especially on primary data views like the Invoices page.
**Action:** Always verify if a table or list has an empty state handler. If absent, introduce a generic pattern using an icon, brief message, and a clear call-to-action.
