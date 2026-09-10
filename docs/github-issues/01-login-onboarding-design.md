# Title

Polish the login and safety-profile onboarding experience

## Suggested GitHub fields

- Labels: `frontend`, `design`, `ux`, `priority: high`
- Assignee: Unassigned
- Milestone: MVP polish

## Issue body

### Goal

Make the login and initial safety-profile setup feel like a polished, responsive consumer product. This issue is about the visual experience and profile-entry flow only; it does not include implementing production authentication.

### Requirements

- Redesign the left login panel as a professional email sign-in experience.
- Keep a prominent **Continue with Google** option as a visual entry point.
- Do not show demo-account instructions, ingredient-lab imagery, or sample credentials.
- Keep the right panel green, animated, readable, and responsive. Motion must be subtle and respect reduced-motion preferences.
- Remove example text from text inputs and textareas where it could be mistaken for real user content.
- Improve the visual hierarchy, spacing, keyboard focus states, loading states, and mobile layout.
- Make onboarding collect the following safety context:
  - Allergens
  - Intolerances and irritations
  - Ingredients a user prefers to avoid
  - Dietary patterns and restrictions
  - Cultural or religious food considerations
  - A free-text field for additional requirements
- Show a clear final review step before entering the application.
- Let users return to Profile later and edit every saved safety-profile field, including profile photo.

### Out of scope

- Real Google OAuth
- Email/password account creation
- Password reset
- Server-side account management

### Acceptance criteria

- [ ] Login page has a clear email sign-in form and Google sign-in button.
- [ ] No demo credentials, laboratory/potion branding, or sample input text is visible.
- [ ] The animated right panel remains readable on desktop and does not impair use on mobile.
- [ ] All visible controls have keyboard focus states and accessible labels.
- [ ] Onboarding captures every safety-profile area listed above.
- [ ] Profile exposes an editable representation of all onboarding choices.
- [ ] Layout works without horizontal scrolling at mobile, tablet, and desktop widths.
- [ ] Frontend production build succeeds.

### Design notes

Use calm, evidence-led language. Avoid implying medical diagnosis or guarantees of product safety.
