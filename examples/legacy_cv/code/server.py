from typing import List, Dict

import io
import os
import sys
import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

# Ensure package root is importable when executed as a script: `python app/server.py`
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    # package execution (recommended): `python -m uvicorn app.server:app ...`
    from .face_detector import DnnFaceDetector, crop_and_save_faces, compute_embeddings
except Exception:
    try:
        # script execution with sys.path adjusted
        from app.face_detector import DnnFaceDetector, crop_and_save_faces, compute_embeddings
    except Exception:
        # final fallback if current dir is app/
        from face_detector import DnnFaceDetector, crop_and_save_faces, compute_embeddings


app = FastAPI(title="Face Detection Service (OpenCV DNN)", version="1.0.0")
detector = DnnFaceDetector(conf_threshold=0.5)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/detect")
async def detect_endpoint(
    file: UploadFile = File(...),
    conf_threshold: float = 0.5,
    save_crops: bool = False,
    output_dir: str = "face_crops",
    margin_ratio: float = 0.2,
    return_embeddings: bool = False,
) -> JSONResponse:
    if file.content_type not in {"image/jpeg", "image/png", "image/bmp", "image/webp"}:
        raise HTTPException(status_code=400, detail="Unsupported image type")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    image_array = np.frombuffer(data, dtype=np.uint8)
    image_bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise HTTPException(status_code=400, detail="Failed to decode image")

    # allow dynamic threshold per request
    detector.conf_threshold = float(conf_threshold)
    faces = detector.detect(image_bgr)

    saved = []
    if save_crops and len(faces) > 0:
        # prefix: yyyyMMdd_HHMMSS
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        # use provided output_dir, resolved inside crop function
        saved = crop_and_save_faces(
            image_bgr,
            faces,
            output_dir=output_dir,
            filename_prefix=f"faces_{ts}",
            margin_ratio=margin_ratio,
        )

    embeddings = []
    if return_embeddings and len(faces) > 0:
        embeddings = compute_embeddings(image_bgr, faces, margin_ratio=margin_ratio)
        if save_crops and embeddings:
            for idx, emb in enumerate(embeddings):
                if idx < len(saved):
                    saved[idx]["embedding"] = emb.get("embedding")

    h, w = image_bgr.shape[:2]
    return JSONResponse(
        content={
            "image": {"width": w, "height": h},
            "num_faces": len(faces),
            "faces": faces,
            "saved": saved,
            "embeddings": embeddings,
        }
    )



if __name__ == "__main__":
    # Allow running: `python app/server.py`
    import uvicorn

    uvicorn.run("app.server:app", host="0.0.0.0", port=8000, reload=False)

