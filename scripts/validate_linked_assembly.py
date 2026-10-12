"""Live linked-source acceptance using only synthetic files and owned documents.

Run inside the interactive Windows session that owns KOMPAS. This test deliberately
keeps the assembly open while its source part changes, then verifies both refresh
and native persistence. It does not establish arbitrary assembly/mate coverage.
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
DENSITY_G_CM3 = 7.85
THICKNESS_VARIABLE = "plate_thickness"


def _measure(k, document_id, thickness):
    result = k.measure(document_id)
    volume = WIDTH * HEIGHT * thickness
    mass = volume * DENSITY_G_CM3 / 1_000_000
    assert math.isclose(result["volume_mm3"], volume, rel_tol=1e-8, abs_tol=1e-5), result
    assert math.isclose(result["mass_kg"], mass, rel_tol=1e-7, abs_tol=1e-9), result
    return result


def _component_state(k, assembly, expected_source):
    # Installed v25 SDK: iparts7_part.html and ipart7_filename.html. Read the
    # actual native component; insert_component()['source'] only echoes input.
    model = documents._cast(k, k.handles[assembly["document"]["handle"]], "IKompasDocument3D")
    parts = model.TopPart.Parts
    assert parts.Count == 1, f"Expected one linked component, got {parts.Count}"
    component = require(parts.Part(0), "get linked component")
    source = Path(component.FileName)
    if not source.is_absolute():
        source = expected_source.parent / source
    state = {
        "component_count": parts.Count,
        "name": component.Name,
        "source_file": str(component.FileName),
        "source_resolved": str(source.resolve()),
        "valid": bool(component.Valid),
        "local": bool(component.IsLocal),
        # NeedRebuild controls whether property updates rebuild automatically;
        # it is not a dirty/error status. See ipart7_needrebuild.html and the
        # equivalent API5 policy documented in kspart_needrebuild.html.
        "rebuild_on_property_change": bool(component.NeedRebuild),
    }
    assert state["valid"] and not state["local"], state
    assert source.is_file() and source.samefile(expected_source), state
    return state


def main():
    import pythoncom

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
    k = Kompas()
    folder = (
        Path(__file__).resolve().parents[1] / "artifacts" / f"linked-assembly-{uuid4().hex[:8]}"
    )
    folder.mkdir(parents=True)
    original_path = folder / "original-plate.m3d"
    working_path = folder / "working-plate.m3d"
    assembly_path = folder / "linked-plate.a3d"
    original_hash = None
    report = {"passed": False, "folder": str(folder), "steps": []}
    owned = []

    def own(document):
        owned.append(document["document"]["handle"])
        return document

    def close(document):
        handle = document["document"]["handle"]
        # Every caller explicitly saves intended mutations before closing. An
        # auto-refresh on opening the original must never write it back to disk.
        documents.close_document(k, handle, discard_changes=True)
        owned.remove(handle)

    def save(document, path, overwrite=False):
        return documents.save_document(
            k, document["document"]["handle"], str(path), overwrite=overwrite
        )

    def record(stage, document, thickness, source=None):
        entry = {
            "stage": stage,
            "measurements": _measure(k, document["document_id"], thickness),
        }
        if source is not None:
            entry["link"] = _component_state(k, document, source)
        report["steps"].append(entry)
        print(stage, json.dumps(entry, ensure_ascii=True), flush=True)
        return entry

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
        candidates = [
            variable
            for variable in variables
            if math.isclose(variable["value"], INITIAL_THICKNESS, rel_tol=0, abs_tol=1e-9)
        ]
        # Only this fresh extrusion is searched. Ambiguity must fail; never select
        # an arbitrary similarly valued parameter in a user's existing model.
        assert len(candidates) == 1, candidates
        parameters.set_variable(
            k, document_id, THICKNESS_VARIABLE, value=INITIAL_THICKNESS, create=True
        )
        parameters.set_variable(
            k,
            document_id,
            candidates[0]["name"],
            expression=THICKNESS_VARIABLE,
            feature_id=feature["feature_id"],
        )
        parameters.set_material(k, document_id, "Synthetic acceptance material", DENSITY_G_CM3)
        record("original_plate", plate, INITIAL_THICKNESS)
        save(plate, original_path)
        close(plate)
        original_hash = hashlib.sha256(original_path.read_bytes()).hexdigest()
        shutil.copy2(original_path, working_path)

        working = own(documents.open_document(k, str(working_path)))
        record("working_copy_reopened", working, INITIAL_THICKNESS)
        close(working)

        assembly = own(documents.create_document(k, "assembly"))
        documents.insert_component(
            k, assembly["document"]["handle"], str(working_path), linked=True
        )
        require(k.document(assembly["document_id"]).RebuildDocument(), "rebuild new assembly")
        record("assembly_created", assembly, INITIAL_THICKNESS, working_path)
        save(assembly, assembly_path)
        close(assembly)

        assembly = own(documents.open_document(k, str(assembly_path)))
        record("assembly_reopened", assembly, INITIAL_THICKNESS, working_path)
        working = own(documents.open_document(k, str(working_path)))
        result = parameters.set_variable(
            k, working["document_id"], THICKNESS_VARIABLE, value=UPDATED_THICKNESS
        )
        assert math.isclose(result["value"], UPDATED_THICKNESS), result
        record("working_copy_edited", working, UPDATED_THICKNESS)
        save(working, working_path, overwrite=True)
        close(working)

        # This is the existing verified API5 document rebuild route. The updated
        # measured volume, rather than its BOOL, establishes external-link refresh.
        require(k.document(assembly["document_id"]).RebuildDocument(), "rebuild linked assembly")
        record("assembly_updated", assembly, UPDATED_THICKNESS, working_path)
        save(assembly, assembly_path, overwrite=True)
        close(assembly)

        assembly = own(documents.open_document(k, str(assembly_path)))
        record("updated_assembly_reopened", assembly, UPDATED_THICKNESS, working_path)
        close(assembly)
        working = own(documents.open_document(k, str(working_path)))
        record("updated_source_reopened", working, UPDATED_THICKNESS)
        values = parameters.list_variables(k, working["document_id"])["variables"]
        restored = [v for v in values if v["name"] == THICKNESS_VARIABLE]
        assert len(restored) == 1 and math.isclose(restored[0]["value"], UPDATED_THICKNESS)
        close(working)
        assert hashlib.sha256(original_path.read_bytes()).hexdigest() == original_hash
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
        # Release the retained native handles in this same STA.
        k.entities.clear()
        k.documents.clear()
        k.handles.clear()
        k.app = None
        pythoncom.CoUninitialize()
        if cleanup_errors:
            raise RuntimeError(f"Could not close {len(cleanup_errors)} owned test document(s)")


if __name__ == "__main__":
    main()
