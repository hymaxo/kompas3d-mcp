"""Wrapper contract tests; native geometry is verified separately in KOMPAS."""

import asyncio
import sys
from types import SimpleNamespace

import pytest

from kompas_mcp import advanced_tools, documents
from kompas_mcp.backend import Kompas


class View:
    def __init__(self, reference, number, events, objects=4, valid=True):
        self._oleobj_ = object()
        self.Reference = reference
        self.Number = number
        self.ObjectCount = 0
        self.Valid = valid
        self._draft = True
        self._objects = objects
        self.events = events
        self.update_result = True
        self.rebuild_result = True

    @property
    def UseOcclusion(self):
        return self._draft

    @UseOcclusion.setter
    def UseOcclusion(self, value):
        self.events.append((self.Reference, "mode", value))
        self._draft = value

    def Update(self):
        self.events.append((self.Reference, "update"))
        return self.update_result

    def Rebuild(self):
        self.events.append((self.Reference, "rebuild"))
        self.ObjectCount = self._objects
        return self.rebuild_result


@pytest.fixture
def drawing_case(monkeypatch, tmp_path):
    events = []
    existing = [View(100, 0, events), View(200, 7, events)]
    existing[1].ObjectCount = 12
    created = [View(301, 1, events), View(302, 2, events), View(303, 3, events)]

    class Views:
        _oleobj_ = object()
        add_result = True

        def __init__(self):
            self.items = list(existing)

        @property
        def Count(self):
            return len(self.items)

        def View(self, index):
            return self.items[index]

        def AddStandartViews(self, *args):
            events.append(("add",))
            # COM may reorder the collection; an append-only index slice would
            # modify existing views and miss newly created ones here.
            self.items = [*created[:1], existing[1], *created[1:], existing[0]]
            return self.add_result

    views = Views()
    drawing = SimpleNamespace(ViewsAndLayersManager=SimpleNamespace(Views=views))
    doc = SimpleNamespace(DocumentType=1, ReadOnly=False)
    backend = Kompas()
    backend.constants = {"ksDocumentDrawing": 1, "ksPtFront": 1, "ksPtUp": 2, "ksPtLeft": 3}
    monkeypatch.setattr(documents, "_document", lambda k, handle: doc)

    def cast(k, obj, interface):
        if interface == "IKompasDocument2D":
            assert obj is doc
            return drawing
        assert interface == "IAssociationView"
        assert obj in created
        return obj

    monkeypatch.setattr(documents, "_cast", cast)
    monkeypatch.setitem(sys.modules, "pythoncom", SimpleNamespace(VT_ARRAY=8192, VT_I4=3))
    monkeypatch.setitem(
        sys.modules, "win32com.client", SimpleNamespace(VARIANT=lambda kind, value: value)
    )
    model = tmp_path / "test.m3d"
    model.write_bytes(b"native-model-placeholder")

    def run(**kwargs):
        return documents.create_standard_views(
            backend, "drawing", str(model), ["front", "top", "left"], **kwargs
        )

    return SimpleNamespace(
        run=run, backend=backend, events=events, existing=existing, created=created, views=views
    )


@pytest.mark.parametrize("draft_projection", [False, True])
def test_new_views_only_use_requested_mode_and_collection_order(drawing_case, draft_projection):
    case = drawing_case
    # The default path must explicitly reset inherited draft mode.
    kwargs = {"draft_projection": True} if draft_projection else {}
    result = case.run(**kwargs)
    assert case.events == [("add",)] + [
        event
        for view in case.created
        for event in (
            (view.Reference, "mode", draft_projection),
            (view.Reference, "update"),
            (view.Reference, "rebuild"),
        )
    ]
    assert case.existing[1].UseOcclusion is True
    assert case.existing[1].ObjectCount == 12
    assert result["count_before"] == 2
    assert result["count_after"] == 5
    assert result["created_count"] == 3
    assert case.backend.handles[result["views"]["handle"]] is case.views
    for view, metadata in zip(case.created, result["created_views"], strict=True):
        assert metadata["number"] == view.Number
        assert case.backend.handles[metadata["handle"]] is view
        assert metadata["object_count"] == 4
        assert metadata["valid"] is True
        assert metadata["draft_projection"] is draft_projection


def test_empty_views_are_failure_despite_true_com_results(drawing_case):
    case = drawing_case
    case.created[1]._objects = 0
    with pytest.raises(RuntimeError, match="invalid, empty") as error:
        case.run()
    message = str(error.value)
    assert "'number': 2, 'object_count': 0" in message
    assert "partially created views remain" in message
    assert case.views.Count == 5
    assert sum(event == ("add",) for event in case.events) == 1


def test_invalid_views_are_failure_even_with_objects(drawing_case):
    drawing_case.created[0].Valid = False
    with pytest.raises(RuntimeError, match="invalid, empty"):
        drawing_case.run()


@pytest.mark.parametrize("created_count", [2, 4])
def test_count_mismatch_reports_partial_views_without_modifying_them(drawing_case, created_count):
    case = drawing_case
    if created_count == 2:
        case.created.pop()
    else:
        case.created.append(View(304, 4, case.events))
    with pytest.raises(RuntimeError, match=f"Expected 3 new views, found {created_count}") as error:
        case.run()
    assert "Created views:" in str(error.value)
    assert "object_count" in str(error.value)
    assert case.events == [("add",)]
    assert case.views.Count == len(case.existing) + created_count


@pytest.mark.parametrize("operation", ["add", "update", "rebuild"])
def test_rejected_mutation_reports_partial_views_and_does_not_retry(drawing_case, operation):
    case = drawing_case
    if operation == "add":
        case.views.add_result = False
    else:
        setattr(case.created[0], f"{operation}_result", False)
    with pytest.raises(RuntimeError, match="KOMPAS rejected") as error:
        case.run()
    assert "'number': 1" in str(error.value)
    assert "partially created views remain" in str(error.value)
    assert case.views.Count == 5
    assert sum(event == ("add",) for event in case.events) == 1
    assert not any(event[0] == 302 for event in case.events)


def test_mcp_tool_passes_projection_choice_to_worker(monkeypatch):
    registered = {}

    class MCP:
        def tool(self):
            def register(function):
                registered[function.__name__] = function
                return function

            return register

    class Worker:
        async def call(self, function):
            return function("backend")

    calls = []
    monkeypatch.setattr(documents, "create_standard_views", lambda *args: calls.append(args))
    advanced_tools.register(MCP(), Worker())
    tool = registered["create_standard_views"]
    asyncio.run(tool("drawing", "model.m3d", ["front"]))
    asyncio.run(tool("drawing", "model.m3d", ["front"], draft_projection=True))
    assert calls[0][-1] is False
    assert calls[1][-1] is True
