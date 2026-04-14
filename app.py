from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile as StarletteUploadFile
from PIL import Image, ImageDraw
import json
import os
import tempfile
import uuid
from typing import List, Dict, Any

app = FastAPI()

PUBLIC_DIR = "public"
os.makedirs(PUBLIC_DIR, exist_ok=True)

app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")


@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ping")
def ping():
    return {"message": "pong"}


@app.post("/echo")
async def echo():
    return {"ok": True}


@app.post("/anonymize")
async def anonymize_image(request: Request):
    input_path = None

    try:
        print("===== POST /anonymize START =====", flush=True)

        form = await request.form()
        print("form keys =", list(form.keys()), flush=True)

        zones_json_raw = form.get("zonesJson")
        uploaded_file = None
        uploaded_key = None

        for key, value in form.multi_items():
            print(f"FORM ITEM -> key={key} | type={type(value)}", flush=True)
            if isinstance(value, StarletteUploadFile):
                uploaded_file = value
                uploaded_key = key
                break

        print("uploaded_key =", uploaded_key, flush=True)

        if not zones_json_raw:
            raise HTTPException(status_code=400, detail="zonesJson manquant")

        try:
            zones: List[Dict[str, Any]] = json.loads(zones_json_raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"zonesJson invalide: {str(e)}")

        if uploaded_file is None:
            raise HTTPException(status_code=400, detail="Aucun fichier image reçu")

        print("filename =", uploaded_file.filename, flush=True)
        print("content_type =", uploaded_file.content_type, flush=True)
        print("zonesJson raw =", zones_json_raw, flush=True)

        suffix = os.path.splitext(uploaded_file.filename or "input.jpg")[1]
        if not suffix:
            suffix = ".jpg"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
            input_path = tmp_in.name
            file_bytes = await uploaded_file.read()
            tmp_in.write(file_bytes)

        unique_name = f"anonymized_{uuid.uuid4().hex}.jpg"
        output_path = os.path.join(PUBLIC_DIR, unique_name)

        print("input_path =", input_path, flush=True)
        print("output_path =", output_path, flush=True)
        print("input file size =", os.path.getsize(input_path), flush=True)
        print("zones_count =", len(zones), flush=True)

        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            draw = ImageDraw.Draw(img)
            image_width, image_height = img.size

            print("image_width =", image_width, flush=True)
            print("image_height =", image_height, flush=True)

            for idx, zone in enumerate(zones, start=1):
                # Inversion uniquement de la position X/Y
                pdf_x = float(zone["PdfY"])
                pdf_y = float(zone["PdfX"])
                pdf_w = float(zone["PdfWidth"])
                pdf_h = float(zone["PdfHeight"])

                page_width = float(zone["PageWidth"])
                page_height = float(zone["PageHeight"])

                scale_x = image_width / page_width
                scale_y = image_height / page_height

                x1 = round(pdf_x * scale_x)
                y1 = round(pdf_y * scale_y)
                x2 = round((pdf_x + pdf_w) * scale_x)
                y2 = round((pdf_y + pdf_h) * scale_y)

                pad_x = 2
                pad_y = 3

                x1 = max(0, x1 - pad_x)
                y1 = max(0, y1 - pad_y)
                x2 = min(image_width, x2 + pad_x)
                y2 = min(image_height, y2 + pad_y)

                if x2 <= x1:
                    x2 = x1 + 1
                if y2 <= y1:
                    y2 = y1 + 1

                print("===== ZONE DEBUG =====", flush=True)
                print("zone_index =", idx, flush=True)
                print("raw zone =", zone, flush=True)
                print("mapped pdf_x =", pdf_x, flush=True)
                print("mapped pdf_y =", pdf_y, flush=True)
                print("pdf_w =", pdf_w, flush=True)
                print("pdf_h =", pdf_h, flush=True)
                print("rect_pixels =", x1, y1, x2, y2, flush=True)

                draw.rectangle([x1, y1, x2, y2], fill="white")

            img.save(output_path, format="JPEG", quality=95)

        file_url = str(request.base_url).rstrip("/") + f"/public/{unique_name}"

        print("file_url =", file_url, flush=True)
        print("===== POST /anonymize END =====", flush=True)

        return {
            "success": True,
            "message": "Image anonymisée avec succès",
            "file_url": file_url,
            "filename": unique_name
        }

    except HTTPException as e:
        print("===== HTTP EXCEPTION =====", flush=True)
        print("status_code =", e.status_code, flush=True)
        print("detail =", e.detail, flush=True)
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

    except Exception as e:
        print("===== UNHANDLED EXCEPTION =====", flush=True)
        print(str(e), flush=True)
        return JSONResponse(
            status_code=500,
            content={"detail": f"Erreur traitement image: {str(e)}"}
        )

    finally:
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception:
                pass
