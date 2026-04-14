from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile as StarletteUploadFile
from PIL import Image, ImageDraw, ImageFont
import json
import os
import tempfile
import uuid
from typing import List, Dict, Any

app = FastAPI()

PUBLIC_DIR = "public"
os.makedirs(PUBLIC_DIR, exist_ok=True)

app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")


# =========================
# Helpers
# =========================

def get_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf"
    ]

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass

    return ImageFont.load_default()


def average_color(pixels, fallback=(255, 255, 255)):
    if not pixels:
        return fallback
    r = int(sum(p[0] for p in pixels) / len(pixels))
    g = int(sum(p[1] for p in pixels) / len(pixels))
    b = int(sum(p[2] for p in pixels) / len(pixels))
    return (r, g, b)


def sample_background_color(img: Image.Image, x1: int, y1: int, x2: int, y2: int):
    """
    Prend des échantillons autour de la zone pour estimer la couleur de fond.
    On privilégie les pixels clairs pour éviter de prendre le texte.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size

    margin = 3
    samples = []

    regions = [
        (max(0, x1 - margin), max(0, y1 - margin), min(w, x2 + margin), y1),             # top
        (max(0, x1 - margin), y2, min(w, x2 + margin), min(h, y2 + margin)),             # bottom
        (max(0, x1 - margin), y1, x1, y2),                                                # left
        (x2, y1, min(w, x2 + margin), y2)                                                 # right
    ]

    for rx1, ry1, rx2, ry2 in regions:
        if rx2 > rx1 and ry2 > ry1:
            crop = rgb.crop((rx1, ry1, rx2, ry2))
            samples.extend(list(crop.getdata()))

    if not samples:
        return (255, 255, 255)

    bright_pixels = [p for p in samples if sum(p) >= 500]
    if bright_pixels:
        return average_color(bright_pixels, fallback=(255, 255, 255))

    return average_color(samples, fallback=(255, 255, 255))


def sample_text_color(img: Image.Image, x1: int, y1: int, x2: int, y2: int):
    """
    Cherche une couleur de texte probable dans la zone d'origine :
    on prend les pixels les plus sombres.
    """
    rgb = img.convert("RGB")
    crop = rgb.crop((x1, y1, x2, y2))
    pixels = list(crop.getdata())

    if not pixels:
        return (0, 0, 0)

    # On trie par luminance croissante (plus sombre d'abord)
    pixels_sorted = sorted(
        pixels,
        key=lambda p: 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]
    )

    darkest_count = max(1, int(len(pixels_sorted) * 0.15))
    darkest_pixels = pixels_sorted[:darkest_count]

    return average_color(darkest_pixels, fallback=(0, 0, 0))


def fit_text_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int):
    """
    Trouve une taille de police qui tient dans la zone.
    """
    if not text:
        return get_font(10), 0, 0, (0, 0, 0, 0)

    start_size = max(6, int(max_height * 0.95))

    for size in range(start_size, 5, -1):
        font = get_font(size)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        if tw <= max_width and th <= max_height:
            return font, tw, th, bbox

    font = get_font(6)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    return font, tw, th, bbox


# =========================
# Routes
# =========================

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

                replacement_text = str(zone.get("ReplacementText", "") or "")
                pad_x = float(zone.get("PadXPx", 1.0) or 1.0)
                pad_y = float(zone.get("PadYPx", 1.0) or 1.0)

                scale_x = image_width / page_width
                scale_y = image_height / page_height

                x1 = round(pdf_x * scale_x)
                y1 = round(pdf_y * scale_y)
                x2 = round((pdf_x + pdf_w) * scale_x)
                y2 = round((pdf_y + pdf_h) * scale_y)

                # Rectangle moins large
                x1 = max(0, int(round(x1 - pad_x)))
                y1 = max(0, int(round(y1 - pad_y)))
                x2 = min(image_width, int(round(x2 + pad_x)))
                y2 = min(image_height, int(round(y2 + pad_y)))

                if x2 <= x1:
                    x2 = x1 + 1
                if y2 <= y1:
                    y2 = y1 + 1

                # Couleur de fond dynamique
                background_color = sample_background_color(img, x1, y1, x2, y2)

                # Couleur du texte dynamique
                text_color = sample_text_color(img, x1, y1, x2, y2)

                print("===== ZONE DEBUG =====", flush=True)
                print("zone_index =", idx, flush=True)
                print("raw zone =", zone, flush=True)
                print("mapped pdf_x =", pdf_x, flush=True)
                print("mapped pdf_y =", pdf_y, flush=True)
                print("pdf_w =", pdf_w, flush=True)
                print("pdf_h =", pdf_h, flush=True)
                print("rect_pixels =", x1, y1, x2, y2, flush=True)
                print("replacement_text =", replacement_text, flush=True)
                print("background_color =", background_color, flush=True)
                print("text_color =", text_color, flush=True)

                # On masque la zone
                draw.rectangle([x1, y1, x2, y2], fill=background_color)

                # On réécrit par-dessus si demandé
                if replacement_text.strip():
                    rect_w = max(1, x2 - x1)
                    rect_h = max(1, y2 - y1)

                    font, tw, th, bbox = fit_text_font(
                        draw,
                        replacement_text,
                        max_width=max(1, rect_w - 2),
                        max_height=max(1, rect_h - 1)
                    )

                    # Alignement gauche, centré verticalement
                    text_x = x1 + 1
                    text_y = y1 + max(0, (rect_h - th) // 2) - bbox[1]

                    draw.text(
                        (text_x, text_y),
                        replacement_text,
                        fill=text_color,
                        font=font
                    )

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
