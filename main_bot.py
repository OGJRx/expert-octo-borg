import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
from config import Config
from geminiborg import GeminiBorg, ASK_FOR_INPUT, ASK_DEEPER_INSIGHT

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BorgotronBot:
    """The main class for the Telegram bot, handling command routing and conversation state."""
    def __init__(self):
        """Initializes the bot, its handlers, and the underlying GeminiBorg logic."""
        self.config = Config()
        self.gemini_borg = GeminiBorg()
        self.application = Application.builder().token(self.config.TELEGRAM_TOKEN).build()
        self._register_handlers()

    def _register_handlers(self):
        """Registers all command, message, and callback handlers for the bot."""
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("presupuesto", self.gemini_borg.presupuesto_start)],
            states={
                ASK_FOR_INPUT: [MessageHandler(filters.Document.ALL, self.gemini_borg.handle_file_input)],
                ASK_DEEPER_INSIGHT: [CallbackQueryHandler(self.handle_inline_callback)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        self.application.add_handler(conv_handler)
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("ayuda", self.ayuda_command))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the /start command with a welcome message and instructions."""
        message = """¡Bienvenido! Soy BORG, tu copiloto financiero personal.

¿Cómo empezar?
1. Usa el comando /presupuesto.
2. Sube tu estado de cuenta en formato PDF o TXT.
3. ¡Listo! Analizaré tus finanzas y te presentaré un dashboard interactivo.

Para cancelar cualquier proceso, usa /cancel.
Para volver a ver este mensaje, usa /ayuda."""
        await update.message.reply_text(message)

    async def ayuda_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles the /ayuda command by showing the start message."""
        await self.start_command(update, context)

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels the current conversation."""
        await update.message.reply_text('Conversación cancelada.', reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    async def handle_inline_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles all callbacks from the inline keyboard."""
        query = update.callback_query
        await query.answer()
        data = query.data
        financial_json = context.user_data.get('financial_json', {})

        if data == 'review_transactions':
            await self.show_transactions_for_review(query, financial_json)
        elif data.startswith('correct_'):
            tx_index = int(data.split('_')[1])
            await self.show_category_options(query, financial_json, tx_index)
        elif data.startswith('setcat_'):
            _, tx_index_str, new_category = data.split('_')
            await self.update_transaction_category(query, context, financial_json, int(tx_index_str), new_category)
        elif data == 'main_menu':
            await self.gemini_borg._send_contextual_inline_menu(update, context, financial_json)
        elif data == 'debt_advisor':
            await query.edit_message_text("Generando plan de deudas personalizado...")
            debt_amount = sum(tx['monto'] for tx in financial_json.get('transacciones', []) if tx.get('categoria_sugerida') == 'Préstamo')
            prompt = f"Eres un asesor financiero experto. Crea un plan de pago de deudas detallado y accionable para un total de {debt_amount:.2f} MXN. Usa estrategias como bola de nieve y avalancha."
            response = await self.gemini_borg._generate_content_robust(prompt)
            await query.edit_message_text(text=response, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("<< Volver", callback_data='main_menu')]]))

    async def show_transactions_for_review(self, query, financial_json):
        """Displays a list of transactions for the user to review and correct."""
        transactions = financial_json.get('transacciones', [])
        buttons = []
        for i, tx in enumerate(transactions):
            desc = tx.get('descripcion', 'N/A')[:20]
            cat = tx.get('categoria_sugerida', 'N/A')
            buttons.append([InlineKeyboardButton(f"{desc}... -> {cat}", callback_data=f'correct_{i}')])
        buttons.append([InlineKeyboardButton("<< Volver", callback_data='main_menu')])
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text="Toca una transacción para corregir su categoría:", reply_markup=reply_markup)

    async def show_category_options(self, query, financial_json, tx_index):
        """Shows a menu of categories for the user to choose from."""
        categories = ["Nómina", "Comida", "Transporte", "Suscripciones", "Préstamo", "Vivienda", "Ocio", "Otro"]
        buttons = [InlineKeyboardButton(cat, callback_data=f'setcat_{tx_index}_{cat}') for cat in categories]
        keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
        keyboard.append([InlineKeyboardButton("<< Volver", callback_data='review_transactions')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        description = financial_json['transacciones'][tx_index]['descripcion']
        await query.edit_message_text(f"Elige la categoría para:\n{description}", reply_markup=reply_markup)

    async def update_transaction_category(self, query, context, financial_json, tx_index, new_category):
        """Updates the category of a specific transaction and refreshes the review list."""
        financial_json['transacciones'][tx_index]['categoria_sugerida'] = new_category
        context.user_data['financial_json'] = financial_json
        logger.info(f"User updated category for tx index {tx_index} to '{new_category}'.")
        await query.answer(f"Categoría actualizada a {new_category}")
        await self.show_transactions_for_review(query, financial_json)

    def run(self):
        """Starts the bot's polling loop."""
        logger.info("Starting bot...")
        self.application.run_polling()
        logger.info("Bot has stopped.")

if __name__ == '__main__':
    bot = BorgotronBot()
    bot.run()