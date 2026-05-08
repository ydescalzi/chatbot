import os
import logging
import unicodedata
import uvicorn
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Union

# ---------------- LOGGING ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------- HUGGING FACE ----------------
HF_API_URL = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.2"
HF_HEADERS = {"Authorization": f"Bearer {os.getenv('HF_API_KEY', '')}"}

HF_SYSTEM_PROMPT = (
    "Eres un asistente académico de la USMP. "
    "Responde SOLO sobre trámites, matrícula e intranet. "
    "Sé breve y directo."
)

def ask_huggingface(prompt: str) -> Optional[str]:
    if not os.getenv("HF_API_KEY"):
        logger.warning("HF_API_KEY no configurada.")
        return None

    payload = {
        "inputs": f"{HF_SYSTEM_PROMPT}\n\nUsuario: {prompt}\nAsistente:",
        "parameters": {
            "max_new_tokens": 120,
            "return_full_text": False,
        },
    }

    try:
        r = requests.post(HF_API_URL, headers=HF_HEADERS, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()

        if isinstance(data, list) and data:
            return data[0].get("generated_text", "").strip() or None

        if isinstance(data, dict) and "error" in data:
            msg = data["error"].lower()
            if "loading" in msg:
                return "⏳ La IA está iniciando, intenta en unos segundos."
            logger.error("HF error: %s", data["error"])
            return None

    except Exception as e:
        logger.error("Error en ask_huggingface: %s", e)

    return None


# ---------------- RUTAS ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
STATIC_BASE_URL = os.getenv("STATIC_BASE_URL", "http://127.0.0.1:8000")

# ---------------- MODELOS ----------------
class ChatQuery(BaseModel):
    question: str
    session_id: str = "default"

class Section(BaseModel):
    title: str
    icon: str
    content: Union[str, List[str]]

class ChatResponse(BaseModel):
    response: Union[str, List[Section], None]
    options: List[str]
    image: Optional[str] = None


# ---------------- APP ----------------
app = FastAPI(title="Bot San Martino", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ---------------- CONTEXTO DE SESIÓN ----------------
user_context: dict = {}

# ---------------- NORMALIZACIÓN ----------------
TYPO_MAP = {
    "fotho": "foto",
    "subr": "subir",
    "retirame": "retirarme",
    "contrase": "contrasena",
    "apalzados": "aplazados",
    "olvide": "olvide",
}

def norm(text: str) -> str:
    text = text.lower().strip()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    for wrong, right in TYPO_MAP.items():
        text = text.replace(wrong, right)
    return text


# ---------------- CARGA DE TXT ----------------

def load_structured_txt(file_name: str) -> List[Section]:
    manual_sections = {
        "retiro_ciclo.txt": [
            Section(title="¿Qué es?", icon="🧾", content="Es el trámite para retirarte completamente del semestre actual."),
            Section(title="¿Quién puede hacerlo?", icon="👤", content="Estudiantes de pregrado (Filial Norte)."),
            Section(title="¿Cuándo hacerlo?", icon="⏰", content="Desde la semana 2 hasta antes de exámenes finales (≈ semana 14)."),
            Section(title="Antes de empezar", icon="🚫", content=[
                "No debes tener deudas con la universidad",
                "No hay devolución de dinero una vez realizado"
            ]),
            Section(title="¿Cómo lo hago?", icon="📝", content=[
                "1️⃣ Presenta tu solicitud en Mesa de Partes (virtual o presencial)",
                "2️⃣ O envíalo por correo: 📩 mesa_partes_fn@usmp.pe",
                "3️⃣ Adjunta TODOS los documentos en un solo archivo PDF",
                "4️⃣ Asunto del correo: 👉 RETIRO DE CICLO"
            ]),
            Section(title="Requisitos", icon="📎", content=[
                "✔ Solicitud registrada",
                "✔ DNI escaneado",
                "✔ Sin deudas"
            ]),
            Section(title="Costo", icon="💰", content="S/ 3.00"),
            Section(title="Tiempo de respuesta", icon="⏳", content="7 días hábiles"),
            Section(title="Horario de atención", icon="🕒", content=[
                "Lunes a viernes",
                "08:00 – 13:00",
                "13:45 – 16:45"
            ]),
            Section(title="Importante", icon="📌", content=[
                "Una vez aprobado: se elimina tu matrícula",
                "Se anulan tus recibos"
            ]),
        ],
        "retiro_asignatura.txt": [
            Section(title="¿Qué es?", icon="🧾", content="Es el trámite para retirarte de una o más asignaturas en el semestre actual."),
            Section(title="¿Quién puede hacerlo?", icon="👤", content="Estudiantes de pregrado (Filial Norte)."),
            Section(title="¿Cuándo hacerlo?", icon="⏰", content="Desde la semana 2 hasta la semana 14 del semestre."),
            Section(title="Antes de empezar", icon="🚫", content=[
                "No debes tener deudas con la universidad",
                "Este trámite NO reduce el costo de tus pensiones"
            ]),
            Section(title="¿Cómo lo hago?", icon="📝", content=[
                "1️⃣ Presenta tu solicitud en Mesa de Partes (virtual o presencial)",
                "2️⃣ O envíalo por correo: 📩 mesa_partes_fn@usmp.pe",
                "3️⃣ Adjunta TODOS los documentos en un solo archivo PDF",
                "4️⃣ Asunto del correo: 👉 RETIRO DE ASIGNATURA"
            ]),
            Section(title="Requisitos", icon="📎", content=[
                "✔ Solicitud registrada",
                "✔ Recibo cancelado",
                "✔ DNI escaneado",
                "✔ No tener deudas"
            ]),
            Section(title="Costo", icon="💰", content=[
                "S/ 3.00 (trámite)",
                "S/ 10.00 (derecho de retiro)"
            ]),
            Section(title="Tiempo de respuesta", icon="⏳", content="7 días hábiles"),
            Section(title="Horario de atención", icon="🕒", content=[
                "Lunes a viernes",
                "08:00 – 13:00",
                "13:45 – 16:45"
            ]),
            Section(title="Importante", icon="📌", content=[
                "✔ Las asignaturas se eliminan del sistema tras aprobación",
                "✔ Si no haces el trámite y no asistes → obtendrás nota 00",
                "✔ Debes verificar la anulación en el Portal Académico SAP",
                "⚠️ Las solicitudes fuera de horario se atienden progresivamente."
            ]),
        ],
        "reserva_matricula.txt": [
            Section(title="¿Qué es?", icon="🧾", content="Es el trámite mediante el cual dejas formalmente de estudiar un semestre académico."),
            Section(title="¿Quién puede hacerlo?", icon="👤", content="Estudiantes de pregrado (Filial Norte)."),
            Section(title="Consideraciones importantes", icon="⚠️", content=[
                "Puedes solicitarlo hasta la semana 14 del semestre",
                "La reserva puede renovarse hasta un máximo de 3 años",
                "Si estás en deficiencia académica → debes pasar evaluación previa",
                "El resultado se consulta en Mesa de Partes Virtual",
                "Puedes solicitar una constancia de reserva"
            ]),
            Section(title="¿Cómo lo hago?", icon="📝", content=[
                "1️⃣ Registra tu solicitud en Mesa de Partes Virtual",
                "2️⃣ Usa el formato establecido",
                "3️⃣ Adjunta tu recibo cancelado"
            ]),
            Section(title="Enlace útil", icon="🌐", content="https://siugeo.aulavirtualusmp.pe/intranet"),
            Section(title="Requisitos", icon="📎", content=[
                "✔ Solicitud registrada",
                "✔ Formato correcto",
                "✔ Recibo cancelado"
            ]),
            Section(title="Costo", icon="💰", content="S/ 50.00"),
            Section(title="Tiempo de respuesta", icon="⏳", content="7 días hábiles"),
            Section(title="Horario de atención", icon="🕒", content="Consultar en Mesa de Partes"),
        ],
        "reactualizacion_matricula.txt": [
            Section(title="¿Qué es?", icon="🧾", content="Es el trámite que permite habilitar tu matrícula para el semestre actual si dejaste de estudiar uno o más ciclos sin hacer reserva."),
            Section(title="¿Quién puede hacerlo?", icon="👤", content="Estudiantes de pregrado que interrumpieron sus estudios sin realizar reserva de matrícula."),
            Section(title="Consideraciones importantes", icon="⚠️", content=[
                "Debes presentar tu solicitud según cronograma",
                "La universidad evaluará tu caso",
                "Debes adaptarte al plan curricular vigente",
                "La matrícula se realiza en el Portal Académico SAP",
                "Puede requerirse matrícula asistida",
                "Puedes matricularte desde 4 créditos (según disponibilidad)",
                "No debe haber cruce de horarios",
                "Si tienes deficiencia académica → debes hacer matrícula condicionada",
                "Trámites fuera de fecha solo permiten cursos disponibles"
            ]),
            Section(title="¿Cómo lo hago?", icon="📝", content=[
                "1️⃣ Registrar solicitud en Mesa de Partes (virtual o presencial)",
                "2️⃣ Esperar evaluación de la universidad",
                "3️⃣ Realizar matrícula en el Portal SAP"
            ]),
            Section(title="Requisitos", icon="📎", content=[
                "✔ Solicitud registrada",
                "✔ Formato establecido",
                "✔ No tener deudas"
            ]),
            Section(title="Costo", icon="💰", content="S/ 60.00"),
            Section(title="Duración", icon="⏳", content="3 semanas aproximadamente"),
            Section(title="Dónde hacerlo", icon="📍", content=[
                "Mesa de Partes Filial Norte",
                "📩 mesa_partes_fn@usmp.pe",
                "🌐 https://siugeo.aulavirtualusmp.pe/intranet"
            ]),
        ],
        "matricula_condicionada.txt": [
            Section(title="¿Qué es?", icon="🧾", content="Es un trámite excepcional que permite al estudiante continuar sus estudios cuando presenta deficiencia académica."),
            Section(title="¿Quién puede solicitarlo?", icon="👤", content=[
                "Estudiantes de pregrado que han desaprobado 3 veces la misma asignatura",
                "Estudiantes que han desaprobado 2 veces consecutivas 3 o más cursos"
            ]),
            Section(title="Consideraciones importantes", icon="⚠️", content=[
                "Solo se otorga UNA VEZ",
                "Debes solicitarlo antes del proceso de matrícula",
                "Tu caso será evaluado por la Comisión Académica",
                "El Decanato emite la resolución final",
                "Deberás firmar una carta de compromiso"
            ]),
            Section(title="Según tu situación", icon="📌", content=[
                "Dependiente: DNI del apoderado",
                "Independiente (trabaja): DNI, constancia de trabajo, 3 últimas boletas de pago"
            ]),
            Section(title="¿Cómo realizar el trámite?", icon="📝", content=[
                "1️⃣ Registrar solicitud en Mesa de Partes (virtual o presencial)",
                "2️⃣ Esperar evaluación de la Comisión Académica",
                "3️⃣ Firmar carta de compromiso",
                "4️⃣ Realizar pago de matrícula",
                "5️⃣ Completar matrícula en el Portal Académico SAP"
            ]),
            Section(title="Requisitos", icon="📎", content="✔ Solicitud registrada en Mesa de Partes"),
            Section(title="Importante", icon="⚠️", content="Si no es aprobado se aplicará el Reglamento General de la Universidad")
        ],
        "justificacion_inasistencia.txt": [
            Section(title="¿Qué es?", icon="🧾", content="Es el trámite para justificar tu inasistencia y consultar el estado de tus reportes de asistencia."),
            Section(title="Pasos", icon="📝", content=[
                "1️⃣ Accede al intranet: https://siugeo.aulavirtualusmp.pe/intranet",
                "2️⃣ Recibirás un código de verificación en tu correo institucional. Cópialo y pégalo en el sistema y haz clic en 'Verificar'.",
                "3️⃣ Dirígete a Trámite Documentario → Registrar.",
                "4️⃣ Selecciona el motivo: 'Justificación de inasistencia'.",
                "5️⃣ Selecciona el curso correspondiente, agrega un comentario y adjunta tu solicitud con evidencias. Luego haz clic en 'Registrar'.",
                "6️⃣ Revisa tu correo institucional para confirmar el registro de tu solicitud.",
                "7️⃣ Para ver el estado del trámite: Ir a Consultar Trámite → Ver.",
                "8️⃣ Para ver tu asistencia: Ir a Menú Inicio → Reportes de Asistencia.",
                "9️⃣ Selecciona tu periodo académico y haz clic en 'Consultar'.",
                "🔟 Verás tus cursos matriculados en ese periodo. Selecciona un curso para ver el detalle de asistencia semanal."
            ]),
            Section(title="Requisitos", icon="📎", content="Documentos y evidencias según el motivo de justificación."),
        ],
    }

    if file_name in manual_sections:
        return manual_sections[file_name]

    path = os.path.join(DATA_DIR, file_name)
    if not os.path.exists(path):
        logger.warning("Archivo no encontrado: %s", path)
        return [Section(title="Error", icon="❌", content="Información no disponible por el momento.")]

    sections = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) != 3:
                continue
            title, icon, content_raw = parts
            content = [i.strip() for i in content_raw.split(";") if i.strip()] if ";" in content_raw else content_raw.strip()
            sections.append(Section(title=title.strip(), icon=icon.strip(), content=content))
    return sections


# ---------------- BUSCADOR TARIFARIO ----------------
def buscar_en_tarifario(sections: List[Section], query: str) -> List[Section]:
    stopwords = PRECIO_KEYWORDS | {"la", "el", "los", "las", "de", "del", "por", "con", "una", "uno"}
    palabras = [p for p in query.split() if len(p) > 2 and p not in stopwords]
    if not palabras: return []
    
    usar_and = len(palabras) >= 2
    resultados = []
    for sec in sections:
        if isinstance(sec.content, list):
            filtrados = [item for item in sec.content if (all(p in norm(item) for p in palabras) if usar_and else any(p in norm(item) for p in palabras))]
            if not filtrados and usar_and:
                filtrados = [item for item in sec.content if any(p in norm(item) for p in palabras)]
            if filtrados:
                resultados.append(Section(title=sec.title, icon=sec.icon, content=filtrados))
    return resultados


# ---------------- PREGUNTAS FRECUENTES ----------------
FAQ_RESPONSES = {
    "horario": "📞 **Horario de Mesa de Partes:**\n⏰ Lunes a viernes: 08:00 - 13:00 y 13:45 - 16:45",
    "mail": "📧 **Correo Mesa de Partes:** mesa_partes_fn@usmp.pe",
    "intranet": "🌐 **Acceso Intranet:** https://siugeo.aulavirtualusmp.pe/intranet",
    "ubicacion": "📍 **Ubicación:** Mesa de Partes Filial Norte - Campus USMP",
    "documentos": "📄 Todos los documentos deben estar en un solo archivo PDF",
    "costo": "💰 Los costos varían según el trámite. Consulta el tarifario.",
    "tiempo": "⏳ Tiempo de respuesta: generalmente 7 días hábiles",
    "deuda": "🚫 No puedes realizar trámites si tienes deudas con la universidad",
    "ayuda": "¿En qué puedo ayudarte? Cuéntame sobre tu trámite o pregunta específica",
    "hola": "👋 ¡Hola! Soy Bot San Martino, asistente académico de la USMP. ¿Cómo puedo ayudarte?",
}


# ---------------- CONFIGURACIÓN Y MENÚS ----------------
PASOS_CONFIG = {
    "registro_foto": {
        "path": "registro_foto",
        "steps": {
            1: {"text": "🌐 Paso 1: Ingresa a Intranet.", "img": "1.png"},
            2: {"text": "🔐 Paso 2: Ingresa tu código de verificación.", "img": "2.png"},
            3: {"text": "📷 Paso 3: Sube tu foto académica.", "img": "3.png"},
            4: {"text": "⚖️ Paso 4: Acepta los términos y condiciones.", "img": "4.png"},
            5: {"text": "✅ Paso 5: Confirmación exitosa.", "img": "5.png"},
        },
    }
}

MENU_PERFILES = ["Estudiante", "Docente", "Persona externa", "Egresado"]
MENU_TRAMITES = [
    "Retiro de ciclo", "Retiro de asignatura", "Reserva de matrícula",
    "Registro de foto académica", "Reactualización de matrícula",
    "Matrícula condicionada", "Justificación de inasistencia",
    "Olvidé mi clave", "Ver mi asistencia", "Soporte en línea / Plataformas",
    "Carreras disponibles", "Contacto y WhatsApp",
]
MENU_POST = ["Volver al inicio"]

# MAPEO NUMÉRICO PARA ESTUDIANTES
NUMERIC_MENU_MAP = {
    "1": "retiro de ciclo",
    "2": "retiro de asignatura",
    "3": "reserva de matricula",
    "4": "registro de foto academica",
    "5": "reactualizacion de matricula",
    "6": "matricula condicionada",
    "7": "justificacion de inasistencia",
    "8": "olvide mi clave",
    "9": "ver mi asistencia",
    "10": "soporte",
    "11": "carreras",
    "12": "contacto",
}

TRAMITES_MAP = {
    "retiro de ciclo": "retiro_ciclo.txt",
    "retiro de asignatura": "retiro_asignatura.txt",
    "reserva de matricula": "reserva_matricula.txt",
    "reactualizacion": "reactualizacion_matricula.txt",
    "matricula condicionada": "matricula_condicionada.txt",
    "inasistencia": "justificacion_inasistencia.txt",
}

SOPORTE_MAP = {
    "soporte": "soporte_en_linea.txt", "plataforma": "soporte_en_linea.txt",
    "intranet": "soporte_en_linea.txt", "asistencia": "asistencia.txt",
    "carrera": "carreras.txt", "whatsapp": "contacto_whatsapp.txt",
    "contacto": "contacto_whatsapp.txt"
}

PRECIO_KEYWORDS = {"cuanto", "costo", "precio", "vale", "pago", "tarifa", "soles"}

def build_image_url(tramite_path: str, img: str) -> str:
    return f"{STATIC_BASE_URL}/static/{tramite_path}/{img}"

def reset_session(session: str) -> None:
    user_context.pop(session, None)

def inicio_response() -> dict:
    return {"response": "👋 Hola, soy **Bot San Martino** 🤖\n¿Con quién tengo el gusto?", "options": MENU_PERFILES}


# ---------------- ENDPOINT PRINCIPAL ----------------
@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatQuery):
    # --- INTERPRETACIÓN DE ENTRADA (NÚMEROS O TEXTO) ---
    raw_q = body.question.strip()
    if raw_q in NUMERIC_MENU_MAP:
        q = norm(NUMERIC_MENU_MAP[raw_q])
    else:
        q = norm(raw_q)
        
    session = body.session_id
    if not q:
        raise HTTPException(status_code=400, detail="Pregunta vacía")

    # --- LÓGICA DE NAVEGACIÓN ---
    if any(x in q for x in ["hola", "inicio", "menu", "empezar", "reiniciar"]):
        reset_session(session)
        return inicio_response()

    user_context.setdefault(session, {})
    context = user_context[session]

    if "perfil" not in context:
        if "estudiante" in q:
            context["perfil"] = "estudiante"
            return {"response": "🎓 ¡Hola, estudiante! ¿En qué trámite puedo ayudarte?", "options": MENU_TRAMITES}
        if "docente" in q:
            context["perfil"] = "docente"
            return {"response": "👨‍🏫 ¡Hola, docente! ¿En qué puedo ayudarte?", "options": ["Olvidé mi clave", "Volver al inicio"]}
        if any(x in q for x in ["externa", "externo", "visitante"]):
            context["perfil"] = "externo"
            return {"response": "🙋 ¡Hola! Para información general, contáctanos en usmp.edu.pe", "options": MENU_POST}
        return {"response": "No reconocí tu perfil. ¿Eres estudiante, docente o persona externa?", "options": MENU_PERFILES}

    if any(x in q for x in ["volver", "atras", "regresar", "cancelar"]):
        reset_session(session)
        return inicio_response()

# --- BÚSQUEDA EN FAQ ---
    for faq_key, faq_response in FAQ_RESPONSES.items():
        if faq_key in q:
            return {"response": faq_response, "options": MENU_POST}

    # --- BÚSQUEDA DE TRÁMITES Y SOPORTE ---
    for key, file in TRAMITES_MAP.items():
        if key in q:
            return {"response": load_structured_txt(file), "options": MENU_POST}

    for key, file in SOPORTE_MAP.items():
        if key in q:
            return {"response": load_structured_txt(file), "options": MENU_POST}

    # --- REGISTRO DE FOTO ---
    if "foto" in q:
        context.update({"tramite": "registro_foto", "step": 1})
        step_data = PASOS_CONFIG["registro_foto"]["steps"][1]
        return {"response": step_data["text"], "options": ["Siguiente ➡️", "Volver al inicio"], "image": build_image_url("registro_foto", "1.png")}

    # --- PASOS SIGUIENTES ---
    tramite_activo = context.get("tramite")
    if tramite_activo and "siguiente" in q:
        config = PASOS_CONFIG[tramite_activo]
        next_step = context.get("step", 1) + 1
        if next_step > len(config["steps"]):
            reset_session(session)
            return {"response": "✅ ¡Proceso completado! ¿Necesitas algo más?", "options": MENU_POST}
        context["step"] = next_step
        step_data = config["steps"][next_step]
        return {"response": step_data["text"], "options": ["Siguiente ➡️", "Volver al inicio"], "image": build_image_url(config["path"], step_data["img"])}

    if any(x in q for x in ["clave", "contrasena", "olvide", "password"]):
        return {"response": load_structured_txt("olvido_clave.txt"), "options": MENU_POST}
  
    # --- PRECIOS ---
    if PRECIO_KEYWORDS & set(q.split()):
        sections = load_structured_txt("tarifario.txt")
        resultados = buscar_en_tarifario(sections, q)
        if resultados:
            return {"response": resultados, "options": MENU_POST}
        return {"response": "💰 Para información de costos de trámites, consulta el tarifario disponible en Mesa de Partes o envía un correo a mesa_partes_fn@usmp.pe", "options": MENU_POST}

    # --- FALLBACK: BÚSQUEDA GENERAL POR PALABRAS ---
    palabras_clave = q.split()
    if len(palabras_clave) > 0:
        # Intenta encontrar coincidencia en trámites por palabra individual
        for key in TRAMITES_MAP.keys():
            if any(palabra in key for palabra in palabras_clave):
                return {"response": load_structured_txt(TRAMITES_MAP[key]), "options": MENU_POST}
        for key in SOPORTE_MAP.keys():
            if any(palabra in key for palabra in palabras_clave):
                return {"response": load_structured_txt(SOPORTE_MAP[key]), "options": MENU_POST}

    # --- FALLBACK IA ---
    ai_response = ask_huggingface(body.question)
    if ai_response:
        return {"response": ai_response, "options": MENU_POST}

    # --- RESPUESTA FINAL AMIGABLE ---
    return {
        "response": "😊 Parece que tu pregunta no está en mi base de datos. Pero puedo ayudarte con:\n\n"
                   "✅ Trámites: retiro de ciclo, reserva de matrícula, foto académica, etc.\n"
                   "✅ Preguntas: horarios, correos, ubicación\n"
                   "✅ Soporte técnico\n\n"
                   "¿Necesitas información sobre alguno de estos temas?",
        "options": MENU_TRAMITES
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)