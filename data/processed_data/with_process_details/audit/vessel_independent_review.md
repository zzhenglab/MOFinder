# Independent vessel audit

The reviewer read all **1,926 distinct raw vessel descriptions** in the canonical positive and negative processed CSVs. The complete inventory, with positive/negative frequencies, is `vessel_independent_raw_inventory.csv`. No source CSV values were changed by this independent review.

The review used mutually exclusive text batches so that every description was inspected: autoclave/bomb (537), remaining vial (439), remaining tube/Schlenk/ampoule (225), remaining flask/bottle/beaker (253), remaining fluoropolymer vessel (259), other recognizable vessel nouns (181), and descriptions without those nouns (32). These are review batches, **not** recommended final classification frequencies.

## Classification rules requiring care

- A material alone is not a vessel type. Teflon/PTFE can describe a **cap, seal, gasket, stirring paddle, spacer, liner, or vessel body**. Classify the named reaction vessel. For example, `5 L glass reactor with reflux condenser and Teflon-lined mechanical stirrer (two blades)` is a glass reactor; `20 mL glass vial with Teflon-lined screw cap` is a vial.
- `autoclavable` describes suitability and does not mean `autoclave`. Autoclavable bottles and vials retain their physical vessel category.
- Keep explicit distinctions such as `Schlenk flask` versus `Schlenk tube`. `glass reactor with drying tube` is a reactor, because the drying tube is an accessory.
- `20 mL ampulla` is an ampoule/tube variant. `Erlenmeyer (2 L) with condenser` is a flask even without the word flask. `three-neck balloon` is recognizable flask terminology.
- Include explicit rare categories for dishes, crucibles, dialysis bags, capillary/flow reactors, and in situ cells if useful. A broad generic reactor/vessel category is appropriate only when the vessel description itself is genuinely generic. Avoid an unexplained `Other vessel` bucket for recognizable objects.
- Equipment-only descriptions do not establish a vessel type: `block heater`, `ultrasound bath`, `ultrasonic bath`, `electric furnace`, `lyophilizer (freeze dryer)`, `air oven`, `oil bath`, `sand bath in oven`. Similarly, `reflux setup`, `liquid diffusion (layering)`, `vapor diffusion setup`, and `soak, static` are methods rather than physical vessels. Use a missing-vessel label and preserve an audit reason. `spray dryer (AF-88)` identifies specialized equipment but no discrete vessel capacity.
- Pressure alone does not establish an autoclave: a pressure flask or glass pressure tube is still a flask or tube. Explicit autoclave and liner descriptions can be grouped as autoclave/pressure reactor if that broader category is clearly documented.
- Do not infer materials or capacities from manufacturer names, product models, or model suffixes. `Parr 5500 reactor vessel` provides a vessel type but no capacity; `Monowave 50 glass vial` provides a vial but no volume.

## Volume rules and audited exceptions

Use the explicitly reported vessel capacity, not reagent charge, diameter, length, temperature, pressure, product model, or count of vessels. Normalize Unicode spacing/dashes and superscript cubic units. A capacity expressed in L can be converted to mL; cm3/cm³ equals mL; explicitly reported microL units can be converted to mL. Preserve approximate-versus-exact and problematic-source flags in the audit.

| Exact raw description | Defensible handling |
|---|---|
| `23-M L Teflon-lined autoclave` | Normalize the split `M L` typography to mL: 23 mL. |
| `Teflon-lined autoclave (2 × 250 mL)` | 250 mL per vessel, not 500 mL. |
| `PTFE-lined steel autoclave (37 mL; reaction volume 20 mL)` | Vessel capacity is 37 mL; 20 mL is the liquid charge. |
| `DURAN glass tube (12 mm) with PBT screw cap and PTFE-coated gasket; 2 mL suspension charged` | Tube; capacity not reported. Diameter and charge are not capacity. |
| `Teflon-lined autoclave (80 mL) with 25×40 mm vial inside; NaOH solution (2 mL H2O + 2 mL EtOH) at bottom when used` | Outer autoclave capacity 80 mL is explicit; inner vial capacity is not. Mark nested setup and outer-capacity provenance. Do not derive inner capacity from geometry or use the 2 mL charges. |
| `10 mL vial in 100 mL high-pressure autoclave (sapphire windows)` | Two capacities apply to distinct vessels. Mark nested/ambiguous unless a documented policy explicitly selects inner or outer vessel. |
| `4 mL glass vial placed inside 20 mL vial (vapor diffusion)` | Nested capacities 4 and 20 mL; same policy requirement. |
| `1.8-dram glass vial inside 20 mL scintillation vial (vapor diffusion)` | Nested capacities and unspecified dram convention; preserve the ambiguity. |
| `4 mL scintillation vials; crystallization in 20 mL vial` | Explicit final crystallization vessel capacity is 20 mL. |
| `glass vials (1 dram; solution initially in 8 dram vial)` | Final versus initial vessels are distinguished in the text. Do not simply select the last number. |
| `glass vials (2-dram for Zr6 solution; 1.5-dram for linker), sealed` | Two preparation vessels; no unique combined-reaction vessel capacity. |
| `1 L high-pressure flask for conversion; initial step in 100 mL–150 mL vessel` | Two-stage description; final conversion flask explicitly 1,000 mL. The earlier vessel is a range. |
| `Teflon-lined stainless-steel autoclave (20–28 mL)` | A range; do not impute an endpoint or midpoint. |
| `microwave vial (Biotage Initiator, 2–5 mL)` | Range/operating size rather than unique capacity; keep uncertain. |
| `microwave vial (Biotage 0.5–2 mL glass reactor)` | Range/operating size rather than unique capacity; keep uncertain. |
| `1-dram vial or 20 mL scintillation vial` | Alternative vessels; no unique capacity. |
| `PTFE insert in stainless steel high-throughput reactor (300 μL)` | Explicit microL: 0.3 mL. |
| `PTFE insert in stainless steel high-throughput reactor (300 ?L)` | Corrupted unit; flag rather than guess from the similar valid string. |
| `10 L glass vial (sealed), oil bath` | Suspicious literal 10,000 mL capacity. Flag for source verification; do not silently change L to mL. |
| `1 L screw-capped vial` | Unusually large vial; preserve literal 1,000 mL with a size-review flag, or mark uncertain under a stated policy. |
| `Parr 5500 reactor vessel` | Model number is not capacity. |
| `Monowave 50 glass vial` | Model number is not capacity. |
| `35 mL 19/22 flask with air-cooled condenser` | Capacity is 35 mL. Joint size is not capacity. |
| `sealed 10 g sample vial` | Mass label is not volume. |
| `6 dr glass vial` | `dr` is a dram abbreviation; handle consistently with `6-dram glass vial` and `six-dram glass vial`. No silent jurisdiction-specific conversion without a documented convention. |

Bare dram descriptions do not distinguish U.S. and imperial fluid units. A conservative mL feature should mark these as unavailable and retain the raw capacity text and an `ambiguous_unit` audit flag. If conversion uses a specified fluid-dram convention, document it as an assumption and treat all typography and word-number variants consistently.

## Multi-vessel and temporal descriptions

Nested assemblies, alternate vessel choices, and sequential preparation/crystallization descriptions need explicit audit flags. Their vessel family may still be recoverable, but family and capacity must refer to the same selected vessel. Examples include:

- `Teflon-lined autoclave; glass vial`
- `Teflon-lined stainless steel vessel; then glass test tube for layering`
- `Teflon beaker for gel prep; glass test tube for gel diffusion`
- `H-shaped tube (diffusion); slow evaporation of filtrate in open vial`
- `mortar and pestle (grind 15 min); autoclave (bake)`
- `glass vial inside sealed glass jar placed in a metal tube (autogenous pressure)`
- `Teflon reactor (4 mL screw-capped vial inside)`
- `Schott Duran glass reactor in aluminium autoclave`
- `Space-confined glass slide reactor immersed in 100 mL Schott bottle`

For a three-feature control dataset, broad and transparent categories plus explicit missing/ambiguous values are preferable to unsupported fine-grained assignments. The final output audit should publish all raw-to-clean mappings and enumerate every unresolved vessel or capacity description, including low-frequency values.
