---
name: kompas-blueprints
description: Reconstruct editable КОМПАС-3D engineering models from dimensioned blueprints, scanned drawings, PDF sheets, orthographic views, or reference photos. Use for drawing-to-solid interpretation and checking a KOMPAS model against its source, including Russian technical drawings.
---

# Blueprint to native KOMPAS model

Use the `kompas3d` MCP tools to view source pages and construct native geometry.
The server renders images; you read the dimensions and reason across views.
Do not present it as automatic OCR, an image-to-CAD neural model, or a guarantee
that an underdefined drawing uniquely determines a solid.

## Read the source before building

Call `blueprint_view` for the whole image or each relevant PDF page (1-based).
Crop crowded dimension labels with normalized `[left,top,right,bottom]` rectangles.
Read the title block, units, scale, projection symbol, revisions, sections, details,
and manufacturing notes. A PDF may contain multiple different parts.

Detail inspection is mandatory, not an optional final polish. When given a drawing,
after the overview you MUST crop every complex, crowded or ambiguous region
with `blueprint_view` and inspect each returned piece separately. Do not rely on
the full-sheet image alone. Subdivide complex regions again until their details
are readable, or explicitly record that the source resolution is insufficient.
Systematically cover every page and view at a scale where the smallest marks and
labels are legible. For dense sheets, use overlapping `blueprint_view` crops;
inspect the overlaps so features crossing crop boundaries are not lost. Start
with quadrants such as `[0,0,0.55,0.55]` and `[0.45,0,1,0.55]`, then subdivide
where needed. Include margins, notes, detail callouts and section references.
Whenever there is any plausible risk of misreading or overlooking a detail,
inspect that region separately and reconcile it with the other views.

Use [drawing interpretation](references/drawing-interpretation.md) for sections,
Russian notation, ambiguous dimensions, and photographic references.
Record a compact dimension ledger as a sidecar Markdown or JSON file alongside
the eventual model. Each entry should identify the feature, value and unit,
source page/view, and whether it is explicit, derived, estimated, or unresolved.
Do not silently promote an estimated pixel measurement into an explicit dimension.
Also track coverage: source page/view/crop, feature or annotation, interpretation,
corresponding model feature, verification evidence and unresolved status. Include
small holes, blind-hole ends, counterbores, grooves, shoulders, thin walls, threads,
fillets, chamfers, pattern counts/spacing, hidden lines, handedness and tolerances
where present. Account for annotations that do not create solid geometry too.

Infer the minimum solid that satisfies all views. Establish datum surfaces and
axes, reconstruct the external envelope, then identify cavities, holes, recesses,
and repeated features. Account for hidden lines and section hatching. Resolve
conflicting dimensions or a missing critical depth with the user; continue any
independent interpretation work while waiting.

## Construct and cross-check

Carefully distinguish dimension and extension lines from actual part geometry.
Use arrowheads, labels, line styles, endpoints and agreement across views, not
color alone. Crop and inspect ambiguous lines before interpreting them as edges
or modeling them as features.

Use `connect`, `create_part`, `create_sketch`, `extrude` / `revolve` with explicit
document IDs. Use `$kompas-modeling` when available for native feature recipes and
advanced SDK operations. These tools take mm/degrees, not drawing pixels.

Choose a feature sequence that follows the part's geometry: turned axial section,
extruded silhouette, then pockets/holes and edge treatments. For mixed shapes,
use several native features rather than tracing every line as a single contour.
Native sketches are editable but not automatically dimension-constrained.

Verify against every independent view. `inspect_model` returns bounds, volume,
body count and entity handles. `model_preview` supplies the current model view;
use documented API view controls to inspect other orientations when needed.
Compare hole centers, diameters, depths, shoulder positions, wall thickness, and
symmetry to the ledger. Verify subtractive volume for simple cuts. A matching
bounding box alone cannot prove a correct reconstruction.

Before delivery, audit every ledger entry against the completed model. Inspect
small visible regions with `model_preview(document_id, crop=[left,top,right,bottom])`.
For occluded geometry, change orientation or use documented native zoom/section
controls and topology measurements. A crop only isolates existing pixels: it
cannot reveal hidden faces or restore unreadable raster detail. Request a clearer
source or missing view when necessary, identify the exact affected feature, and
continue independent work. Every entry must be verified or explicitly reported as
unresolved; never silently omit a detail or claim full verification with open items.

Save M3D and requested exchange formats. Deliver the model path, ledger path,
source identifier, key checks, and any remaining ambiguity. If a dimension was
not available, say what you assumed and which feature it affects.
