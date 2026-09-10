# Title

Connect catalog search, product analysis, and history in the frontend

## Suggested GitHub fields

- Labels: `frontend`, `catalog`, `ux`, `priority: medium`
- Assignee: Unassigned
- Milestone: Product catalog MVP

## Issue body

### Goal

Make searching for a product, analyzing it, and finding it again in History feel like one continuous and responsive product flow.

### Requirements

- Make **Catalog** the dedicated product and company search view.
- Let a user search by product name or brand/company.
- Display product cards with:
  - Product image when a verified image URL is available
  - A graceful visual fallback when no image is available
  - Brand/company name
  - Product name
  - Category
  - Data-source/verification state when available
- Let a user choose **Analyze** directly from a catalog result.
- Show the selected product’s real catalog name, brand, category, and image/fallback in the analysis result instead of “Untitled product analysis.”
- Preserve the product context when the user navigates away and returns to the current analysis.
- Save catalog-driven analyses into History with the selected product name, company, image/fallback, score, and date.
- Keep the internal History navigation with **Products** and **Ingredients** tabs.
- Let the user open a previous product analysis from History.
- Provide polished loading, empty, no-results, API-error, and success states.
- Use subtle transitions for result cards and history entries; respect reduced-motion preferences.
- Ensure the flow is usable on mobile and desktop.

### Out of scope

- Product recommendations
- Price comparison
- Real-time product availability
- Changing the evidence score solely because a product has an image

### Acceptance criteria

- [ ] Catalog searches the product API by product name and brand/company.
- [ ] Search results show an understandable empty state when no product is found.
- [ ] Selecting Analyze opens the analysis view and preserves selected product metadata.
- [ ] Analysis results show the selected product name and brand.
- [ ] History stores and displays catalog product information rather than generic placeholder text.
- [ ] The Products and Ingredients History tabs both work.
- [ ] Product cards use an image only when available and use a non-broken fallback otherwise.
- [ ] Loading and error states are visible and actionable.
- [ ] The frontend build succeeds and the layouts remain responsive.

### Design notes

Use clear labels such as “Catalog data,” “Demo catalog record,” or “Label last verified” when the API provides that information. Do not imply that an analysis is medical advice or a guarantee of safety.
