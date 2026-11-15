"""Explicit bounded media retention; preview by default, no background deletion."""
from datetime import datetime, timedelta
from pathlib import Path
import re

from flask import current_app

from app import db
from app.models import MediaAsset


def prune_media(older_than_days, limit=1000, apply=False):
    if older_than_days < 1 or not 1 <= limit <= 10000:
        raise ValueError('Retention must be positive and limit between 1 and 10000')
    cutoff = datetime.now() - timedelta(days=older_than_days)
    assets = MediaAsset.query.filter(MediaAsset.created_at < cutoff).order_by(
        MediaAsset.created_at, MediaAsset.filename).limit(limit).all()
    if not apply:
        return len(assets)
    root = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    validated = []
    for asset in assets:
        if not re.fullmatch(r'[a-f0-9]{32}\.jpg', asset.filename):
            raise ValueError('Unexpected media filename; manual review required')
        path = root / asset.filename
        if path.is_symlink() or path.resolve().parent != root:
            raise ValueError('Media path escapes configured storage')
        validated.append((asset, path))
    # Reject an unsafe batch before deleting any otherwise valid files.
    for asset, path in validated:
        path.unlink(missing_ok=True)
        db.session.delete(asset)
    db.session.commit()
    return len(assets)
