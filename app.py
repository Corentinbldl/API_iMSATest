from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image, ImageDraw
import json
import os
import tempfile
from typing import List, Dict, Any

app = FastAPI()


@app.get("/")
def root():
    print(">>> GET / called", flush=True)
    return {"status": "ok"}


@app.get("/health")
def health():
    print(">>> GET /health called", flush=True)
    return {"status": "ok"}


@app.get("/ping")
def ping():
    print(">>> GET /ping called", flush=True)
    return {"message": "pong"}


@app.post("/echo")
async def echo():
    print(">>> POST /echo called", flush=True)
    return {"ok": True}


@app.post("/anonymize")
async def anonymize_image(
    image: UploadFile = File(...),
    zonesJson: str = Form(...)
):
    input_path = None
    output_path = None

    try:
        print("===== POST /anonymize START =====", flush=True)
        print("filename =", image.filename, flush=True)
        print("content_type =", image.content_type, flush=True)
        print("zonesJson raw =", zonesJson, flush=True)

        try:
            zones: List[Dict[str, Any]] = json.loads(zonesJson)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"zonesJson invalide: {str(e)}")

        suffix = os.path.splitext(image.filename or "input.jpg")[1]
        if not suffix:
            suffix = ".jpg"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
            input_path = tmp_in.name
            file_bytes = await image.read()
            tmp_in.write(file_bytes)

        output_path = input_path.replace(suffix, f"_anonymized{suffix}")

        print("input_path =", input_path, flush=True)
        print("output_path =", output_path, flush=True)
        print("input file size =", os.path.getsize(input_path), flush=True)
        print("zones_count =", len(zones), flush=True)

        with Image.open(input_path) as img:
            print("image format =", img.format, flush=True)
            print("image mode before =", img.mode, flush=True)

            draw = ImageDraw.Draw(img)
            image_width, image_height = img.size

            print("image_width =", image_width, flush=True)
            print("image_height =", image_height, flush=True)

            for idx, zone in enumerate(zones, start=1):
                pdf_x = float(zone["PdfX"])
                pdf_y = float(zone["PdfY"])
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
                print("pdf_x =", pdf_x, "pdf_y =", pdf_y, "pdf_w =", pdf_w, "pdf_h =", pdf_h, flush=True)
                print("page_width =", page_width, "page_height =", page_height, flush=True)
                print("scale_x =", scale_x, "scale_y =", scale_y, flush=True)
                print("rect_pixels =", x1, y1, x2, y2, flush=True)

                draw.rectangle([x1, y1, x2, y2], fill="black")

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            print("image mode after =", img.mode, flush=True)
            img.save(output_path, format="JPEG", quality=95)

        print("output exists =", os.path.exists(output_path), flush=True)
        if os.path.exists(output_path):
            print("output size =", os.path.getsize(output_path), flush=True)

        print("===== POST /anonymize END =====", flush=True)

        return FileResponse(
            path=output_path,
            media_type="image/jpeg",
            filename=f"anonymized_{image.filename or 'image.jpg'}"
        )

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
