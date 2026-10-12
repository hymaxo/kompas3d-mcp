---
name: kompas-modeling
description: Create and edit native КОМПАС-3D parts from text descriptions, dimensions, sketches, and design references using the kompas3d MCP server. Use for engineering solid models in KOMPAS, including shafts, plates, brackets, housings, and model changes. Does not route Blender mesh or artistic sculpting tasks.
---

# KOMPAS modeling

Use the `kompas3d` MCP server. Tool prefixes vary by client; the names below are their suffixes. The server is a CAD executor; you interpret requirements and choose the construction sequence. Keep native editable M3D as the primary deliverable.

## Translate intent into geometry

Extract required dimensions, interfaces, symmetry, hole patterns, material, fit, and output formats. Convert dimensions to mm and angles to degrees. Separate specified values from chosen defaults. Ask only about missing information that changes fit, function, or the interpretation of the object. For an exploratory concept, choose proportional dimensions and disclose them.

Choose a datum and short feature sequence before construction. Place symmetric objects around the origin, and reference functional mating surfaces when that is more useful. Prefer a revolved axial section for a turned part, extrusions for prismatic geometry, and repeated sketches for simple repeated cuts. Add edge treatments after structural features. See [feature recipes](references/recipes.md) for concrete tool inputs.

For a drawing or scan, use `$kompas-blueprints` if available, or follow the same dimension-led process: inspect all views, resolve hidden depth and projection, and preserve a record of assumptions before creating geometry.

## Build with explicit identity

1. `connect`, then `create_part` for a new design. Use `open_model` for a file, or `attach_active_model` only when the user requests the currently open model. Verify its returned name/path. Never choose a document by UI focus midway through a build.
2. `create_sketch` returns `sketch_id`; `extrude` and `revolve` consume it with the same `document_id`. Give sketches and operations semantic names such as `Mounting holes Ø6` rather than `Sketch 7`.
3. Use `inspect_model` after meaningful changes. Its measurements include volume in mm³, surface area in mm², body count, and mass in kg. Mass uses the model's density and is not evidence that the correct material was assigned.
4. `model_preview` returns the current view. Check hole placement, handedness, and proportions visually as well as numerically. `inspect_model` bounds are `[success,xmin,ymin,zmin,xmax,ymax,zmax]`. Bounds do not establish that holes are correct; compare volume and inspect topology.
5. `save_model` to an absolute `.m3d` path. Export only requested formats with `export_model`. Existing paths require an explicit overwrite choice. Provide saved paths and concise assumptions/verification notes.

## Mandatory detail review for complex models

Maintain a compact feature/region checklist linking requirements to model features
and verification evidence. Inspect every region, including small edge treatments,
holes and their ends, recesses, wall thickness, internal geometry, interfaces and
repeated-feature counts/spacing. For drawings, use the coverage ledger described
in `$kompas-blueprints`; include every view, section and annotation.

Any plausible risk of overlooking or misinterpreting a detail requires a closer
inspection. Use overlapping `blueprint_view` crops for source details and
`model_preview(document_id, crop=[left,top,right,bottom])` for visible model regions.
When given a drawing, cropping each complex, crowded or ambiguous region and
examining the returned pieces individually is mandatory; a full-sheet overview
does not satisfy this check. Subdivide further if the details remain unreadable.
Check crop boundaries. Cropping does not improve the source resolution or expose
hidden geometry: use documented native zoom, orientation or section controls and
topology measurements where needed. Cross-check features numerically and from
all relevant directions, not only a single isometric view or overall bounds.

Audit the checklist before delivery. Record and disclose each unchecked feature,
the reason and the evidence needed to resolve it; ask for missing critical input
while continuing independent work. Do not silently simplify uncertain details or
describe a model as fully verified while any check remains unresolved.

## Geometry rules

- Sketch coordinates are local 2D coordinates on XY, XZ, or YZ. On XY, positive normal is +Z. Determine other plane orientations from a small measured feature or SDK placement data rather than guessing from the rendered screen.
- Extrusion `reverse=false` follows the sketch normal for both add and cut. The server normalizes API5's inverted cut convention. `reverse=true` goes opposite. Offset sign follows the base-plane normal.
- A closed polyline lists each vertex once; omit a repeated endpoint. Separate nested closed loops make holes in an extruded profile. Crossed contours, touching loops, and zero-length edges can invalidate a solid even if sketch drawing succeeds.
- A revolution sketch needs exactly one straight open construction polyline for its axis. Keep the section on one side of it. Full rotation is 360 degrees; radius and diameter are distinct.
- Typed sketches are editable native geometry, but not automatically dimension-constrained. Use `list_variables` / `set_variable` for native driving parameters and expressions; `treat_edges` for fillets/chamfers; `list_entities` for current solid topology; `create_feature` / `update_feature` for documented native definitions. For constraints, assemblies, lofts, sweeps and patterns, read [advanced SDK work](references/advanced.md).
- Feature creation checks material volume change. An error can leave an inspectable feature or sketch behind. Do not blindly replay failed or timed-out mutations, and do not delete unrelated geometry.
- Document IDs, entity IDs, and COM handles live only for this server session. Reopen or reattach after a restart and rediscover topology.

If a tool hangs, the application may be waiting for a license or modal dialog. A timeout cannot cancel a running COM operation. Check the application and inspect the result once it recovers before retrying. Do not kill KOMPAS with unsaved work.

## Advanced operation selection

For native shell, rib, draft, loft, sweep, hole, pattern, mirror, Boolean,
face-edit or sheet-metal work, load `$kompas-api` and its operation reference.
Use the installed tool schema to prefer dedicated tools where available;
otherwise follow the documented SDK route. Do not approximate shell or sheet
metal intent with an unconnected set of thin solids. Surface geometry needs
surface-aware checks because zero material volume can be correct.

For model families, constrain functional interfaces and drive dimensions with
variables. For assemblies, retain component occurrences and mates in A3D.
For manufacturing drawings, preserve associative views and native annotations.
When interpreting drawings, carefully distinguish dimension and extension lines
from actual part geometry. Check arrowheads, labels, line styles, endpoints and
agreement across views, not color alone. Crop ambiguous regions before treating
a line as an edge or modeling it as a feature.
The API skill has separate guidance for these workflows.

