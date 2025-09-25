import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, PicklePersistence
from config import Config
from geminiborg import GeminiBorg

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class BorgotronBot:
    def __init__(self):
        self.config = Config()
        self.gemini_borg = GeminiBorg()
        persistence = PicklePersistence(filepath="borg_persistence")
        self.application = Application.builder().token(self.config.TELEGRAM_TOKEN).persistence(persistence).build()
        self._register_handlers()

    def _register_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("presupuesto", self.presupuesto_command))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.application.add_handler(CommandHandler("plan_deudas", self.debt_advisor_command))
        self.application.add_handler(CommandHandler("fondo_emergencia", self.emergency_fund_command))
        self.application.add_handler(CommandHandler("plan_inversion", self.investment_command))
        self.application.add_handler(CommandHandler("generar_oportunidad", self.opportunity_command))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("¡Bienvenido! Soy BORG. Usa /presupuesto y sube un documento para empezar.")

    async def presupuesto_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.gemini_borg.presupuesto_start(update, context)

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Procesando tu archivo...")
        structured_summary = await self.gemini_borg.process_file_from_update(update)
        if 'error' in structured_summary:
            await update.message.reply_text(f"Error: {structured_summary['error']}")
            return
        context.user_data['financial_json'] = structured_summary
        resumen = structured_summary.get('resumen', {})
        summary_message = (f"Análisis Completado.\n\n"
                           f"Saldo Inicial: {resumen.get('saldo_inicial', 0):.2f}\n"
                           f"Saldo Final: {resumen.get('saldo_final', 0):.2f}\n"
                           f"Total Ingresos: {resumen.get('total_ingresos', 0):.2f}\n"
                           f"Total Egresos: {resumen.get('total_egresos', 0):.2f}")
        await update.message.reply_text(summary_message)
        actions = self.gemini_borg.get_available_actions(structured_summary)
        if actions:
            action_message = "Acciones Disponibles:\n" + "\n".join(f"• {desc}" for desc in actions.values())
            await update.message.reply_text(action_message)

    async def debt_advisor_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        financial_json = context.user_data.get('financial_json')
        if not financial_json:
            await update.message.reply_text("Primero sube un documento con /presupuesto.")
            return
        await update.message.reply_text("Generando plan de deudas...")
        debt_amount = sum(tx['monto'] for tx in financial_json.get('transacciones', []) if tx.get('categoria_sugerida') == 'Préstamo')
        prompt = f"Crea un plan de pago de deudas para un total de {debt_amount:.2f} MXN."
        response_text = await self.gemini_borg.generate_text_response(prompt)
        await update.message.reply_text(response_text)

    async def emergency_fund_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        financial_json = context.user_data.get('financial_json')
        if not financial_json:
            await update.message.reply_text("Primero sube un documento con /presupuesto.")
            return
        await update.message.reply_text("Calculando fondo de emergencia...")
        total_egresos = financial_json.get('resumen', {}).get('total_egresos', 0)
        prompt = f"Calcula un fondo de emergencia para gastos mensuales de {total_egresos:.2f} MXN."
        response_text = await self.gemini_borg.generate_text_response(prompt)
        await update.message.reply_text(response_text)

    async def investment_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Funcionalidad de inversión en construcción.")

    async def opportunity_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if 'financial_json' not in context.user_data:
            await update.message.reply_text("Primero sube un documento con /presupuesto.")
            return
        await update.message.reply_text("Activando Modo Bestia... Generando plan de acción.")
        prompt = """Eres un coach de 'grind' financiero, sin filtros, modo bestia. Tu único objetivo es ayudar a alguien a generar $20 USD en las próximas 4 horas, empezando desde cero. Crea un plan de acción hora por hora, ultra-detallado y agresivo. Incluye: 1. Mentalidad: Una frase inicial para activar el modo bestia. 2. Hora 1: Identificación de micro-habilidades vendibles (ej: eliminar fondos de 10 fotos, transcribir 1 min de audio, diseñar un post simple en Canva). Búsqueda de plataformas (Fiverr, Upwork, foros de Reddit). Creación de una oferta irresistible. 3. Hora 2: Prospección agresiva. Enviar 50 mensajes/ofertas. Incluye una plantilla de mensaje directo y sin rodeos. 4. Hora 3: Ejecución del primer micro-trabajo. Enfoque láser en la entrega. 4. Hora 4: Entrega, cobro y búsqueda del siguiente cliente. El tono debe ser directo, motivador y sin excusas. Cero descanso hasta ganar."""
        response_text = await self.gemini_borg.generate_text_response(prompt)
        await update.message.reply_text(response_text)

    def run(self):
        logger.info("Starting bot...")
        self.application.run_polling()
        logger.info("Bot has stopped.")

if __name__ == '__main__':
    bot = BorgotronBot()
    bot.run()