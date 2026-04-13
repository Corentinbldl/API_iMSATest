from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw
import json
import os
import tempfile
from typing import List, Dict, Any

app = FastAPI()


@app.post("/anonymize")
async def anonymize_image(
    image: UploadFile = File(...),
    zonesJson: str = Form(...)
):
    try:
        zones: List[Dict[str, Any]] = json.loads(zonesJson)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"zonesJson invalide: {str(e)}")

    suffix = os.path.splitext(image.filename or "input.jpg")[1]
    if not suffix:
        suffix = ".jpg"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
        input_path = tmp_in.name
        tmp_in.write(await image.read())

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
                # TEST TEMPORAIRE : inversion X/Y
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

                print("===== ZONE DEBUG =====")
                print("zone_index =", idx)
                print("RAW PdfX =", zone["PdfX"], "RAW PdfY =", zone["PdfY"])
                print("USED pdf_x =", pdf_x, "USED pdf_y =", pdf_y)
                print("pdf_w =", pdf_w, "pdf_h =", pdf_h)
                print("page_width =", page_width, "page_height =", page_height)
                print("image_width =", image_width, "image_height =", image_height)
                print("scale_x =", scale_x, "scale_y =", scale_y)
                print("rect_pixels =", x1, y1, x2, y2)

                draw.rectangle([x1, y1, x2, y2], outline="red", width=3)

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
        filename=f"anonymized_{image.filename or 'image.jpg'}"
    )