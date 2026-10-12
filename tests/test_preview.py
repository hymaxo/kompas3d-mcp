import asyncio
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from kompas_mcp import server


@pytest.mark.parametrize("crop", [None, (0.5, 0, 1, 1), (0.8, 0, 0.2, 1)])
def test_model_preview_crops_original_pixels_and_cleans_up(monkeypatch, crop):
    paths = []

    def preview(document_id, path):
        assert document_id == "part"
        paths.append(Path(path))
        image = Image.new("RGB", (4000, 200), "red")
        image.paste("blue", (2000, 0, 4000, 200))
        image.save(path)

    async def call(operation):
        return operation(SimpleNamespace(preview=preview))

    monkeypatch.setattr(server.worker, "call", call)
    if crop == (0.8, 0, 0.2, 1):
        with pytest.raises(ValueError, match="crop must be ordered"):
            asyncio.run(server.model_preview("part", crop=crop))
    else:
        result = asyncio.run(server.model_preview("part", crop=crop))
        with Image.open(io.BytesIO(result.data)) as image:
            if crop:
                assert image.size == (2000, 200)
                assert image.getpixel((0, 0)) == (0, 0, 255)
            else:
                assert image.size == (2400, 120)
    assert paths and all(not path.exists() for path in paths)
