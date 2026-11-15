"""Validate, re-encode and persist private device images."""

import base64
from io import BytesIO
from pathlib import Path
import uuid
import warnings
from flask import current_app
from PIL import Image, UnidentifiedImageError
from app.extensions import db
from app.models import MediaAsset
from app.media_storage import protect


def save_snapshot_image(image_b64, prefix="snapshot", device_id=None):
    if not image_b64:
        return None
    if not isinstance(image_b64, str) or not device_id:
        raise ValueError("Image and device identity are required")
    raw = base64.b64decode(image_b64, validate=True)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format not in ("JPEG", "PNG") or image.width * image.height > 4_000_000:
                    raise ValueError("Image must be JPEG/PNG with at most four million pixels")
                image.load()
                output = BytesIO()
                image.convert("RGB").save(output, format="JPEG", quality=85)
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Invalid image") from exc
    filename = uuid.uuid4().hex + ".jpg"
    directory = Path(current_app.config["UPLOAD_FOLDER"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(protect(output.getvalue(), filename, device_id))
    db.session.add(MediaAsset(filename=filename, device_id=device_id))
    return "/api/media/" + filename
