import os
import unicodedata
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

# ---------------- MODELOS ----------------
class ChatQuery(BaseModel):
    question: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    options: List[str]
    image: Optional[str] = None

# ---------------- APP CONFIG ----------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔥 SERVIR IMÁGENES
app.mount("/static", StaticFiles(directory="static"), name="static")

user_context = {}

# ---------------- UTILIDADES ----------------
def norm(t: str):
    t = t.lower().strip()
    return "".join(
        c for c in unicodedata.normalize("NFD", t)
        if unicodedata.category(c) != "Mn"
    )

def parse_txt(file_path):
    if not os.path.exists(file_path):
        return {}

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    sections = ["Descripción", "Requisitos", "Procedimiento", "Costo", "Duración", "Horario"]
    data = {}

    for sec in sections:
        idx = content.lower().find(sec.lower())
        if idx != -1:
            next_indices = [
                content.lower().find(s.lower(), idx + len(sec))
                for s in sections
            ]
            next_indices = [i for i in next_indices if i > idx]
            end_idx = min(next_indices) if next_indices else len(content)

            data[norm(sec)] = content[idx + len(sec):end_idx].strip(": \n-—\t")

    return data

# ---------------- DATA ----------------
BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "data")

DATA = {
    "retiro_ciclo": parse_txt(os.path.join(DATA_PATH, "retiro_ciclo.txt")),
    "retiro_asignatura": parse_txt(os.path.join(DATA_PATH, "retiro_asignatura.txt")),
    "reserva": parse_txt(os.path.join(DATA_PATH, "reserva_matricula.txt")),
    "reactualizacion": parse_txt(os.path.join(DATA_PATH, "reactualizacion_matricula.txt")),
}

MENU_TRAMITES = [
    "Retiro de ciclo",
    "Retiro de asignatura",
    "Reserva de matrícula",
    "Reactualización de matrícula",
    "Encuesta docentes"
]

MENU_DETALLES = [
    "Requisitos",
    "Procedimiento",
    "Costo",
    "Duración",
    "Volver al inicio"
]

# ---------------- ENCUESTA ----------------
PASOS_ENCUESTA = {
    1: {"text": "✨ PASO 1: Acceso al Intranet\nhttps://siugeo.aulavirtualusmp.pe/intranet", "img": "1.png", "btn": "Siguiente ➡️"},
    2: {"text": "🔐 PASO 2: Inicio de sesión\nUsa tu DNI y correo institucional.", "img": "2.png", "btn": "Siguiente ➡️"},
    3: {"text": "📧 PASO 3: Verificación\nIngresa el código enviado a tu correo.", "img": "3.png", "btn": "Siguiente ➡️"},
    4: {"text": "🏠 PASO 4: Acceso a Intranet\nBusca el módulo ENCUESTAS.", "img": "4.png", "btn": "Siguiente ➡️"},
    5: {"text": "📊 PASO 5: Módulo de encuestas", "img": "5.png", "btn": "Siguiente ➡️"},
    6: {"text": "📝 PASO 6: Selecciona la encuesta", "img": "6.png", "btn": "Siguiente ➡️"},
    7: {"text": "✍️ PASO 7: Responde todas las preguntas", "img": "7.png", "btn": "Siguiente ➡️"},
    8: {"text": "✅ PASO 8: Confirmación", "img": "8.png", "btn": "Siguiente ➡️"},
    9: {"text": "🎨 PASO 9: Estado final", "img": "9.png", "btn": "Finalizar"}
}

# ---------------- ENDPOINT ----------------
@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatQuery, request: Request):
    q = norm(body.question)
    session = body.session_id

    # 🔥 URL DINÁMICA (CLAVE)
    base_url = str(request.base_url).rstrip("/")
    base_img_url = f"{base_url}/static/encuesta_desempeno_docentes"

    # RESET
    if any(x in q for x in ["inicio", "volver", "menu", "finalizar"]):
        user_context.pop(session, None)
        return {
            "response": "🔄 Volviste al inicio. ¿Qué trámite deseas?",
            "options": MENU_TRAMITES
        }

    # ENCUESTA
    if "siguiente" in q or "➡️" in body.question:
        contexto = user_context.get(session, "")
        step = int(contexto.split("_")[1]) + 1 if "encuesta_" in contexto else 1

        if step <= 9:
            user_context[session] = f"encuesta_{step}"
            d = PASOS_ENCUESTA[step]

            return {
                "response": d["text"],
                "options": [d["btn"], "Volver al inicio"],
                "image": f"{base_img_url}/{d['img']}"
            }

        user_context.pop(session, None)
        return {
            "response": "🎉 Encuesta completada correctamente.",
            "options": MENU_TRAMITES
        }

    # SELECCIÓN TRÁMITE
    target = None
    if "ciclo" in q: target = "retiro_ciclo"
    elif "asignatura" in q: target = "retiro_asignatura"
    elif "reserva" in q: target = "reserva"
    elif "reactualizacion" in q: target = "reactualizacion"
    elif "encuesta" in q: target = "encuesta"

    if target:
        if target == "encuesta":
            user_context[session] = "encuesta_1"
            d = PASOS_ENCUESTA[1]

            return {
                "response": d["text"],
                "options": [d["btn"], "Volver al inicio"],
                "image": f"{base_img_url}/{d['img']}"
            }

        user_context[session] = target
        info = DATA.get(target, {})

        return {
            "response": f"📋 {target.replace('_',' ').upper()}\n\n{info.get('descripcion','Información disponible.')}",
            "options": MENU_DETALLES
        }

    # DETALLES
    context = user_context.get(session)
    if context in DATA:
        info = DATA[context]

        if "requisito" in q:
            res = f"📎 REQUISITOS:\n{info.get('requisitos')}"
        elif "procedimiento" in q:
            res = f"📝 PROCEDIMIENTO:\n{info.get('procedimiento')}"
        elif "costo" in q:
            res = f"💰 COSTO:\n{info.get('costo')}"
        elif "duracion" in q:
            res = f"⏳ DURACIÓN:\n{info.get('duracion')}"
        else:
            res = "Puedes consultar requisitos, procedimiento, costo o duración."

        return {"response": res, "options": MENU_DETALLES}

    return {
        "response": "👋 Hola, soy Bot San Martino 🤖. ¿En qué puedo ayudarte?",
        "options": MENU_TRAMITES
    }
