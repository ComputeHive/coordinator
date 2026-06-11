from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def extract_zip_file(zip_path: Path) -> Path:
    if not zip_path.is_file():
        raise FileNotFoundError(f"Zip file not found: {zip_path}")
    parent_dir = zip_path.parent
    with ZipFile(zip_path, 'r') as zf:
        zf.extractall(parent_dir)
    zip_path.unlink()
    return parent_dir


def zip_directory(parent_dir: Path, zip_filename: str) -> Path:
    source = parent_dir.resolve()
    if not source.is_dir():
        raise ValueError(f"Directory {source} does not exist")
    output_zip = source / f"{zip_filename}.zip"
    with ZipFile(output_zip, "w", ZIP_DEFLATED) as zf:
        for file_path in source.rglob('*'):
            if file_path.suffix.lower() == ".zip":
                continue
            arcname = file_path.relative_to(source)
            zf.write(file_path, arcname)
    return output_zip
