from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw
import json
import os
import tempfile
from typing import List, Dict, Any

app = FastAPI()


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/anonymize")
async def anonymize_image(request: Request):
    try:
        form = await request.form()

        zones_json_raw = form.get("zonesJson")
        if not zones_json_raw:
            raise HTTPException(status_code=400, detail="zonesJson manquant")

        zones: List[Dict[str, Any]] = json.loads(zones_json_raw)

        uploaded_file = None
        for _, value in form.multi_items():
            if isinstance(value, UploadFile):
                uploaded_file = value
                break

        if uploaded_file is None:
            raise HTTPException(status_code=400, detail="Aucun fichier image reçu")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Requête invalide: {str(e)}")

    suffix = os.path.splitext(uploaded_file.filename or "input.jpg")[1]
    if not suffix:
        suffix = ".jpg"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
        input_path = tmp_in.name
        tmp_in.write(await uploaded_file.read())

    output_path = input_path.replace(suffix, f"_anonymized{suffix}")

    try:
        with Image.open(input_path) as img:
            draw = ImageDraw.Draw(img)
            image_width, image_height = img.size

            print("===== IMAGE DEBUG =====")
            print("input_path =", input_path)
            print("output_path =", output_path)
            print("image_width =", image_width)
            print("image_height =", image_height)
            print("zones_count =", len(zones))

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

                print("===== ZONE DEBUG =====")
                print("zone_index =", idx)
                print("pdf_x =", pdf_x, "pdf_y =", pdf_y, "pdf_w =", pdf_w, "pdf_h =", pdf_h)
                print("page_width =", page_width, "page_height =", page_height)
                print("image_width =", image_width, "image_height =", image_height)
                print("scale_x =", scale_x, "scale_y =", scale_y)
                print("rect_pixels =", x1, y1, x2, y2)

                draw.rectangle([x1, y1, x2, y2], fill="black")

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img.save(output_path, format="JPEG")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur traitement image: {str(e)}")

    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

    return FileResponse(
        output_path,
        media_type="image/jpeg",
        filename=f"anonymized_{uploaded_file.filename or 'image.jpg'}"
    )
