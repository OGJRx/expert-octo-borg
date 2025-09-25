import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, CallbackQueryHandler, PicklePersistence
)
from config import Config
from geminiborg import GeminiBorg

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BorgotronBot:
    """The main class for the Telegram bot, using a stateless event-driven model."""
    def __init__(self):
        """Initializes the bot with persistence and global handlers."""
        self.config = Config()
        self.gemini_borg = GeminiBorg()
        persistence = PicklePersistence(filepath="borg_persistence")
        self.application = (
            Application.builder()
            .token(self.config.TELEGRAM_TOKEN)
            .persistence(persistence)
            .build()
        )
        self._register_handlers()

    def _register_handlers(self):
        """Registers simple, global handlers for commands, documents, and callbacks."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("ayuda", self.ayuda_command))
        self.application.add_handler(CommandHandler("presupuesto", self.presupuesto_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.application.add_handler(CallbackQueryHandler(self.handle_inline_callback))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = """¡Bienvenido! Soy BORG, tu copiloto financiero. Usa /presupuesto para empezar."""
        await update.message.reply_text(message)

    async def ayuda_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = """Usa /presupuesto y sube un documento PDF o TXT para que analice tus finanzas."""
        await update.message.reply_text(message)

    async def presupuesto_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self.gemini_borg.presupuesto_start(update, context)

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data.clear()
        await update.message.reply_text("Acción cancelada y datos de sesión borrados.")

    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        document = update.message.document
        if not document or not (document.file_name.lower().endswith('.pdf') or document.file_name.lower().endswith('.txt')):
            await update.message.reply_text("Formato no válido. Por favor, sube un archivo PDF o TXT.")
            return

        await update.message.reply_text("Procesando tu archivo... Esto puede tardar un momento.")

        # Reutilizamos la lógica de geminiborg para mantener el código limpio
        structured_summary = await self.gemini_borg.process_file_from_update(update)

        if 'error' in structured_summary:
            await update.message.reply_text(f"No pude procesar el documento. Razón: {structured_summary['error']}")
            return

        context.user_data['financial_json'] = structured_summary

        resumen = structured_summary.get('resumen', {})
        final_message = (
            "Análisis Completado.\n\n"
            f"Saldo Inicial: {resumen.get('saldo_inicial', 0):.2f}\n"
            f"Saldo Final: {resumen.get('saldo_final', 0):.2f}\n"
            f"Total Ingresos: {resumen.get('total_ingresos', 0):.2f}\n"
            f"Total Egresos: {resumen.get('total_egresos', 0):.2f}\n\n"
            "Panel de Control Principal:"
        )
        buttons = self.gemini_borg._get_contextual_buttons(structured_summary)
        reply_markup = InlineKeyboardMarkup([buttons[i:i+2] for i in range(0, len(buttons), 2)])
        await update.message.reply_text(final_message, reply_markup=reply_markup)

    async def handle_inline_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        financial_json = context.user_data.get('financial_json')

        if not financial_json:
            await query.edit_message_text("Tus datos de sesión han expirado. Por favor, sube el documento de nuevo con /presupuesto.")
            return

        # Lógica de acciones
        if data == 'emergency_fund':
            await self._show_emergency_fund(query, context)
        elif data == 'debt_advisor':
            await self._show_debt_advisor(query, context)
        elif data == 'investment_portfolio':
            await query.edit_message_text("El módulo de Inversión está en desarrollo.", reply_markup=None)
        elif data == 'review_transactions':
            await self.show_transactions_for_review(query, context)
        elif data.startswith('correct_'):
            tx_index = int(data.split('_')[1])
            await self.show_category_options(query, context, tx_index)
        elif data.startswith('setcat_'):
            _, tx_index_str, new_category = data.split('_')
            await self.update_transaction_category(query, context, int(tx_index_str), new_category)
        elif data == 'main_menu':
            await self.show_main_menu(query, context)
        else:
            await query.edit_message_text("Opción no reconocida o en desarrollo.")

    async def _show_debt_advisor(self, query: Update, context: ContextTypes.DEFAULT_TYPE):
        financial_json = context.user_data.get('financial_json', {})
        await query.edit_message_text("Generando plan de deudas personalizado...")
        debt_amount = sum(tx['monto'] for tx in financial_json.get('transacciones', []) if tx.get('categoria_sugerida') == 'Préstamo')
        prompt = f"Eres un asesor financiero experto. Crea un plan de pago de deudas detallado y accionable para un total de {debt_amount:.2f} MXN. Usa estrategias como bola de nieve y avalancha."
        response_text = await self.gemini_borg.generate_text_response(prompt)
        await query.edit_message_text(text=response_text, reply_markup=None)

    async def _show_emergency_fund(self, query: Update, context: ContextTypes.DEFAULT_TYPE):
        financial_json = context.user_data.get('financial_json', {})
        await query.edit_message_text("Calculando fondo de emergencia...")
        total_egresos = financial_json.get('resumen', {}).get('total_egresos', 0)
        prompt = f"Calcula un fondo de emergencia para gastos mensuales de {total_egresos:.2f} MXN, mostrando tablas para 3, 6 y 9 meses."
        response_text = await self.gemini_borg.generate_text_response(prompt) # Necesitamos una función que no fuerce JSON
        await query.edit_message_text(text=response_text, reply_markup=None) # Quitamos los botones después de la acción

    async def show_transactions_for_review(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Displays a list of transactions for the user to review and correct."""
        financial_json = context.user_data.get('financial_json', {})
        transactions = financial_json.get('transacciones', [])
        buttons = []
        for i, tx in enumerate(transactions):
            desc = tx.get('descripcion', 'N/A')[:20]
            cat = tx.get('categoria_sugerida', 'N/A')
            buttons.append([InlineKeyboardButton(f"{desc}... -> {cat}", callback_data=f'correct_{i}')])
        buttons.append([InlineKeyboardButton("<< Volver al Menú", callback_data='main_menu')])
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text="Toca una transacción para corregir su categoría:", reply_markup=reply_markup)

    async def show_main_menu(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Displays the main control panel."""
        financial_json = context.user_data.get('financial_json', {})
        buttons = self.gemini_borg._get_contextual_buttons(financial_json)
        reply_markup = InlineKeyboardMarkup([buttons[i:i+2] for i in range(0, len(buttons), 2)])
        await query.edit_message_text("Panel de Control Principal:", reply_markup=reply_markup)

    async def show_category_options(self, query, context: ContextTypes.DEFAULT_TYPE, tx_index: int):
        """Shows a menu of categories for the user to choose from for a specific transaction."""
        financial_json = context.user_data.get('financial_json', {})
        categories = ["Nómina", "Comida", "Transporte", "Suscripciones", "Préstamo", "Vivienda", "Ocio", "Otro"]
        buttons = [InlineKeyboardButton(cat, callback_data=f'setcat_{tx_index}_{cat}') for cat in categories]
        keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        keyboard.append([InlineKeyboardButton("<< Volver a Transacciones", callback_data='review_transactions')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        description = financial_json['transacciones'][tx_index]['descripcion']
        await query.edit_message_text(f"Elige la categoría para:\n{description}", reply_markup=reply_markup)

    async def update_transaction_category(self, query, context: ContextTypes.DEFAULT_TYPE, tx_index: int, new_category: str):
        """Updates the category of a specific transaction and refreshes the review list."""
        financial_json = context.user_data.get('financial_json', {})
        financial_json['transacciones'][tx_index]['categoria_sugerida'] = new_category
        context.user_data['financial_json'] = financial_json
        logger.info(f"User updated category for tx index {tx_index} to '{new_category}'.")
        await query.answer(f"Categoría actualizada a {new_category}")
        await self.show_transactions_for_review(query, context)

    def run(self):
        logger.info("Starting bot...")
        self.application.run_polling()
        logger.info("Bot has stopped.")

if __name__ == '__main__':
    bot = BorgotronBot()
    bot.run()