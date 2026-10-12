"""Live exact-projection and associative-dimension acceptance on a synthetic plate.

Run in KOMPAS's interactive Windows session. The saved original is protected by
a separate working copy and a hash check. Only documents created/opened by this
run are closed. Native geometry and dimension updates must survive reopening.
After the first edit, subsequent edits use distinct source revision files and
explicitly rebind the existing views; repeated overwrites can retain stale views.
"""

import hashlib
import json
import math
import shutil
from pathlib import Path
from uuid import uuid4

from kompas_mcp import documents, parameters
from kompas_mcp.backend import Kompas, require
from kompas_mcp.models import ExtrusionSpec, SketchSpec

WIDTH = 80.0
HEIGHT = 50.0
INITIAL_THICKNESS = 8.0
UPDATED_THICKNESS = 12.0
PERSISTENCE_PROBE_THICKNESS = 16.0
THICKNESS_VARIABLE = "plate_thickness"
TOLERANCE = 1e-6


def _close_enough(actual, expected):
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=TOLERANCE)


def _view(k, drawing, number):
    native = documents._drawing_view(k, drawing["document"]["handle"], number)
    return documents._cast(k, native, "IAssociationView")


def _geometry(k, view):
    collection = documents._cast(k, view, "IDrawingContainer").LineSegments
    assert collection.Count == 4, f"View {view.Number}: expected four projected edges"
    lines = [documents._cast(k, collection.Item(i), "ILineSegment") for i in range(4)]
    endpoints = [[line.X1, line.Y1, line.X2, line.Y2] for line in lines]
    xs = [value for edge in endpoints for value in (edge[0], edge[2])]
    ys = [value for edge in endpoints for value in (edge[1], edge[3])]
    bounds = [min(xs), min(ys), max(xs), max(ys)]
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    assert width > TOLERANCE and height > TOLERANCE, bounds

    # A count and bounding box alone could also describe crossing/duplicated
    # lines. Verify that these are the four distinct sides of this rectangle.
    sides = set()
    for x1, y1, x2, y2 in endpoints:
        if _close_enough(y1, y2) and _close_enough(abs(x2 - x1), width):
            assert _close_enough(min(x1, x2), bounds[0]), endpoints
            assert _close_enough(max(x1, x2), bounds[2]), endpoints
            if _close_enough(y1, bounds[1]):
                sides.add("bottom")
            elif _close_enough(y1, bounds[3]):
                sides.add("top")
        elif _close_enough(x1, x2) and _close_enough(abs(y2 - y1), height):
            assert _close_enough(min(y1, y2), bounds[1]), endpoints
            assert _close_enough(max(y1, y2), bounds[3]), endpoints
            if _close_enough(x1, bounds[0]):
                sides.add("left")
            elif _close_enough(x1, bounds[2]):
                sides.add("right")
    assert sides == {"bottom", "top", "left", "right"}, endpoints
    return {"bounds_mm": bounds, "size_mm": [width, height], "edges_mm": endpoints}, lines


def _expected_sizes(thickness):
    return {"front": [WIDTH, HEIGHT], "top": [WIDTH, thickness], "left": [thickness, HEIGHT]}


def _identify_views(k, drawing, created):
    result = {}
    for item in created:
        view = _view(k, drawing, item["number"])
        geometry, _ = _geometry(k, view)
        matches = [
            role
            for role, expected in _expected_sizes(INITIAL_THICKNESS).items()
            if all(_close_enough(a, b) for a, b in zip(geometry["size_mm"], expected))
        ]
        assert len(matches) == 1 and matches[0] not in result, geometry
        result[matches[0]] = view.Number
    assert set(result) == {"front", "top", "left"}, result
    return result


def _dimension_state(k, view, thickness, require_partner_links=False):
    collection = documents._cast(k, view, "ISymbols2DContainer").LineDimensions
    assert collection.Count == 1, f"Expected one thickness dimension, got {collection.Count}"
    dimension = documents._cast(k, collection.Item(0), "ILineDimension")
    text = documents._cast(k, dimension, "IDimensionText")
    extra = documents._cast(k, dimension, "IDrawingObject1")
    constraints = extra.Constraints
    # SDK idrawingobject1_constraints.html: a single result can be VT_DISPATCH,
    # whereas multiple results are VT_ARRAY|VT_DISPATCH.
    if constraints is None:
        constraints = []
    elif not isinstance(constraints, (tuple, list)):
        constraints = [constraints]
    constraints = [documents._cast(k, item, "IParametriticConstraint") for item in constraints]
    association_type = k.constants["ksCAssociation"]
    merge_type = k.constants["ksCMergePoints"]
    assert association_type == 12, "Unexpected installed association constraint enum"
    assert merge_type == 11, "Unexpected installed coincident-points constraint enum"
    _, projected_lines = _geometry(k, view)
    projected_references = {int(line.Reference) for line in projected_lines}
    details = []
    for item in constraints:
        detail = {
            "type": item.ConstraintType,
            "valid": bool(item.Valid),
            "index": item.Index,
            "partner_index": item.PartnerIndex,
        }
        try:
            partners = item.Partner
            if partners is None:
                partners = []
            elif not isinstance(partners, (tuple, list)):
                partners = [partners]
            detail["partner_references"] = [int(partner.Reference) for partner in partners]
        except Exception as exc:  # noqa: BLE001 - retain native link diagnostics on failure
            detail["partner_error"] = repr(exc)
            detail["partner_references"] = []
        details.append(detail)

    def linked_to_projection(detail):
        references = set(detail["partner_references"])
        # In the tested installation reprojection can leave valid endpoint
        # constraints whose Partner getter returns no dispatch. Require actual
        # edge references when binding the dimension; after regeneration rely
        # additionally on repeated measured edits across a save/reopen boundary.
        # An unreadable or nonempty foreign partner is still a failure.
        return (
            "partner_error" not in detail
            and (bool(references) or not require_partner_links)
            and references <= projected_references
        )

    associations = [item for item in details if item["type"] == association_type]
    merged_points = [item for item in details if item["type"] == merge_type]
    direct_association = (
        len(associations) == 1
        and associations[0]["valid"]
        and linked_to_projection(associations[0])
    )
    # Native KOMPAS can decompose the ksCAssociation creation request into two
    # ksCMergePoints records. Both dimension endpoints must remain validly
    # attached to projected edges; the creation enum need not be the stored type.
    endpoint_association = (
        len(merged_points) == 2
        and {item["index"] for item in merged_points} == {0, 1}
        and all(item["valid"] and linked_to_projection(item) for item in merged_points)
    )
    result = {
        "nominal_mm": float(text.NominalValue),
        "auto_nominal": bool(text.AutoNominalValue),
        "constraint_types": [item["type"] for item in details],
        "constraints": details,
        "projected_line_references": sorted(projected_references),
        "partner_links_required": require_partner_links,
        "direct_association": direct_association,
        "endpoint_association": endpoint_association,
        "endpoints_mm": [dimension.X1, dimension.Y1, dimension.X2, dimension.Y2],
    }
    assert direct_association or endpoint_association, result
    assert result["auto_nominal"] and _close_enough(result["nominal_mm"], thickness), result
    assert _close_enough(abs(dimension.X2 - dimension.X1), thickness), result
    assert _close_enough(dimension.Y1, dimension.Y2), result
    return result


def _create_dimension(k, drawing, number):
    view = _view(k, drawing, number)
    geometry, lines = _geometry(k, view)
    bottom = [
        line
        for line in lines
        if _close_enough(line.Y1, line.Y2)
        and _close_enough(line.Y1, geometry["bounds_mm"][1])
    ]
    assert len(bottom) == 1
    line = bottom[0]
    added = documents.draw_linear_dimension(
        k,
        drawing["document"]["handle"],
        line.X1,
        line.Y1,
        line.X2,
        line.Y2,
        (line.X1 + line.X2) / 2,
        line.Y1 - 12,
        orientation="horizontal",
        view_number=number,
    )
    dimension = k.handles[added["object"]["handle"]]
    extra = documents._cast(k, dimension, "IDrawingObject1")
    association = require(extra.NewConstraint(), "allocate dimension association")
    association.ConstraintType = k.constants["ksCAssociation"]
    # Installed SDK newconstraint_example.html explicitly uses one dispatch
    # partner when a dimension associates with a single geometric object.
    association.Partner = line
    require(association.Create(), "associate thickness dimension with projected edge")
    return _dimension_state(k, view, INITIAL_THICKNESS, require_partner_links=True)


def _drawing_state(k, drawing, roles, source, thickness):
    views = k.handles[drawing["views"]["handle"]]
    assert views.Count == 4, f"Expected system view plus three projections, got {views.Count}"
    result = {}
    for role, expected in _expected_sizes(thickness).items():
        view = _view(k, drawing, roles[role])
        geometry, _ = _geometry(k, view)
        native_source = Path(view.SourceFileName)
        assert native_source.is_file() and native_source.samefile(source), view.SourceFileName
        assert view.Valid and not view.UseOcclusion, f"View {view.Number}: invalid/draft projection"
        assert all(_close_enough(a, b) for a, b in zip(geometry["size_mm"], expected)), geometry
        result[role] = {
            "number": view.Number,
            "object_count": view.ObjectCount,
            "source": str(native_source),
            "draft_projection": bool(view.UseOcclusion),
            **geometry,
        }
        if role == "left":
            result[role]["thickness_dimension"] = _dimension_state(k, view, thickness)
    return result


def _model_state(k, model, thickness):
    measured = k.inspect_document(model["document_id"])
    expected_bounds = [0, 0, 0, WIDTH, HEIGHT, thickness]
    assert measured["bounds_raw"][0], measured
    assert all(
        _close_enough(a, b) for a, b in zip(measured["bounds_raw"][1:], expected_bounds)
    ), measured
    assert measured["measurements"]["body_count"] == 1, measured
    assert _close_enough(measured["measurements"]["volume_mm3"], WIDTH * HEIGHT * thickness)
    values = parameters.list_variables(k, model["document_id"])["variables"]
    variables = [item for item in values if item["name"] == THICKNESS_VARIABLE]
    assert len(variables) == 1 and _close_enough(variables[0]["value"], thickness), variables
    return {"bounds_mm": measured["bounds_raw"][1:], "measurements": measured["measurements"]}


def _rebind_views(k, drawing, roles, source):
    views = [_view(k, drawing, roles[role]) for role in ("front", "top", "left")]
    references = [int(view.Reference) for view in views]
    # Rebind every view before rebuilding the projection group. Updating only
    # one view leaves other views associated with the preceding revision.
    for view in views:
        view.SourceFileName = str(source)
        require(view.Update(), f"update revision source for view {view.Number}")
    for view in views:
        require(view.Rebuild(), f"rebuild revision view {view.Number}")
    document2d = documents._cast(
        k, k.handles[drawing["document"]["handle"]], "IKompasDocument2D1"
    )
    require(document2d.RebuildDocument(), "rebuild revision drawing and associative dimension")
    assert [int(view.Reference) for view in views] == references, "View identity changed"
    return {"source": str(source), "view_references": references}


def _export_png(k, drawing, path):
    from PIL import Image

    assert not path.exists(), path
    reference = k.handles[drawing["document"]["handle"]].Reference
    native = k.api.ksDocument2D(
        require(k.app.ksGetDocumentByReference(reference), "get native 2D document")
    )
    settings = require(native.RasterFormatParam(), "allocate drawing raster settings")
    require(settings.Init(), "initialize drawing raster settings")
    settings.format = k.constants["ksRasterFormatPNG"]
    settings.colorBPP = 24
    settings.extResolution = 150
    require(native.SaveAsToRasterFormat(str(path), settings), "render drawing PNG")
    result = k.file_result(path)
    with Image.open(path) as image:
        assert image.format == "PNG"
        result["pixels"] = list(image.size)
        image.verify()
    return result


def main():
    import pythoncom

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    k = Kompas()
    folder = (
        Path(__file__).resolve().parents[1]
        / "artifacts"
        / f"associative-drawing-{uuid4().hex[:8]}"
    )
    folder.mkdir(parents=True)
    original_path = folder / "original-plate.m3d"
    source_path = folder / "working-plate.m3d"
    drawing_path = folder / "plate-views.cdw"
    original_hash = None
    report = {"passed": False, "folder": str(folder), "steps": []}
    protected_sources = {}
    owned = []

    def own(document):
        owned.append(document["document"]["handle"])
        return document

    def close(document):
        handle = document["document"]["handle"]
        documents.close_document(k, handle, discard_changes=True)
        owned.remove(handle)

    def save(document, path, overwrite=False):
        documents.save_document(k, document["document"]["handle"], str(path), overwrite)

    def record(stage, result):
        report["steps"].append({"stage": stage, **result})
        print(stage, json.dumps(result, ensure_ascii=True), flush=True)

    try:
        report["version"] = k.connect()["version"]
        plate = own(documents.create_document(k, "part"))
        document_id = plate["document_id"]
        sketch = k.sketch(
            document_id,
            SketchSpec(
                name="Synthetic plate outline",
                curves=[
                    {
                        "kind": "polyline",
                        "points": [[0, 0], [WIDTH, 0], [WIDTH, HEIGHT], [0, HEIGHT]],
                    }
                ],
            ),
        )
        feature = k.feature(
            document_id,
            ExtrusionSpec(
                name="Synthetic plate thickness",
                sketch_id=sketch["sketch_id"],
                depth=INITIAL_THICKNESS,
            ),
        )
        variables = parameters.list_variables(k, document_id, feature["feature_id"])["variables"]
        depth = [item for item in variables if _close_enough(item["value"], INITIAL_THICKNESS)]
        assert len(depth) == 1, depth
        parameters.set_variable(
            k, document_id, THICKNESS_VARIABLE, value=INITIAL_THICKNESS, create=True
        )
        parameters.set_variable(
            k,
            document_id,
            depth[0]["name"],
            expression=THICKNESS_VARIABLE,
            feature_id=feature["feature_id"],
        )
        record("original_plate", _model_state(k, plate, INITIAL_THICKNESS))
        save(plate, original_path)
        close(plate)
        original_hash = hashlib.sha256(original_path.read_bytes()).hexdigest()
        shutil.copy2(original_path, source_path)

        working = own(documents.open_document(k, str(source_path)))
        record("working_copy_reopened", _model_state(k, working, INITIAL_THICKNESS))
        close(working)
        drawing = own(documents.create_document(k, "drawing"))
        created = documents.create_standard_views(
            k,
            drawing["document"]["handle"],
            str(source_path),
            ["front", "top", "left"],
            x=60,
            y=170,
        )
        assert created["created_count"] == 3, created
        roles = _identify_views(k, drawing, created["created_views"])
        report["view_numbers"] = roles
        record("dimension_associated", _create_dimension(k, drawing, roles["left"]))
        record("drawing_created", _drawing_state(k, drawing, roles, source_path, INITIAL_THICKNESS))
        save(drawing, drawing_path)
        close(drawing)

        drawing = own(documents.open_document(k, str(drawing_path)))
        record("drawing_reopened", _drawing_state(k, drawing, roles, source_path, INITIAL_THICKNESS))
        report["drawing_before"] = _export_png(k, drawing, folder / "drawing-before.png")
        working = own(documents.open_document(k, str(source_path)))
        parameters.set_variable(k, working["document_id"], THICKNESS_VARIABLE, value=UPDATED_THICKNESS)
        record("working_copy_edited", _model_state(k, working, UPDATED_THICKNESS))
        save(working, source_path, overwrite=True)
        close(working)
        for role in ("front", "top", "left"):
            require(_view(k, drawing, roles[role]).Rebuild(), f"rebuild {role} after source edit")
        document2d = documents._cast(
            k, k.handles[drawing["document"]["handle"]], "IKompasDocument2D1"
        )
        require(document2d.RebuildDocument(), "rebuild drawing and associative dimension")
        document2d = None
        record("drawing_updated", _drawing_state(k, drawing, roles, source_path, UPDATED_THICKNESS))
        save(drawing, drawing_path, overwrite=True)
        close(drawing)

        drawing = own(documents.open_document(k, str(drawing_path)))
        record(
            "updated_drawing_reopened",
            _drawing_state(k, drawing, roles, source_path, UPDATED_THICKNESS),
        )
        # Keep the first working copy at 12 mm. Later edits get new filenames:
        # the tested installation can retain stale geometry when repeatedly
        # overwriting one linked source. Rebinding preserves these native views
        # and their dimension, whose measured updates must still pass below.
        baseline_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        protected_sources[source_path] = baseline_hash
        report["working_copy_baseline"] = {"path": str(source_path), "sha256": baseline_hash}
        report["source_revisions"] = []
        revisions = (
            (PERSISTENCE_PROBE_THICKNESS, "association_after_reopen_probe"),
            (UPDATED_THICKNESS, "restored_final"),
        )
        for index, (thickness, stage) in enumerate(revisions, start=1):
            previous_path = source_path
            previous_hash = hashlib.sha256(previous_path.read_bytes()).hexdigest()
            source_path = folder / f"working-plate-revision-{index:02d}-{thickness:g}mm.m3d"
            assert not source_path.exists(), source_path
            shutil.copy2(previous_path, source_path)
            copied_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            assert copied_hash == previous_hash, "Revision was not an identical source copy"
            working = own(documents.open_document(k, str(source_path)))
            assert Path(working["path"]).samefile(source_path), working["path"]
            parameters.set_variable(k, working["document_id"], THICKNESS_VARIABLE, value=thickness)
            record(f"{stage}_source", _model_state(k, working, thickness))
            save(working, source_path, overwrite=True)
            close(working)
            working = own(documents.open_document(k, str(source_path)))
            assert Path(working["path"]).samefile(source_path), working["path"]
            record(f"{stage}_source_reopened", _model_state(k, working, thickness))
            close(working)
            assert hashlib.sha256(previous_path.read_bytes()).hexdigest() == previous_hash
            revision_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
            protected_sources[source_path] = revision_hash
            revision = {
                "path": str(source_path),
                "thickness_mm": thickness,
                "copied_from": str(previous_path),
                "source_sha256": previous_hash,
                "copy_sha256_before_edit": copied_hash,
                "sha256_after_edit": revision_hash,
                "previous_source_unchanged": True,
            }
            report["source_revisions"].append(revision)
            report["final_source_path"] = str(source_path)
            record(f"{stage}_revision", revision)
            record(f"{stage}_views_rebound", _rebind_views(k, drawing, roles, source_path))
            record(f"{stage}_drawing", _drawing_state(k, drawing, roles, source_path, thickness))
            save(drawing, drawing_path, overwrite=True)
            close(drawing)
            drawing = own(documents.open_document(k, str(drawing_path)))
            record(
                f"{stage}_drawing_reopened",
                _drawing_state(k, drawing, roles, source_path, thickness),
            )
        report["drawing_after"] = _export_png(k, drawing, folder / "drawing-after.png")
        close(drawing)
        working = own(documents.open_document(k, str(source_path)))
        record("updated_source_reopened", _model_state(k, working, UPDATED_THICKNESS))
        close(working)
        assert hashlib.sha256(original_path.read_bytes()).hexdigest() == original_hash
        assert all(
            hashlib.sha256(path.read_bytes()).hexdigest() == digest
            for path, digest in protected_sources.items()
        ), "A saved source revision changed after validation"
        report["original_sha256"] = original_hash
        report["passed"] = True
    except Exception as exc:
        report["error"] = repr(exc)
        raise
    finally:
        if original_hash is not None:
            report["original_unchanged"] = (
                hashlib.sha256(original_path.read_bytes()).hexdigest() == original_hash
            )
        report["source_revisions_unchanged"] = {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() == digest
            for path, digest in protected_sources.items()
        }
        cleanup_errors = []
        for handle in reversed(owned):
            try:
                documents.close_document(k, handle, discard_changes=True)
            except Exception as exc:  # noqa: BLE001 - close all owned docs before raising
                cleanup_errors.append({"document": handle, "error": repr(exc)})
        if cleanup_errors:
            report["cleanup_errors"] = cleanup_errors
            report["passed"] = False
        (folder / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps({"folder": str(folder), "passed": report["passed"]}), flush=True)
        k.entities.clear()
        k.documents.clear()
        k.handles.clear()
        k.app = None
        pythoncom.CoUninitialize()
        if cleanup_errors:
            raise RuntimeError(f"Could not close {len(cleanup_errors)} owned test document(s)")


if __name__ == "__main__":
    main()
