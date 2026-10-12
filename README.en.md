# КОМПАС-3D MCP

[Русский](README.md)

Local Windows MCP server for broad KOMPAS-3D automation: native modeling and editing,
parameters, assemblies, drawings, and documents. Blueprint and text-driven modeling
remain the primary workflows. Includes **41 tools**, two prompts, and three rich skills.
Tested with **КОМПАС-3D v25 Home**, its installed SDK, and Python 3.12.

The AI client interprets the description or drawing. This server executes native
CAD operations and returns geometry measurements, model previews, and SDK evidence.
It does not contain an OCR engine or a separate text-to-3D model.

## Setup

For the ZIP download and PowerShell installer walkthrough, see the
[Russian quick start](README.md#быстрая-установка-в-codex).

Requirements: Windows, licensed KOMPAS-3D with COM registration and SDK installed,
Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync --locked
uv run python scripts/install.py
```

Restart your MCP client to load `kompas3d` and the installed skills. Installation
adds one server entry to Codex's configuration and copies the three skills to
`$CODEX_HOME/skills` (default `~/.codex/skills`). Existing differing entries are
preserved and reported. The initial configuration is backed up before writing.
The server command uses this checkout's virtualenv, so keep the checkout in place.
For an existing installation, run `uv run python scripts/install.py --update-skills`.
This backs up changed skill files before updating them and preserves server configuration.

For other MCP clients, use this stdio configuration with your absolute path:

```json
{
  "mcpServers": {
    "kompas3d": {
      "command": "C:/path/to/Compass3DMCP/.venv/Scripts/python.exe",
      "args": ["-m", "kompas_mcp.server"]
    }
  }
}
```

Run manually with `uv run kompas3d-mcp`. The server uses stdout for MCP and stderr
for logging. No port, cloud service, or API key is required. KOMPAS launches only
when an application-dependent tool requests it. SDK archive search/read and blueprint
viewing do not need the application. Interface catalog discovery currently connects.

The SDK is autodetected under `C:/Program Files/ASCON/KOMPAS*/SDK`.
For a different installation or multiple versions, set `KOMPAS_SDK_PATH` to the
desired SDK folder in the MCP client's environment. The registered COM ProgID
chooses the application version; that registration must match the chosen SDK.

## Included tools

| Tools | Capability |
| --- | --- |
| `connect`, `create_part`, `open_model`, `attach_active_model` | Explicit document sessions |
| `blueprint_view` | PDF page/image viewing and normalized detail crops |
| `create_sketch` | Circles, arcs, polylines, construction lines, principal/offset planes |
| `extrude`, `revolve` | Native additive/subtractive solid features |
| `inspect_model` | Bounds, volume, area, mass, body count, session entities and SDK handles |
| `model_preview` | PNG of the current model view |
| `save_model`, `export_model` | Native M3D/A3D and STEP/STL/IGES export |
| `sdk_search`, `sdk_read` | Installed SDK help without browser or internet |
| `api_constants`, `api_describe`, `api_invoke` | Advanced API5/API7 discovery and COM operations |
| `api_catalog`, `api_describe_interface`, `api_cast`, `api_batch` | Discover all 1,119 installed interfaces, QueryInterface, typed arrays, checked dependent operations |
| `list_entities`, `create_feature`, `update_feature`, `set_entity_state`, `delete_feature` | Existing-model discovery and native feature lifecycle |
| `treat_edges` | Native fillets/chamfers using geometric solid-edge selection |
| `list_variables`, `set_variable`, `set_material` | Driving parameters/expressions, material and density |
| `list_documents`, `create_document`, `open_document`, `save_document`, `close_document` | Parts, assemblies, drawings, fragments, specifications, text documents |
| `insert_component`, `create_standard_views` | Linked assembly components and associative engineering drawing views |
| `draw_line`, `draw_circle`, `draw_linear_dimension`, `draw_text` | Native editable drawing objects and measured dimensions |

Two MCP prompts provide starting workflows: `model_from_blueprint` and
`model_from_description`.

All geometry uses **mm and degrees**. Extrusion `reverse=false` follows the sketch
normal for both addition and cutting, including API5's otherwise inverted cut
direction. Native sketches are editable but are not automatically constrained.

`create_feature` configures native API5 definitions, so shells, lofts, sweeps,
patterns and mirrors share a checked mechanism instead of requiring a tool per
button. API7-only functionality uses additional interfaces through `api_cast`
and ordered `api_batch` steps, including typed SAFEARRAY arguments. Native sheet-metal
plate creation/editing and sketch constraints were validated through these interfaces.
There is no arbitrary Python execution tool. See the [coverage matrix](docs/coverage.md)
for the exact boundary between live-verified workflows and documented but untested operations.

API7 model document tools return `document_id` for the API5 modeling tools.
`list_entities` finds existing/reopened geometry, not only session-created entities.
Edges/faces default to solid boundaries, excluding sketch and datum geometry.
Sketches can use `support_entity_id` for a native face or construction plane.
See [tool workflows](skills/kompas-api/references/tool-workflows.md) for checked batch syntax.

## Skills

- [`kompas-modeling`](skills/kompas-modeling/SKILL.md): text-to-model planning,
  feature recipes, identity management, geometry checks, and advanced operations.
- [`kompas-blueprints`](skills/kompas-blueprints/SKILL.md): multi-view interpretation,
  dimension provenance, Russian drawing notation, assumptions, and verification.
- [`kompas-api`](skills/kompas-api/SKILL.md): installed SDK discovery, API5/API7,
  topology selection, and automation troubleshooting.

Example requests:

> Use $kompas-modeling to create an 80 × 50 × 8 mm mounting plate with four Ø6 holes,
> each 10 mm from its adjacent edges. Save the editable model and a STEP copy.

> Use $kompas-blueprints to reconstruct this PDF drawing in КОМПАС-3D.
> Keep a dimension ledger and identify missing information before assuming it.

> Use $kompas-api to add a 2 mm fillet to the four vertical outer edges of this part.

## Verification

```powershell
uv run pytest -q
uv run ruff check src tests scripts
uv run python scripts/validate_live.py
uv run python scripts/validate_advanced.py
uv run python scripts/validate_documents.py
uv run python scripts/validate_parameters.py
uv run python scripts/validate_patterns.py
uv run python scripts/validate_sheet_metal.py
uv run python scripts/validate_constraints.py
```

Unit/protocol tests run without launching CAD. The explicitly run live acceptance
script launches KOMPAS, builds positive/reverse extrusions and cuts, checks exact
bounds and analytic volumes, creates a revolved shaft, saves/reopens native files,
exports STEP/STL/IGES, retrieves a PNG through MCP, and reads SDK help. It writes
results under `artifacts/acceptance-*` and closes only its own test documents.

The live plate checks `80*50*8 - pi*5²*8 = 31371.681469282 mm³`, one body.
The revolved cylinder checks `pi*10²*30 = 9424.777960769 mm³`.
Additional live suites verify fillet radius edits and suppression, chamfers, open
shells, lofts, linear/mirror patterns, sheet-metal thickness edits, driving variables,
sketch constraints, six native document kinds, linked assembly insertion, associative
views, native drawing objects and measured dimensions, including save/reopen persistence.
This does not establish arbitrary blueprint reconstruction or every release/license.

## Operational limits

- One dedicated STA thread owns all COM references. Calls are serialized.
  Cancellation/timeouts cannot abort a running CAD operation. Inspect before retrying.
- IDs/handles are session-scoped and can become stale if the user deletes geometry
  or closes documents. Attach/open again after a server restart.
- `open_model` can reject a native file already open in KOMPAS. Use explicit
  `attach_active_model` and check its path in that case.
- STEP import was verified as a solid. STL import may produce polygonal geometry
  with zero solid body count; it does not reconstruct a native feature history.
  IGES import depends on converter behavior and was not successful in the local test.
- Extrusion/revolution tools check material volume change. General feature tools
  check native return values and report measurements; callers must compare them
  against the intended result, especially for surfaces and auxiliary geometry.
  A failed feature may remain in the tree for inspection. Operations are not atomic.
- High-level saves refuse existing output paths unless `overwrite=true`.
  **`api_invoke` and `api_batch` provide unrestricted local COM access**, including file writes,
  deletion, and application commands. It bypasses high-level safeguards and is for
  a trusted local MCP client. Do not expose this server to untrusted remote callers.
- Preview uses the current view, not a standardized engineering projection.
  Material-dependent mass is reported from KOMPAS, not independently certified.
- Blueprint dimensions, manufacturing fits, and hidden geometry still require
  interpretation and checks; a plausible preview is not a dimensional proof.

## Implementation references

- Installed ASCON v25 `SDK/lib/*.tlb`, `SDK/Include/ldefin2d.h`, and SDK Help archive.
- [ASCON API5 document interface](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/ksdocument3d.html)
- [ASCON cut direction semantics](https://help.ascon.ru/KOMPAS_SDK/25/ru-RU/kscutextrusiondefinition_directiontype.html)
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

## Questions, suggestions and bugs

For any questions, ideas or bug reports, please open an [issue](https://github.com/hymaxo/kompas3d-mcp/issues/new) in this repository. For bugs, include your KOMPAS-3D version, the MCP client you use, reproduction steps and the error message.

## License

This project is licensed under the [MIT License](LICENSE). KOMPAS-3D and its SDK
are not included; their use is governed by ASCON's terms.
