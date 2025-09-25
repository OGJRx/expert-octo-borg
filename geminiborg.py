import json
import logging
import asyncio
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import pytesseract
from config import Config
import re
import os

logger = logging.getLogger(__name__)

# Conversation states
ASK_FOR_INPUT, ASK_DEEPER_INSIGHT = range(2)

class GeminiBorg:
    def __init__(self):
        self.config = Config()
        self.model_name = 'gemini-1.5-flash'
        self.setup_ai_client()
        self.model = genai.GenerativeModel(self.model_name)

    def setup_ai_client(self):
        genai.configure(api_key=self.config.GOOGLE_AI_KEY)

    async def _generate_content_robust(self, prompt: str, retries: int = 3, delay: int = 5) -> str:
        generation_config = genai.types.GenerationConfig(
            temperature=0.2,
            max_output_tokens=8192,
            response_mime_type="application/json"
        )
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        for attempt in range(retries):
            try:
                response = await self.model.generate_content_async(
                    contents=[prompt],
                    generation_config=generation_config,
                    safety_settings=safety_settings
                )
                return response.text
            except Exception as e:
                logger.error(f"Attempt {attempt + 1}: Error generating content with Gemini: {e}", exc_info=True)
                if attempt < retries - 1:
                    await asyncio.sleep(delay)
                else:
                    return '{"error": "Hubo un error al generar la respuesta con Gemini."}'
        return '{"error": "La API de Gemini no devolvió contenido."}'

    async def presupuesto_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        raw_message = """👋 ¡Hola! Soy *BORG*, tu **copiloto financiero** 🤖.

Sube un estado de cuenta o un documento financiero en formato `PDF` o `TXT`.

Lo analizaré para darte un resumen inteligente, detectar patrones y ofrecerte acciones personalizadas. Tu privacidad es mi prioridad.

¿Listo para tomar el control? ✨"""
        escaped_message = escape_markdown(raw_message, version=2)
        await update.message.reply_text(escaped_message, parse_mode=ParseMode.MARKDOWN_V2)
        return ASK_FOR_INPUT

    async def handle_file_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        document = update.message.document
        if not document or not (document.file_name.lower().endswith('.pdf') or document.file_name.lower().endswith('.txt')):
            await update.message.reply_text("Por favor, sube un archivo en formato PDF o TXT.")
            return ASK_FOR_INPUT

        await update.message.reply_text("Procesando tu archivo... Esto puede tardar un momento. 🧠")
        
        new_file = await context.bot.get_file(document.file_id)
        file_path = f"/tmp/{document.file_id}_{document.file_name}"
        await new_file.download_to_drive(file_path)

        file_content = ""
        try:
            if document.file_name.lower().endswith('.pdf'):
                images = convert_from_path(file_path)
                for image in images:
                    file_content += pytesseract.image_to_string(image, lang='spa')
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()

            if not file_content.strip():
                await update.message.reply_text("El archivo está vacío o no se pudo leer.")
                return ASK_FOR_INPUT

            cleaned_content = self._clean_ocr_text(file_content)
            structured_summary = await self._summarize_with_gemini(cleaned_content)
            
            if 'error' in structured_summary:
                await update.message.reply_text(f"No pude procesar el documento. Razón: {structured_summary['error']}")
                return ConversationHandler.END

            context.user_data['financial_json'] = structured_summary

            resumen = structured_summary.get('resumen', {})
            final_message = (
                f"*Análisis Completado* 📊\n\n"
                f"Saldo Inicial: `{resumen.get('saldo_inicial', 0):.2f}`\n"
                f"Saldo Final: `{resumen.get('saldo_final', 0):.2f}`\n"
                f"Total Ingresos: `{resumen.get('total_ingresos', 0):.2f}`\n"
                f"Total Egresos: `{resumen.get('total_egresos', 0):.2f}`\n\n"
                f"*Panel de Control Principal:*"
            )

            buttons = self._get_contextual_buttons(structured_summary)
            keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(final_message, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=reply_markup)
            
            return ASK_DEEPER_INSIGHT

        except Exception as e:
            logger.error(f"Error processing file: {e}", exc_info=True)
            await update.message.reply_text("Hubo un error crítico al procesar tu archivo.")
            return ConversationHandler.END
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    async def _send_contextual_inline_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, financial_json: dict):
        buttons = self._get_contextual_buttons(financial_json)
        keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.edit_message_text("*Panel de Control Principal:*", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text("*Panel de Control Principal:*", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

    def _get_contextual_buttons(self, financial_json: dict) -> list:
        buttons = []
        transacciones = financial_json.get('transacciones', [])
        resumen = financial_json.get('resumen', {})

        buttons.append(InlineKeyboardButton("🔍 Revisar Transacciones", callback_data='review_transactions'))

        if any(tx.get('categoria_sugerida') == 'Préstamo' for tx in transacciones):
            buttons.append(InlineKeyboardButton("💳 Plan Deudas", callback_data='debt_advisor'))

        if resumen.get('saldo_final', 0) > 5000:
            buttons.append(InlineKeyboardButton("📈 Plan Inversión", callback_data='investment_portfolio'))

        if resumen.get('total_egresos', 0) > resumen.get('total_ingresos', 0) * 0.9:
            buttons.append(InlineKeyboardButton("🆘 Fondo Emergencia", callback_data='emergency_fund'))

        return buttons

    async def _summarize_with_gemini(self, text: str) -> dict:
        prompt = f"""
Eres un experto analista financiero. Analiza el siguiente texto de un estado de cuenta y extráelo a un formato JSON.
Tu respuesta DEBE ser únicamente el objeto JSON, sin explicaciones ni markdown.

<input_text>
{text}
</input_text>

<output_schema>
{{
  "resumen": {{ "saldo_inicial": float, "saldo_final": float, "total_ingresos": float, "total_egresos": float }},
  "transacciones": [ {{ "fecha": "YYYY-MM-DD", "descripcion": "string", "monto": float, "tipo": "ingreso|egreso", "categoria_sugerida": "Nómina|Comida|Transporte|Suscripciones|Préstamo|Comisiones|Vivienda|Ocio|Otro" }} ],
  "insights_detectados": {{ "pagos_recurrentes": ["string"], "fuentes_ingreso": ["string"], "comisiones_bancarias": float }}
}}
</output_schema>
"""
        raw_response = await self._generate_content_robust(prompt)
        try:
            cleaned_response = re.sub(r'```json\n|```', '', raw_response.strip())
            data = json.loads(cleaned_response)
            if 'error' in data:
                logger.error(f"Received error from Gemini: {data['error']}")
                return {"error": data['error']}
            return data
        except (json.JSONDecodeError, TypeError):
            logger.error(f"Failed to decode JSON from Gemini. Raw response: {raw_response}")
            return {"error": "La respuesta de la IA no fue un JSON válido."}

    def _clean_ocr_text(self, text: str) -> str:
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\n\s.,$:€-]', '', text)
        return text.strip()