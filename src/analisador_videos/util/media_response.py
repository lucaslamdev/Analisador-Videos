from pathlib import Path

from fastapi.responses import FileResponse


def video_file_response(
    path: Path,
    *,
    download: bool = False,
    filename: str | None = None,
) -> FileResponse:
    name = filename or path.name
    disposition = "attachment" if download else "inline"
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=name,
        headers={"Content-Disposition": f'{disposition}; filename="{name}"'},
    )
