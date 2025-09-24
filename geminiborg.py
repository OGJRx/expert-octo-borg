import json  # Agregado para parsing seguro de JSON de Gemini
import logging
import asyncio
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CommandHandler, filters
from telegram.constants import ParseMode
from telegram import ReplyKeyboardRemove
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import pytesseract
from config import Config
import re
import os

logger = logging.getLogger(__name__)

def escape_markdown_v2(text: str) -> str:
    """Helper function to escape special characters for MarkdownV2."""
    # Escape backslash first to prevent issues with other escapes
    text = text.replace('\\', '\\\\')
    special_chars = r'_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

# Conversation states
ASK_FOR_INPUT, HANDLE_FILE, HANDLE_INCOME, ASK_DEEPER_INSIGHT = range(4)

class GeminiBorg:
    def __init__(self):
        self.config = Config()

        self.model_name = 'gemini-2.5-flash' # Using gemini-2.5-flash as specified
        self.setup_ai_client()
        self.model = genai.GenerativeModel(self.model_name)

    def setup_ai_client(self):
        """Configurar conexión con Google AI Client"""
        genai.configure(api_key=self.config.GOOGLE_AI_KEY)

    async def _generate_content_stream(self, prompt: str) -> str:
        """Generates content using Gemini's streaming API correctly."""
        # NOTA: La estructura de la configuración y los contenidos se ha actualizado
        # para coincidir con la última versión del SDK de google-generativeai.
        
        generation_config = genai.types.GenerationConfig(
            temperature=0.75,
            max_output_tokens=4000,
        )

        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        full_response = []
        try:
            # Esta es la forma correcta de llamar a la API en un entorno asíncrono.
            # No se necesita loop.run_in_executor.
            response = await self.model.generate_content_async(
                contents=[prompt],  # La forma de pasar el prompt es más directa
                stream=True,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # El 'async for' ahora funcionará porque la respuesta es un generador asíncrono.
            async for chunk in response:
                if chunk.text: # Asegurarse de que el chunk no esté vacío
                    full_response.append(chunk.text)
            
            return "".join(full_response)
        
        except Exception as e:
            logger.error(f"Error generating content with Gemini: {e}")
            return "Lo siento, hubo un error al generar la respuesta con Gemini."

    async def presupuesto_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Starts the /Presupuesto conversation with a professional and conversational message."""
        message = """👋 ¡Hola! Soy *BORG*, tu **asistente financiero personal** 🤖. Impulsado por Google Gemini, te ayudaré a tomar el control de tus finanzas con un plan de presupuesto personalizado. 🚀

Para crear tu plan, necesito información. Elige una opción:

1️⃣ 📄 *Sube un archivo (PDF o TXT)*:
Envía estados de cuenta o documentos financieros. Analizaré tu situación para un presupuesto contextualizado. ¡Tu privacidad es clave! 🔒

2️⃣ 💰 *Ingresa tu ingreso mensual*:
Indica cuánto ganas al mes (ej. `Gano 20000 MXN`). Con esto, crearé tu plan financiero. ¡Rápido y sencillo! 📈

3️⃣ ⏩ *Usa /skip*:
Si prefieres un plan genérico, usaré un ingreso predefinido. ¡Ideal para una visión general! 💡

Mi meta es que domines tus finanzas como un experto. ¡Empecemos a construir tu futuro financiero! ✨"""
        escaped_message = escape_markdown_v2(message)
        await update.message.reply_text(escaped_message, parse_mode=ParseMode.MARKDOWN_V2)
        return ASK_FOR_INPUT

    async def skip_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Skips input and generates a generic budget plan."""
        await update.message.reply_text("Generando un plan de presupuesto genérico... ⏳")
        # Here we will call the budget generation logic with a generic income
        await self._generate_budget_plan(update, context, income=20000, user_input="generic plan")
        return ConversationHandler.END

    async def handle_message_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handles text input for income or file upload."""
        text = update.message.text
        if text and ("gano" in text.lower() or "ingreso" in text.lower() or "salario" in text.lower()):
            # Assume it's an income input
            await update.message.reply_text("Analizando tu ingreso... 💰")
            context.user_data['user_income_input'] = text
            return await self._process_income_input(update, context)
        elif update.message.document:
            # Assume it's a file upload
            await update.message.reply_text("Recibiendo tu archivo... 📄")
            context.user_data['file_info'] = update.message.document
            return await self._process_file_input(update, context)
        else:
            await update.message.reply_text("No entiendo tu entrada. Por favor, sube un archivo, ingresa tu ingreso o usa /skip.")
            return ASK_FOR_INPUT

    async def _process_income_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Processes the income input and generates a budget plan."""
        user_input = context.user_data.get('user_income_input', "")
        income = self._extract_income_from_text(user_input)
        if income:
            await self._generate_budget_plan(update, context, income=income, user_input=user_input)
        else:
            await update.message.reply_text("No pude extraer un ingreso válido de tu mensaje. Por favor, intenta de nuevo.")
        return ConversationHandler.END

    async def _process_file_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Processes the uploaded file and generates a budget plan."""
        file_info = context.user_data.get('file_info')
        if file_info:
            file_id = file_info.file_id
            new_file = await context.bot.get_file(file_id)
            file_path = f"/tmp/{file_info.file_name}"
            await new_file.download_to_drive(file_path)

            file_content = ""
            try:
                if file_info.file_name.lower().endswith('.pdf'):
                    try:
                        # Attempt OCR-based extraction first
                        logger.info("Attempting OCR extraction for PDF...")
                        images = convert_from_path(file_path)
                        for image in images:
                            file_content += pytesseract.image_to_string(image, lang='spa') + "\n"
                        logger.info("OCR extraction successful.")
                    except Exception as ocr_error:
                        logger.warning(f"OCR extraction failed: {ocr_error}. Falling back to PyPDF2.")
                        # Fallback to PyPDF2 if OCR fails
                        reader = PdfReader(file_path)
                        for page in reader.pages:
                            file_content += page.extract_text() or ""
                elif file_info.file_name.lower().endswith('.txt'):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()
                else:
                    await update.message.reply_text("Solo se admiten archivos PDF o TXT. Por favor, sube un archivo válido.")
                    return ASK_FOR_INPUT

                if file_content:
                    # PASO 1: Limpiar el output crudo del OCR
                    cleaned_content = self._clean_ocr_text(file_content)
                    
                    # PASO 2: Sanitizar PII del texto ya limpio
                    sanitized_content, replacements = self._sanitize_text(cleaned_content)

                    # Log the sanitization results
                    total_replacements = sum(replacements.values())
                    if total_replacements > 0:
                        log_message = (
                            f"Sanitized PII from document. "
                            f"Replacements: {replacements['nombres']} names, "
                            f"{replacements['numeros_cuenta']} account numbers, "
                            f"{replacements['direcciones']} addresses."
                        )
                        logger.info(log_message)

                    await update.message.reply_text("Procesando tu archivo con Gemini... 🧠")
                    
                    structured_summary = await self._summarize_with_gemini(sanitized_content)
                    context.user_data['financial_json'] = structured_summary  # Almacenamos el JSON para reutilización

                    # Eliminamos el initial_response_message estático; ahora enviamos un resumen breve basado en JSON
                    resumen = structured_summary['resumen']
                    initial_message = (
                        f"¡Análisis completado! 📊\n"
                        f"Saldo Inicial: {resumen['saldo_inicial']:.2f}\n"
                        f"Saldo Final: {resumen['saldo_final']:.2f}\n"
                        f"Total Ingresos: {resumen['total_ingresos']:.2f}\n"
                        f"Total Egresos: {resumen['total_egresos']:.2f}\n\n"
                        f"Elige una opción abajo para insights personalizados."
                    )
                    escaped_message = escape_markdown_v2(initial_message)
                    await update.message.reply_text(escaped_message, parse_mode=ParseMode.MARKDOWN_V2)

                    # Enviamos el menú inline contextual
                    await self._send_contextual_inline_menu(update, context, structured_summary)
                    return ASK_DEEPER_INSIGHT
                else:
                    await update.message.reply_text("El archivo está vacío o no se pudo leer. Por favor, intenta con otro.")
                    return ASK_FOR_INPUT
            except Exception as e:
                logger.error(f"Error processing file: {e}")
                await update.message.reply_text(f"Hubo un error al procesar tu archivo: {e}. Por favor, intenta de nuevo.")
                return ASK_FOR_INPUT
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)
        else:
            await update.message.reply_text("Hubo un problema con la carga de tu archivo. Por favor, intenta de nuevo.")
        return ConversationHandler.END

    async def _send_contextual_inline_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, financial_json: dict):
        """Genera y envía un menú inline dinámico basado en el JSON financiero."""
        buttons = self._get_contextual_buttons(financial_json)
        if not buttons:
            await update.message.reply_text("No se detectaron insights específicos. ¿Quieres un análisis genérico?")
            return

        keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Opciones basadas en tu análisis:", reply_markup=reply_markup)

    def _get_contextual_buttons(self, financial_json: dict) -> list:
        """Devuelve lista de InlineKeyboardButton basada en reglas contextuales del JSON."""
        buttons = []
        transacciones = financial_json.get('transacciones', [])
        resumen = financial_json.get('resumen', {})
        insights = financial_json.get('insights_detectados', {})

        # Botón prioritario: Revisar transacciones
        buttons.append(InlineKeyboardButton("Revisar Transacciones Categorizadas", callback_data='review_transactions'))

        if any(tx['categoria_sugerida'] == 'Préstamo' for tx in transacciones):
            buttons.append(InlineKeyboardButton("Asesor de Deudas", callback_data='debt_advisor'))

        if resumen.get('saldo_final', 0) > 0 and resumen.get('total_ingresos', 0) > resumen.get('total_egresos', 0):
            buttons.append(InlineKeyboardButton("Crear Portafolio de Inversión", callback_data='investment_portfolio'))

        if abs(resumen.get('total_ingresos', 0) - resumen.get('total_egresos', 0)) / max(1, resumen.get('total_ingresos', 0)) < 0.1:
            buttons.append(InlineKeyboardButton("Calcular Fondo de Emergencia", callback_data='emergency_fund'))

        if len(insights.get('pagos_recurrentes', [])) > 1:
            buttons.append(InlineKeyboardButton("Ideas de Ingreso Pasivo", callback_data='passive_income'))

        return buttons

    async def handle_deeper_insight(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handles user's request for deeper insight or proceeds to budget generation."""
        user_response = update.message.text
        original_file_content = context.user_data.get('original_file_content', "")
        structured_summary_data = context.user_data.get('file_summary_data', {})
        
        if "presupuesto" in user_response.lower() or "generar" in user_response.lower():
            await update.message.reply_text("Entendido, generando tu plan de presupuesto con la información del archivo... ⏳")
            await self._generate_budget_plan(update, context, income=20000, user_input=f"file content: {original_file_content}") # Generic income for now, will be improved
            return ConversationHandler.END
        else:
            await update.message.reply_text("Analizando tu pregunta sobre el documento... 🧠")
            
            # Construct a more informed prompt for deeper insight
            summary_text = structured_summary_data.get("Resumen General", "")
            key_points = "\n".join(structured_summary_data.get("Puntos Clave Identificados", []))
            areas_of_interest = "\n".join(structured_summary_data.get("Áreas de Interés/Preocupación", []))

            insight_prompt = (
                f"Eres un experto en finanzas personales y un tutor universitario. El usuario ha proporcionado un documento "
                f"que ya ha sido resumido. Aquí tienes el resumen y los puntos clave:\n\n"
                f"### Resumen del Documento:\n{summary_text}\n\n"
                f"### Puntos Clave Identificados:\n{key_points}\n\n"
                f"### Áreas de Interés/Preocupación:\n{areas_of_interest}\n\n"
                f"El usuario ahora pregunta: '{user_response}'.\n\n"
                f"Basándote en el contexto del documento original (que también tienes disponible) y el resumen, "
                f"responde a la pregunta del usuario de forma detallada y conversacional. "
                f"Si es relevante, puedes hacer referencia a secciones del documento (simuladas, como '[página X]') "
                f"para dar un toque más académico. Al final de tu respuesta, sugiere 1 o 2 preguntas de seguimiento "
                f"que el usuario podría hacer para profundizar aún más en el tema o explorar otras áreas relevantes del documento. "
                f"Formatea tu respuesta usando MarkdownV2."
            )
            
            response_text = await self._generate_content_stream(insight_prompt)
            await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN_V2)
            
            # Extract new suggested questions from Gemini's response if possible, or use a generic prompt
            # For now, I'll keep the generic follow-up question.
            await update.message.reply_text("¿Hay algo más que quieras saber del documento o quieres que genere tu presupuesto?", parse_mode=ParseMode.MARKDOWN_V2)
            return ASK_DEEPER_INSIGHT

    async def _summarize_with_gemini(self, text: str) -> dict:
        """Utiliza Gemini para parsear el texto en un JSON estructurado de datos financieros."""
        prompt = (
            """Eres un parser de datos financieros. Extrae la siguiente información del texto y devuélvela estrictamente en formato JSON.
No agregues texto adicional, explicaciones o Markdown. Solo el JSON válido.

<input>{text}</input>

<output_schema>
{
  "resumen": {
    "saldo_inicial": float,
    "saldo_final": float,
    "total_ingresos": float,
    "total_egresos": float
  },
  "transacciones": [
    {
      "fecha": "YYYY-MM-DD",
      "descripcion": "string",
      "monto": float,
      "tipo": "ingreso|egreso",
      "categoria_sugerida": "Nómina|Comida|Transporte|Suscripciones|Préstamo|Comisiones|Otro"
    }
  ],
  "insights_detectados": {
    "pagos_recurrentes": ["Netflix", "Pago Préstamo Coche"],
    "fuentes_ingreso": ["Nómina Empresa X"],
    "comisiones_bancarias": float
  }
}
</output_schema>

Instrucciones:
- Analiza solo transacciones financieras; ignora encabezados, pies de página o texto no relevante.
- Para 'categoria_sugerida', infiere basándote en descripción (e.g., 'Netflix' -> 'Suscripciones').
- Calcula totals en 'resumen' sumando montos por tipo.
- En 'insights_detectados', identifica recurrentes (mismo descripción >1 vez), fuentes únicas de ingresos, y suma comisiones.
- Si un valor no se detecta, usa 0.0 para floats o [] para listas.
""".replace("{text}", text)
        )
        
        raw_response = await self._generate_content_stream(prompt)
        
        try:
            # Limpiamos el raw_response para quitar ```json y ```
            cleaned_response = re.sub(r'```json\n|```', '', raw_response.strip())
            summary_data = json.loads(cleaned_response)
            logger.info("JSON parseado exitosamente del PDF.")
            return summary_data
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando JSON de Gemini: {e}. Raw: {raw_response}")
            return {
                "resumen": {"saldo_inicial": 0.0, "saldo_final": 0.0, "total_ingresos": 0.0, "total_egresos": 0.0},
                "transacciones": [],
                "insights_detectados": {"pagos_recurrentes": [], "fuentes_ingreso": [], "comisiones_bancarias": 0.0}
            }

    def _sanitize_text(self, text: str) -> tuple[str, dict]:
        """Removes or anonymizes PII from the text and counts replacements."""
        replacements = {}

        # Anonymize names (assuming they are in ALL CAPS and reasonably long)
        # This regex looks for sequences of 10 or more uppercase letters and spaces,
        # which is a heuristic for full names.
        text, count = re.subn(r'\b[A-ZÁÉÍÓÚÑ\s]{10,}\b', '[NOMBRE REMOVIDO]', text)
        replacements['nombres'] = count

        # Anonymize account numbers (long sequences of digits)
        text, count = re.subn(r'\b\d{10,}\b', '[NUMERO_CUENTA REMOVIDO]', text)
        replacements['numeros_cuenta'] = count

        # Anonymize addresses based on common keywords up to a postal code indicator
        # This is a broad-stroke approach and might need refinement.
        text, count = re.subn(r'(URB\.|CALLE|EDF\.|PARROQUIA)[\s\S]*?(Z\.P\.)', '[DIRECCION REMOVIDA]', text, flags=re.IGNORECASE)
        replacements['direcciones'] = count

        return text, replacements

    def _clean_ocr_text(self, text: str) -> str:
        """Cleans raw OCR output by normalizing whitespace and removing non-standard characters."""
        # 1. Colapsa múltiples espacios horizontales y tabs en un solo espacio, pero DEJA LOS SALTOS DE LÍNEA.
        text = re.sub(r'[ \t]+', ' ', text)
        
        # 2. Elimina cualquier carácter que no sea útil. AÑADIMOS \n A LA LISTA DE PERMITIDOS para ser explícitos.
        # Aunque \s incluye \n, ser explícito aquí previene regresiones y aclara la intención.
        text = re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\s\n.,$:€-]', '', text)
        
        return text.strip()

    def _extract_income_from_text(self, text: str) -> float | None:
        """Extracts a numerical income from text, handling various phrases and formats."""
        # Keywords for income
        income_keywords = r"(?:gano|ingreso|salario|sueldo|ganancia|remuneracion|cobro|percibo|mi ingreso es de)"

        # Currency symbols and codes (common ones in Latin America and general)
        currency_symbols = r"(?:\\$|€|£|MXN|USD|COP|CLP|ARS|PEN|BRL|pesos|dolares|euros)"

        # Number pattern: allows for thousands separators (.,) and decimal separators (.,)
        # Example: 1.234.567,89 or 1,234,567.89 or 1234567.89 or 1234567,89
        number_pattern = r"(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"

        # Regex to find income statements
        # It tries to capture:
        # 1. Keyword followed by number (with optional currency before/after)
        # 2. Currency followed by number
        # 3. Just a number if it's a very simple statement (less reliable, but as a fallback)
        # The order of patterns in the regex matters for prioritization
        patterns = [
            # e.g., "gano $20,000.50", "mi ingreso es de 20.000 MXN"
            rf"{income_keywords}\s*(?:{currency_symbols}\s*)?{number_pattern}(?:\s*{currency_symbols})?",
            # e.g., "$20,000.50", "MXN 20.000"
            rf"{currency_symbols}\s*{number_pattern}",
            # e.g., "20000.50" (as a last resort, could be ambiguous)
            rf"\b{number_pattern}\b"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Extract the number string, which is always in the first capturing group
                number_str = match.group(1)

                # Clean the number string for float conversion
                # Remove thousands separators (commas or dots, depending on decimal)
                # Determine decimal separator: if both . and , exist, assume last one is decimal
                if ',' in number_str and '.' in number_str:
                    if number_str.rfind(',') > number_str.rfind('.'): # e.g., 1.234,56
                        number_str = number_str.replace('.', '').replace(',', '.')
                    else: # e.g., 1,234.56
                        number_str = number_str.replace(',', '')
                else: # Only one or no separator
                    number_str = number_str.replace(',', '.') # Default to dot as decimal

                try:
                    return float(number_str)
                except ValueError:
                    logger.warning(f"Could not convert '{number_str}' to float after cleaning.")
                    continue # Try next pattern if conversion fails for this match
        return None

    async def _generate_budget_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE, income: float, user_input: str) -> None:
        """Generates a budget plan using Gemini."""
        prompt = (
            f"Eres un experto en finanzas personales y un tutor universitario. Genera un plan de presupuesto detallado para un individuo con un ingreso mensual de {income} MXN. "
            "El plan debe incluir:\n"
            "- Asignación de ingresos a categorías (esenciales, ahorros, discrecionales) con porcentajes sugeridos.\n"
            "- Un porcentaje de ahorro recomendado.\n"
            "- Áreas clave para reducir gastos.\n"
        )
            