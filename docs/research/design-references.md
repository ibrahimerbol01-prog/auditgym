# Design references (Nov 20) and what we took

Five sites studied for patterns, not looks. Sources: the sites themselves and their makers' write-ups.

| Site | Why it matters | What we took | What we did not take |
|---|---|---|---|
| Stripe | Reference for fintech marketing; animated WebGL gradient, light-weight type (Söhne 300), progressive disclosure | Discipline: a flat, considered colour beats a cheap imitation of an effect | WebGL gradients, their indigo |
| Linear | Reference for tool UI; LCH colour, themes from 3 variables (base, accent, contrast), Inter Display for headings, pixel alignment | Order and alignment; a classification table instead of icon cards | Rebuilding the palette in LCH (too risky before the deadline) |
| Mercury | "Quiet luxury" banking: editorial serif headline + sans body, near-black text, one action colour, hairline depth, mono for data, 120/200/320 ms motion, no hover lifts | Motion tokens 120/200/320 ms, no lifting buttons, hairlines instead of shadows, mono only for data | Their mint band and indigo |
| Bruno Simon | Portfolio you drive as a game; teaches interaction without words (the car hits the name first) | "Touch it in the first seconds": the hero's "check it yourself" link opens train-03 with the cited invoice selected | 3D / game navigation (slow, hurts information seekers) |
| The Pudding | Visual essays; data-driven story shapes (e.g. a V: wide → one detail → wide) | V-shape for the demo video: 475 ledger rows → one invoice → one figure (43 861.60) → 4 policies on the same episodes | Long-form scrollytelling on the site |

Our resulting rules live in `docs/DESIGN_BRIEF.md`.
