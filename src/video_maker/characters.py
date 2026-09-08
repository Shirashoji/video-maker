import uuid
from pathlib import Path

from psd_tools import PSDImage

from .media import inside


def layers(root: Path, path: str):
    psd = PSDImage.open(inside(root, path))
    result = []

    def walk(group, prefix=""):
        for i, layer in enumerate(group):
            key = f"{prefix}/{i}"
            result.append({"path": key, "name": layer.name, "visible": layer.visible,
                           "effective_visible": layer.is_visible(), "group": layer.is_group()})
            if layer.is_group():
                walk(layer, key)
    walk(psd)
    return result


def export(root: Path, path: str, visibility: dict[str, bool]):
    """Explicit layer-index overrides; retain all unspecified layer states."""
    psd = PSDImage.open(inside(root, path))
    for key, visible in visibility.items():
        layer = psd
        try:
            for index in key.strip("/").split("/"):
                i = int(index)
                if i < 0:
                    raise ValueError("negative layer index")
                layer = layer[i]
            layer.visible = visible
        except (ValueError, IndexError, TypeError) as e:
            raise ValueError(f"Unknown PSD layer path: {key}") from e
    output = root / "assets" / "characters" / f"{uuid.uuid4().hex}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    psd.composite(ignore_preview=True).save(output)
    return {"image": str(output), "visibility": visibility, "source": path}
