# Design System Specification: The Fluid Authority

## 1. Overview & Creative North Star
**Creative North Star: "The Empathetic Architect"**

This design system is built to resolve the tension between emotional human distress and cold financial precision. We are moving away from the "SaaS-in-a-box" aesthetic toward a **High-End Editorial** experience. 

The system treats the interface not as a series of boxes, but as a **layered landscape**. We break the rigid, generic grid through intentional asymmetry—using generous whitespace to guide the eye and overlapping elements to create a sense of organic flow. For the User Side, we prioritize "The Breath"—wide margins and soft transitions. For the Admin Side, we pivot to "The Lens"—retaining the sophisticated palette but tightening the focus for high-density intelligence.

---

## 2. Color & Surface Theory
We reject the primitive use of lines to define space. In this system, **edges are felt, not seen.**

### The "No-Line" Rule
Explicitly prohibited: 1px solid borders for sectioning or containment. 
*   **Alternative:** Boundaries must be defined solely through background color shifts. Use `surface-container-low` (#f5f3ef) sections sitting on a `background` (#fbf9f5) or subtle tonal transitions.

### Surface Hierarchy & Nesting
Treat the UI as a physical stack of fine paper. 
*   **Layer 1 (The Foundation):** `surface` (#fbf9f5).
*   **Layer 2 (Content Grouping):** `surface-container-low` (#f5f3ef).
*   **Layer 3 (Interactive Elements/Cards):** `surface-container-lowest` (#ffffff) to provide a soft, natural lift.
*   **Depth through Tone:** Use `surface-container-high` (#eae8e4) only for recessed elements like search bars or inactive areas.

### The "Glass & Gradient" Rule
To elevate the "Soft UI" aesthetic:
*   **Aurora Gradients:** Use a subtle linear gradient from `primary` (#000666) to `primary-container` (#1a237e) for high-impact CTAs.
*   **Glassmorphism:** For floating modals or navigation bars, use `surface` at 80% opacity with a `24px` backdrop blur. This allows the "warmth" of the background to bleed through, ensuring the UI feels integrated rather than "pasted on."

---

## 3. Typography: Editorial Authority
We utilize a dual-typeface approach to balance character with utility.

*   **Display & Headlines (Manrope):** Chosen for its geometric precision and modern warmth. Use `display-lg` (3.5rem) with tighter letter-spacing (-0.02em) for a bold, editorial feel in the user flow.
*   **Body & Labels (Inter):** The workhorse. Inter provides maximum legibility for complex financial data. 
*   **Hierarchy as Narrative:** Use high contrast between `headline-lg` and `body-md`. Large headlines should feel like titles in a premium magazine, while body text remains humble and readable.

---

## 4. Elevation & Depth
Depth is a functional tool, not a stylistic flourish.

*   **Tonal Layering:** Avoid shadows for static components. A `surface-container-lowest` card on a `surface-container-low` background is the preferred method for defining objects.
*   **Ambient Shadows:** For "Active" or "Floating" states, use a double-layered shadow:
    *   `Shadow 1: 0px 4px 20px rgba(27, 28, 26, 0.04)`
    *   `Shadow 2: 0px 8px 40px rgba(27, 28, 26, 0.06)`
*   **The "Ghost Border" Fallback:** If accessibility requires a border (e.g., input fields), use `outline-variant` (#c6c5d4) at **20% opacity**. Never use 100% opaque borders.

---

## 5. Components & Intentional Density

### The Density Pivot
*   **User Side (Human-Centric):** Use `xl` (3rem) corner radius. Spacing should follow a "Generous" rhythm (32px+ between blocks).
*   **Admin Side (Data-Centric):** Use `sm` (0.5rem) corner radius. Spacing follows a "Compact" rhythm (8px-12px between blocks) to maximize data density without sacrificing the premium feel.

### Key Primitive Styles
*   **Buttons:** 
    *   *Primary:* Gradient fill (Indigo to Deep Indigo), `full` (9999px) roundness for users, `sm` (0.5rem) for admins. 
    *   *Tertiary:* No background. Use `primary` text with an underline that only appears on hover.
*   **Input Fields:** Use `surface-container-lowest` fill. Use a bottom-only "active" indicator (2px Teal) rather than a full box stroke to maintain an open, airy feel.
*   **Cards & Lists:** **Strictly forbid divider lines.** Use vertical white space (8px for lists, 32px for cards) or a `surface-variant` hover state to create separation.
*   **Status Badges:** Use `secondary-container` (#81f3e5) with `on-secondary-container` (#006f66) text. The high-radius "pill" shape is mandatory to soften the "financial" nature of the data.

---

## 6. Do’s and Don’ts

### Do:
*   **Do** use asymmetrical layouts. Place a headline on the left and a supporting card offset to the right with 64px of padding.
*   **Do** use "Teal/Sage" accents (`secondary`) to highlight positive actions or completed steps—it acts as a "calming signal."
*   **Do** use `display-sm` for large numerical data (e.g., claim amounts) to give them weight and importance.

### Don't:
*   **Don't** use pure black (#000000). Use `on-surface` (#1b1c1a) for all text to maintain the "warm neutral" ethos.
*   **Don't** use standard "Drop Shadows." If an element needs to pop, use a tonal background shift first.
*   **Don't** cram information on the user-facing side. If a process has 10 steps, show 1 step at a time with a fluid, aurora-style progress bar.