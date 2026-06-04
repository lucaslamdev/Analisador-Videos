import zipfile
from pathlib import Path


def zip_files(paths: list[Path], out_zip: Path) -> Path:
    entries = [(p, p.name) for p in paths if p.is_file()]
    return zip_named(entries, out_zip)


def zip_named(entries: list[tuple[Path, str]], out_zip: Path) -> Path:
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in entries:
            if path.is_file():
                zf.write(path, arcname=arcname.replace("\\", "/"))
    return out_zip
