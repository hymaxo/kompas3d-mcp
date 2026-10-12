"""Stdio MCP entrypoint. No CAD application launches until explicitly connected."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

from mcp.server.fastmcp import FastMCP, Image
from pydantic import JsonValue

from .models import ExtrusionSpec, RevolutionSpec, SketchSpec
from .worker import ComWorker

worker = ComWorker()

DETAIL_REVIEW = (
    "Carefully distinguish dimension and extension lines from actual part geometry. "
    "Use arrowheads, labels, line styles, endpoints and agreement across views, not color "
    "alone. Crop and inspect ambiguous lines before interpreting them as edges or features. "
    "For every drawing reconstruction and complex 3D model, mandatory detail review: "
    "inspect every source page, view, section, note and model region, including small or "
    "apparently minor features. Keep a coverage ledger linking each feature to source evidence, "
    "dimensions, implementation and verification status. Explicitly check holes and their ends, "
    "recesses, thin walls, steps, fillets, chamfers, threads, repeated-feature counts and spacing, "
    "hidden geometry, handedness, units and tolerances where applicable. "
    "Whenever a detail could be missed or misread, inspect it at readable scale before deciding. "
    "When given a drawing, you MUST crop each complex, crowded or ambiguous region with "
    "blueprint_view and inspect the returned pieces individually at readable scale; an overview "
    "alone is insufficient. Subdivide further until its details can be read, or record the "
    "source limitation. Cover dense sheets with overlapping tiles and inspect tile seams. "
    "Use model_preview crops for visible regions; change orientation or use documented native "
    "zoom/section controls and topology measurements for hidden or unresolved model details. "
    "Cropping cannot reveal occluded geometry or recover pixels absent from a raster. "
    "Cross-check every feature against all relevant views and numerical geometry, not just "
    "the silhouette, bounds or a single isometric image. Review the ledger before delivery. "
    "If evidence or inspection tools are insufficient, record the exact unchecked region and "
    "reason, request the missing source or critical clarification, and continue independent work. "
    "Never silently omit a detail, guess it as fact, or claim full verification with open items. "
)


@asynccontextmanager
async def lifespan(server):
    try:
        yield
    finally:
        worker.close()


mcp = FastMCP(
    "kompas3d",
    lifespan=lifespan,
    instructions=(
        "Create editable KOMPAS-3D models. Dimensions are mm, angles degrees. "
        "Inspect blueprint images before modeling. Track given dimensions separately from assumptions. "
        + DETAIL_REVIEW
        + "Use document and entity IDs returned by tools; never assume the active UI document. "
        "A failed or cancelled mutation may leave partial geometry: inspect before retrying. "
        "Prefer typed tools; api_invoke is an advanced local COM escape hatch, not a sandbox."
    ),
)


@mcp.tool()
async def connect(visible: bool = True) -> dict:
    """Connect to or launch local KOMPAS-3D; return version and application handle."""
    return await worker.call(lambda k: k.connect(visible))


@mcp.tool()
async def attach_active_model() -> dict:
    """Explicitly adopt the active 3D document and return its name/path and stable session ID.

    Use when the user requests work on an already-open model. Verify returned identity.
    """
    return await worker.call(lambda k: k.attach_active())


@mcp.tool()
def sdk_search(query: str, limit: int = 30) -> dict:
    """Find installed SDK topics by interface/member/enum filename substring, e.g. fillet."""
    from .sdk import search

    return search(query, limit)


@mcp.tool()
def sdk_read(topic: str, offset: int = 0, length: int = 16000) -> dict:
    """Read an exact SDK HTML topic as text, including linked topics for navigation."""
    from .sdk import read

    return read(topic, offset, length)


@mcp.tool()
async def create_part(name: str = "Part") -> dict:
    """Create a new native part without replacing the user's open documents."""
    return await worker.call(lambda k: k.new_document(name))


@mcp.tool()
async def open_model(path: str) -> dict:
    """Open native M3D/A3D or import STEP/IGES/STL, returning an explicit document ID."""
    return await worker.call(lambda k: k.open_document(path))


@mcp.tool()
async def create_sketch(document_id: str, spec: SketchSpec) -> dict:
    """Draw circles, arcs and polylines on XY/XZ/YZ or offset planes. Geometry is mm.

    Revolutions need one open two-point construction polyline as the rotation axis.
    Sketch coordinates are local to the selected KOMPAS plane, not world XYZ.
    support_entity_id can select a native face or construction plane instead of plane/offset.
    """
    return await worker.call(lambda k: k.sketch(document_id, spec))


@mcp.tool()
async def extrude(document_id: str, spec: ExtrusionSpec) -> dict:
    """Add or cut a finite-depth extrusion from an existing sketch."""
    return await worker.call(lambda k: k.feature(document_id, spec))


@mcp.tool()
async def revolve(document_id: str, spec: RevolutionSpec) -> dict:
    """Add or cut a revolution. Sketch must contain a profile and construction axis."""
    return await worker.call(lambda k: k.feature(document_id, spec))


@mcp.tool()
async def inspect_model(document_id: str) -> dict:
    """Return bounding box (success,x1,y1,z1,x2,y2,z2), entity IDs and COM handles.

    Session entities are only those created by typed tools, not the full feature tree.
    Use the part's EntityCollection through api_invoke for existing model topology.
    """
    return await worker.call(lambda k: k.inspect_document(document_id))


@mcp.tool()
async def save_model(document_id: str, path: str, overwrite: bool = False) -> dict:
    """Save editable native M3D/A3D at an absolute path; no overwrite by default."""
    return await worker.call(lambda k: k.save(document_id, path, overwrite))


@mcp.tool()
async def export_model(document_id: str, path: str, overwrite: bool = False) -> dict:
    """Export STEP/STL/IGES. Availability depends on installed KOMPAS license/converters."""
    return await worker.call(lambda k: k.export(document_id, path, overwrite))


@mcp.tool()
async def model_preview(
    document_id: str, crop: tuple[float, float, float, float] | None = None
) -> Image:
    """Render the current view, optionally cropping normalized [left,top,right,bottom].

    Crop before downsampling (2400px max) to inspect visible details. This does not
    zoom the CAD camera or expose hidden faces: reorient/zoom/section using documented
    API controls and render again when the source view lacks the required detail.
    """
    import tempfile

    path = str(Path(tempfile.gettempdir()) / f"kompas-preview-{uuid4().hex}.png")
    try:
        await worker.call(lambda k: k.preview(document_id, path))
        return blueprint_view(path, crop=crop)
    finally:
        Path(path).unlink(missing_ok=True)


@mcp.tool()
def blueprint_view(
    path: str, page: int = 1, crop: tuple[float, float, float, float] | None = None
) -> Image:
    """Read local PNG/JPEG/TIFF/WebP or a PDF page (1-based) as an image.

    Optional crop is normalized [left,top,right,bottom] in 0..1. Cropping before
    downsampling helps read small dimensions. Maximum returned dimension is 2400px.
    This renders input; interpretation/OCR is the MCP client's responsibility.
    """
    import io

    from PIL import Image as PILImage

    source = Path(path).resolve()
    if page < 1:
        raise ValueError("page must be >= 1")
    if crop and not (0 <= crop[0] < crop[2] <= 1 and 0 <= crop[1] < crop[3] <= 1):
        raise ValueError("crop must be ordered normalized coordinates in [0,1]")
    if source.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(source) as pdf:
            if page > len(pdf):
                raise ValueError(f"PDF has {len(pdf)} pages")
            sheet = pdf[page - 1]
            rect = sheet.rect
            if crop:
                rect = pymupdf.Rect(
                    rect.width * crop[0],
                    rect.height * crop[1],
                    rect.width * crop[2],
                    rect.height * crop[3],
                )
            scale = min(4, 2400 / max(rect.width, rect.height))
            pix = sheet.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=rect, alpha=False)
            return Image(data=pix.tobytes("png"), format="png")
    with PILImage.open(source) as original:
        if page > getattr(original, "n_frames", 1):
            raise ValueError("Image page is out of range")
        original.seek(page - 1)
        img = original.convert("RGB")
        if crop:
            img = img.crop(
                (
                    int(crop[0] * img.width),
                    int(crop[1] * img.height),
                    int(crop[2] * img.width),
                    int(crop[3] * img.height),
                )
            )
        if img.width == 0 or img.height == 0:
            raise ValueError("Crop is smaller than a pixel")
        img.thumbnail((2400, 2400))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return Image(data=buffer.getvalue(), format="png")


@mcp.tool()
async def api_constants(query: str) -> dict:
    """Find installed SDK enum names/values by case-insensitive substring."""
    return await worker.call(
        lambda k: {n: v for n, v in k.constants.items() if query.lower() in n.lower()}
    )


@mcp.tool()
async def api_describe(handle: str) -> dict:
    """Read generated SDK method signatures and readable/writable properties."""
    return await worker.call(lambda k: k.describe(handle))


@mcp.tool()
async def api_invoke(
    handle: str,
    member: str,
    action: Literal["call", "get", "set"] = "call",
    arguments: list[JsonValue] | None = None,
    value: JsonValue = None,
) -> JsonValue:
    """Advanced unrestricted local COM access, including mutations and file operations.

    Inspect the interface first. Pass COM arguments as {"handle":"..."}.
    Returned COM objects become session handles. This bypasses typed save/ownership
    protections. Use only documented SDK members within the user's requested work.
    False/zero results are returned verbatim and may indicate API failure.
    """
    return await worker.call(lambda k: k.api_call(handle, member, action, arguments or [], value))


@mcp.prompt()
def model_from_blueprint(source: str) -> str:
    """Dimension-led reconstruction of a blueprint into an editable native part."""
    return (
        f"Reconstruct {source} in KOMPAS-3D. Use blueprint_view and detail crops. "
        + DETAIL_REVIEW
        + "Record explicit dimensions, units, projections, datums, holes and uncertainties. "
        "Resolve critical ambiguity before geometry. Build named sketches and features, "
        "check bounds and rendered views against all projections, then save native M3D. "
        "Report assumptions and verification limits."
    )


@mcp.prompt()
def model_from_description(description: str) -> str:
    """Plan and build a dimensioned part from natural language."""
    return (
        f"Create in KOMPAS-3D: {description}\nSeparate required dimensions from "
        "design choices. Choose datum planes and a short editable feature sequence. "
        "Use revolutions for turned shapes and extrusions for prismatic parts. "
        "Verify geometry and save native M3D; report any assumed dimensions. " + DETAIL_REVIEW
    )


from .advanced_tools import register

register(mcp, worker)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
