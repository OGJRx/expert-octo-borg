import json
import logging
import asyncio
import google.generativeai as genai
from telegram import Update
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
import pytesseract
from config import Config
import re
import os

logger = logging.getLogger(__name__)

class GeminiBorg:
    def __init__(self):
        self.config = Config()
        self.model_name = 'gemini-1.5-flash'
        self.setup_ai_client()
        self.model = genai.GenerativeModel(self.model_name)

    def setup_ai_client(self):
        genai.configure(api_key=self.config.GOOGLE_AI_KEY)

    async def _generate_content_robust(self, prompt: str, is_json: bool = True) -> str:
        generation_config = genai.types.GenerationConfig(
            temperature=0.2,
            max_output_tokens=4096,
            response_mime_type="application/json" if is_json else "text/plain"
        )
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        try:
            response = await self.model.generate_content_async(
                contents=[prompt],
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            return response.text
        except Exception as e:
            logger.error(f"Error generating content with Gemini: {e}", exc_info=True)
            return '{"error": "Error en la API de Gemini."}' if is_json else "Error en la API de Gemini."

    async def presupuesto_start(self, update: Update, context) -> None:
        await update.message.reply_text("Para comenzar, sube tu estado de cuenta en formato PDF o TXT.")

    async def process_file_from_update(self, update: Update) -> dict:
        document = update.message.document
        new_file = await update.message.effective_attachment.get_file()
        file_path = f"/tmp/{document.file_id}_{document.file_name}"
        await new_file.download_to_drive(file_path)
        try:
            file_content = ""
            if document.file_name.lower().endswith('.pdf'):
                images = convert_from_path(file_path)
                for image in images:
                    file_content += pytesseract.image_to_string(image, lang='spa')
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = f.read()

            if not file_content.strip():
                return {"error": "El archivo está vacío."}
            cleaned_content = self._clean_ocr_text(file_content)
            return await self._summarize_with_gemini(cleaned_content)
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

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
        raw_response = await self._generate_content_robust(prompt, is_json=True)
        try:
            return json.loads(re.sub(r'```json\n|```', '', raw_response.strip()))
        except (json.JSONDecodeError, TypeError):
            return {"error": "La IA no devolvió un JSON válido."}

    async def generate_text_response(self, prompt: str) -> str:
        return await self._generate_content_robust(prompt, is_json=False)

    def _clean_ocr_text(self, text: str) -> str:
        return re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ\n\s.,$:€-]', '', re.sub(r'[ \t]+', ' ', text)).strip()

    def get_available_actions(self, financial_json: dict) -> dict:
        actions = {}
        transacciones = financial_json.get('transacciones', [])
        resumen = financial_json.get('resumen', {})
        if any(tx.get('categoria_sugerida') == 'Préstamo' for tx in transacciones):
            actions['plan_deudas'] = "He detectado pagos de préstamos. Usa `/plan_deudas` para crear una estrategia de pago."
        if resumen.get('total_egresos', 0) > resumen.get('total_ingresos', 0) * 0.9 and resumen.get('total_ingresos', 0) > 0:
            actions['fondo_emergencia'] = "Tus gastos son altos. Usa `/fondo_emergencia` para calcular tu red de seguridad."
        if resumen.get('saldo_final', 0) > 5000:
            actions['plan_inversion'] = "Tienes un excedente. Usa `/plan_inversion` para explorar opciones."
        return actions