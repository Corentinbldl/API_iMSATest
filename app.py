from fastapi import FastAPI, UploadFile, HTTPException, Request
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
    input_path = None
    output_path = None

    try:
        form = await request.form()

        print("===== FORM DEBUG =====")
        print("form keys =", list(form.keys()))

        zones_json_raw = form.get("zonesJson")
        print("zonesJson présent =", zones_json_raw is not None)
        if zones_json_raw:
            print("zonesJson preview =", str(zones_json_raw)[:500])

        if not zones_json_raw:
            raise HTTPException(status_code=400, detail="zonesJson manquant")

        try:
            zones: List[Dict[str, Any]] = json.loads(zones_json_raw)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"zonesJson invalide: {str(e)}")

        print("zones count =", len(zones))

        uploaded_file = None
        for key, value in form.multi_items():
            print("form item key =", key, "type =", type(value))
            if isinstance(value, UploadFile):
                uploaded_file = value
                print("uploaded file found on key =", key)
                print("uploaded file name =", uploaded_file.filename)
                break

        if uploaded_file is None:
            raise HTTPException(status_code=400, detail="Aucun fichier image reçu")

        suffix = os.path.splitext(uploaded_file.filename or "input.jpg")[1]
        if not suffix:
            suffix = ".jpg"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
            input_path = tmp_in.name
            file_bytes = await uploaded_file.read()
            tmp_in.write(file_bytes)

        output_path = input_path.replace(suffix, f"_anonymized{suffix}")

        print("===== FILE DEBUG =====")
        print("input_path =", input_path)
        print("output_path =", output_path)
        print("uploaded bytes =", len(file_bytes))

        with Image.open(input_path) as img:
            print("image format =", img.format)
            print("image mode =", img.mode)

            draw = ImageDraw.Draw(img)
            image_width, image_height = img.size

            print("===== IMAGE DEBUG =====")
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

                # Hypothèse A : coordonnées PDF mesurées depuis le haut
                x1_a = round(pdf_x * scale_x)
                y1_a = round(pdf_y * scale_y)
                x2_a = round((pdf_x + pdf_w) * scale_x)
                y2_a = round((pdf_y + pdf_h) * scale_y)

                # Hypothèse B : coordonnées PDF mesurées depuis le bas
                x1_b = round(pdf_x * scale_x)
                x2_b = round((pdf_x + pdf_w) * scale_x)
                y1_b = round((page_height - (pdf_y + pdf_h)) * scale_y)
                y2_b = round((page_height - pdf_y) * scale_y)

                pad_x = 2
                pad_y = 3

                def clamp_rect(x1, y1, x2, y2):
                    x1 = max(0, x1 - pad_x)
                    y1 = max(0, y1 - pad_y)
                    x2 = min(image_width, x2 + pad_x)
                    y2 = min(image_height, y2 + pad_y)

                    if x2 <= x1:
                        x2 = x1 + 1
                    if y2 <= y1:
                        y2 = y1 + 1

                    return x1, y1, x2, y2

                x1_a, y1_a, x2_a, y2_a = clamp_rect(x1_a, y1_a, x2_a, y2_a)
                x1_b, y1_b, x2_b, y2_b = clamp_rect(x1_b, y1_b, x2_b, y2_b)

                print("===== ZONE DEBUG =====")
                print("zone_index =", idx)
                print("pdf_x =", pdf_x, "pdf_y =", pdf_y, "pdf_w =", pdf_w, "pdf_h =", pdf_h)
                print("page_width =", page_width, "page_height =", page_height)
                print("image_width =", image_width, "image_height =", image_height)
                print("scale_x =", scale_x, "scale_y =", scale_y)
                print("rect A (top-origin) =", x1_a, y1_a, x2_a, y2_a)
                print("rect B (bottom-origin) =", x1_b, y1_b, x2_b, y2_b)

                # Pour debug visuel :
                # - rouge = hypothèse A
                # - vert = hypothèse B
                draw.rectangle([x1_a, y1_a, x2_a, y2_a], outline="red", width=2)
                draw.rectangle([x1_b, y1_b, x2_b, y2_b], outline="lime", width=2)

                # Quand tu auras identifié la bonne hypothèse,
                # remplace les 2 lignes au-dessus par UNE seule ligne noire.

            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img.save(output_path, format="JPEG")

        if os.path.exists(output_path):
            print("===== OUTPUT DEBUG =====")
            print("output exists =", True)
            print("output size bytes =", os.path.getsize(output_path))
        else:
            print("output exists =", False)
            raise HTTPException(status_code=500, detail="Le fichier de sortie n'a pas été créé")

        return FileResponse(
            output_path,
            media_type="image/jpeg",
            filename=f"anonymized_{uploaded_file.filename or 'image.jpg'}"
        )

    except HTTPException:
        raise
    except Exception as e:
        print("===== ERROR DEBUG =====")
        print("Exception =", repr(e))
        raise HTTPException(status_code=500, detail=f"Erreur traitement image: {str(e)}")

    finally:
        if input_path and os.path.exists(input_path):
            try:
                os.remove(input_path)
            except Exception as e:
                print("Impossible de supprimer input_path :", repr(e))
