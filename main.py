import os
import unicodedata
from fastapi import FastAPI
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

# Configuración de estáticos para imágenes locales
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

user_context = {}

# ---------------- UTILIDADES ----------------
def norm(t: str):
    """Limpia el texto: minúsculas, sin tildes y sin espacios extra."""
    t = t.lower().strip()
    return "".join(
        c for c in unicodedata.normalize("NFD", t)
        if unicodedata.category(c) != "Mn"
    )

def parse_txt(file_path):
    """Extrae secciones (Requisitos, Costos, etc.) de los archivos .txt."""
    if not os.path.exists(file_path):
        return {}
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    
    sections = ["Descripción", "Requisitos", "Procedimiento", "Costo", "Duración", "Horario"]
    data = {}
    for sec in sections:
        idx = content.lower().find(sec.lower())
        if idx != -1:
            next_indices = [content.lower().find(s.lower(), idx + len(sec)) for s in sections]
            next_indices = [i for i in next_indices if i > idx]
            end_idx = min(next_indices) if next_indices else len(content)
            data[norm(sec)] = content[idx + len(sec):end_idx].strip(": \n-—\t")
    return data

# ---------------- CARGA DE DATOS ----------------
DATA_PATH = os.path.join(os.path.dirname(__file__), "data")
DATA = {
    "retiro_ciclo": parse_txt(os.path.join(DATA_PATH, "retiro_ciclo.txt")),
    "retiro_asignatura": parse_txt(os.path.join(DATA_PATH, "retiro_asignatura.txt")),
    "reserva": parse_txt(os.path.join(DATA_PATH, "reserva_matricula.txt")),
    "reactualizacion": parse_txt(os.path.join(DATA_PATH, "reactualizacion_matricula.txt")),
}

MENU_TRAMITES = ["Retiro de ciclo", "Retiro de asignatura", "Reserva de matrícula", "Reactualización de matrícula", "Encuesta docentes"]
MENU_DETALLES = ["Requisitos", "Procedimiento", "Costo", "Duración", "Volver al inicio"]

PASOS_ENCUESTA = {
    1: {"text": "✨ PASO 1: Acceso al Intranet\nhttps://siugeo.aulavirtualusmp.pe/intranet", "img": "1.png", "btn": "Siguiente: Inicio de sesión ➡️"},
    2: {"text": "🔐 PASO 2: Inicio de sesión\nUsa tu DNI y correo institucional.", "img": "2.png", "btn": "Siguiente: Verificación ➡️"},
    3: {"text": "📧 PASO 3: Verificación\nIngresa el código enviado a tu correo.", "img": "3.png", "btn": "Siguiente: Ir a Intranet ➡️"},
    4: {"text": "🏠 PASO 4: Acceso a Intranet\nBusca el módulo: ENCUESTAS.", "img": "4.png", "btn": "Siguiente: Módulo Encuestas ➡️"},
    5: {"text": "📊 PASO 5: Módulo de encuestas\nLee las indicaciones con cuidado.", "img": "5.png", "btn": "Siguiente: Selección ➡️"},
    6: {"text": "📝 PASO 6: Selección\nElige la encuesta y haz clic en: REALIZAR.", "img": "6.png", "btn": "Siguiente: Responder preguntas ➡️"},
    7: {"text": "✍️ PASO 7: Desarrollo\nEs obligatorio responder todas las preguntas.", "img": "7.png", "btn": "Siguiente: Confirmación ➡️"},
    8: {"text": "✅ PASO 8: Confirmación\nVerifica el mensaje 'REGISTRO CORRECTO'.", "img": "8.png", "btn": "Siguiente: Ver estados ➡️"},
    9: {"text": "🎨 PASO 9: Estado final\n🟢 Verde: Completada\n🔵 Azul: Pendiente", "img": "9.png", "btn": "Finalizar tutorial"}
}

# ---------------- LÓGICA DEL CHAT ----------------
@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatQuery):
    q = norm(body.question)
    session = body.session_id
    base_img_url = "http://localhost:8000/static/encuesta_desempeno_docentes"

    # 1. RESET: Prioridad máxima para volver al inicio
    if any(x in q for x in ["inicio", "volver", "menu", "finalizar", "reset"]):
        user_context.pop(session, None)
        return {"response": "¡Claro! He vuelto al menú principal. ¿Qué trámite deseas consultar? 🌸", "options": MENU_TRAMITES}

    # 2. NAVEGACIÓN ENCUESTA: Si hay flecha o estamos en flujo de encuesta
    if "➡️" in body.question or ("siguiente" in q and "encuesta_" in user_context.get(session, "")):
        contexto = user_context.get(session, "")
        step = int(contexto.split("_")[1]) + 1 if "encuesta_" in contexto else 1
        
        if step <= 9:
            user_context[session] = f"encuesta_{step}"
            d = PASOS_ENCUESTA[step]
            return {"response": d[ "text"], "options": [d["btn"], "Volver al inicio"], "image": f"{base_img_url}/{d['img']}"}
        user_context.pop(session, None)
        return {"response": "✨ Tutorial finalizado con éxito.", "options": MENU_TRAMITES}

    # 3. DETECTAR NUEVO TRÁMITE
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
            return {"response": d["text"], "options": [d["btn"], "Volver al inicio"], "image": f"{base_img_url}/{d['img']}"}
        
        user_context[session] = target
        info = DATA.get(target, {})
        return {
            "response": f"📋 {target.replace('_',' ').upper()}\n\n{info.get('descripcion', 'Información disponible.')}\n\n¿Qué detalle deseas conocer?",
            "options": MENU_DETALLES
        }

    # 4. CONSULTAR DETALLES DE TRÁMITE ACTUAL
    context = user_context.get(session)
    if context and context in DATA:
        info = DATA[context]
        if "requisito" in q: res = f"📎 REQUISITOS:\n{info.get('requisitos', 'No detallados.')}"
        elif "procedimiento" in q: res = f"📝 PROCEDIMIENTO:\n{info.get('procedimiento', 'No detallado.')}"
        elif "costo" in q: res = f"💰 COSTO:\n{info.get('costo', 'Consultar tasas.')}"
        elif "duracion" in q: res = f"⏳ DURACIÓN:\n{info.get('duracion', '7 días hábiles.')}"
        else: res = "Puedes consultar los Requisitos, Procedimiento, Costo o Duración de este trámite."
        return {"response": res, "options": MENU_DETALLES}

    return {"response": "¡Hola! Soy Bot San Martino 🤖✨\n¿En qué trámite puedo ayudarte?", "options": MENU_TRAMITES}