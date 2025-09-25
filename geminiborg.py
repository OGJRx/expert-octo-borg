import json
import logging
import asyncio
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import pytesseract
from config import Config
import re
import os

logger = logging.getLogger(__name__)

class GeminiBorg:
    """Handles all the core logic for the financial analysis bot."""
    def __init__(self):
        """Initializes the GeminiBorg, setting up AI configuration."""
        self.config = Config()
        self.model_name = 'gemini-1.5-flash'
        self.setup_ai_client()
        self.model = genai.GenerativeModel(self.model_name)

    def setup_ai_client(self):
        """Configures the Google Generative AI client with the API key."""
        genai.configure(api_key=self.config.GOOGLE_AI_KEY)

    async def _generate_content_robust(self, prompt: str, retries: int = 3, delay: int = 5, is_json: bool = True) -> str:
        """
        Generates content from the Gemini API with retry logic, supporting both JSON and text.
        """
        generation_config = genai.types.GenerationConfig(
            temperature=0.2,
            max_output_tokens=8192,
            response_mime_type="application/json" if is_json else "text/plain"
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
                    error_message = '{"error": "Hubo un error al generar la respuesta con Gemini."}' if is_json else "Hubo un error al generar la respuesta."
                    return error_message
        return '{"error": "La API de Gemini no devolvió contenido."}' if is_json else "La API no devolvió contenido."

    async def presupuesto_start(self, update: Update, context) -> None:
        """Asks the user to upload a file."""
        message = "Para comenzar, sube tu estado de cuenta en formato PDF o TXT."
        await update.message.reply_text(message)

    async def process_file_from_update(self, update: Update) -> dict:
        """
        Processes an uploaded file from a Telegram update, returning a structured summary.
        """
        document = update.message.document
        new_file = await update.message.effective_attachment.get_file()
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
                return {"error": "El archivo está vacío o no se pudo leer."}

            cleaned_content = self._clean_ocr_text(file_content)
            return await self._summarize_with_gemini(cleaned_content)
            
        except Exception as e:
            logger.error(f"Error processing file: {e}", exc_info=True)
            return {"error": "Hubo un error crítico al procesar tu archivo."}
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    def _get_contextual_buttons(self, financial_json: dict) -> list:
        """
        Generates a list of contextual buttons based on the financial summary.
        """
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
        """
        Sends the text content to the Gemini API for financial summarization.
        """
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
        raw_response = await self._generate_content_robust(prompt, is_json=True)
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

    async def generate_text_response(self, prompt: str) -> str:
        """
        Generates a plain text response from the Gemini API.
        """
        return await self._generate_content_robust(prompt, is_json=False)

    def _clean_ocr_text(self, text: str) -> str:
        """
        Cleans the text extracted from OCR to improve processing.
        """
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\n\s.,$:€-]', '', text)
        return text.strip()