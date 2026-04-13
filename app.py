from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.datastructures import UploadFile as StarletteUploadFile
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
    input_path = None
    output_path = None

    try:
        form = await request.form()

        print("===== REQUEST DEBUG START =====")
        print("method =", request.method)
        print("url =", str(request.url))
        print("headers =", dict(request.headers))
        print("form keys =", list(form.keys()))

        zones_json_raw = None
        uploaded_file = None

        for key, value in form.multi_items():
            print("FORM ITEM -> key =", key, "| type =", str(type(value)))

            if key == "zonesJson":
                zones_json_raw = value

            # très important : ne pas dépendre du nom du champ
            if isinstance(value, StarletteUploadFile):
                uploaded_file = value
                print("UPLOAD FILE DETECTED")
                print("upload key =", key)
                print("filename =", value.filename)
                print("content_type =", value.content_type)

        # fallback: parfois UiPath peut envoyer zonesJson ailleurs
        if not zones_json_raw:
            zones_json_raw = request.query_params.get("zonesJson")
            if zones_json_raw:
                print("zonesJson trouvé dans query params")

        if not zones_json_raw:
            raise HTTPException(status_code=400, detail="zonesJson manquant")

        try:
            zones: List[Dict[str, Any]] = json.loads(zones_json_raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"zonesJson invalide: {str(e)}")

        if uploaded_file is None:
            raise HTTPException(
                status_code=400,
                detail="Aucun fichier image reçu. Vérifie la section Local files de UiPath."
            )

        suffix = os.path.splitext(uploaded_file.filename or "input.jpg")[1]
        if not suffix:
            suffix = ".jpg"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
            input_path = tmp_in.name
            file_bytes = await uploaded_file.read()
            tmp_in.write(file_bytes)

        output_path = input_path.replace(suffix, f"_anonymized{suffix}")

        print("===== IMAGE DEBUG =====")
        print("input_path =", input_path)
        print("output_path =", output_path)
        print("input file size =", os.path.getsize(input_path))
        print("zones_count =", len(zones))

        with Image.open(input_path) as img:
            print("image format =", img.format)
            print("image mode before =", img.mode)

            draw = ImageDraw.Draw(img)
            image_width, image_height = img.size

            print("image_width =", image_width)
            print("image_height =", image_height)

            for idx, zone in enumerate(zones, start=1):
                pdf_x = float(zone["PdfX"])
                pdf_y = float(zone["PdfY"])
                pdf_w = float(zone["PdfWidth"])
                pdf_h = float(zone["PdfHeight"])
                page_width = float(zone["PageWidth"])
                page_height = float(zone["PageHeight"])

                scale_x = image_width / page_width
                scale_y = image_height / page_height

                # Coordonnées IXP : x/y semblent déjà correspondre à l'image
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
                print("scale_x =", scale_x, "scale_y =", scale_y)
                print("rect_pixels =", x1, y1, x2, y2)

                # pour debug visuel
                draw.rectangle([x1, y1, x2, y2], fill="black")

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            print("image mode after =", img.mode)

            img.save(output_path, format="JPEG")

        print("output exists =", os.path.exists(output_path))
        if os.path.exists(output_path):
            print("output size =", os.path.getsize(output_path))

        print("===== REQUEST DEBUG END =====")

        return FileResponse(
            output_path,
            media_type="image/jpeg",
            filename=f"anonymized_{uploaded_file.filename or 'image.jpg'}"
        )

    except HTTPException as e:
        print("===== HTTP EXCEPTION =====")
        print("status_code =", e.status_code)
        print("detail =", e.detail)
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

    except Exception as e:
        print("===== UNHANDLED EXCEPTION =====")
        print(str(e))
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
