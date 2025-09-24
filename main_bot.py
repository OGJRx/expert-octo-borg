import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'

import logging
import google.generativeai as genai
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode
from config import Config
from geminiborg import GeminiBorg, ASK_FOR_INPUT, HANDLE_FILE, HANDLE_INCOME, ASK_DEEPER_INSIGHT, escape_markdown_v2 # Import the GeminiBorg class, conversation states, and markdown escape utility

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BorgotronBot:
    def __init__(self):
        self.config = Config()
        self.gemini_borg = GeminiBorg()
        self.setup_ai()

        # Crear la aplicación una vez y reutilizarla
        self.application = Application.builder().token(self.config.TELEGRAM_TOKEN).build()
        self._register_handlers()

    def setup_ai(self):
        """Configurar conexión con Google AI"""
        logger.info("Google AI configured via GeminiBorg.")

    def _register_handlers(self):
        """Registra todos los manejadores de comandos y conversaciones."""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("ayuda", self.ayuda_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel))
        self.application.add_handler(CallbackQueryHandler(self.handle_inline_callback))

        presupuesto_handler = ConversationHandler(
            entry_points=[CommandHandler("presupuesto", self.gemini_borg.presupuesto_start)],
            states={
                ASK_FOR_INPUT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.gemini_borg.handle_message_input),
                    MessageHandler(filters.Document.ALL, self.gemini_borg.handle_message_input),
                    CommandHandler("skip", self.gemini_borg.skip_input),
                ],
                ASK_DEEPER_INSIGHT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.gemini_borg.handle_deeper_insight),
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        self.application.add_handler(presupuesto_handler)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start - Confirmación del sistema y lista de comandos"""
        # Usamos código en línea (`) para los comandos y el estado.
        full_message = """🟢 *SISTEMA BORG ACTIVO* 🚀
`Conectado a Google AI`
*Estado:* Operativo

📚 *Guía Rápida de Comandos*:
• `/start` - _Verifica el estado del bot._
• `/ayuda` - _Obtén información detallada._
• `/presupuesto` - _Inicia un plan financiero._
• `/cancel` - _Finaliza cualquier conversación._
"""
        # No es necesario escapar el mensaje, ya que está formateado correctamente.
        await update.message.reply_text(full_message, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"User {update.effective_user.id} started the bot.")
    
    async def ayuda_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /ayuda - Asistente IA dinámico"""
        message = (
            "🤖 *¡Hola! Soy BORG, tu asistente financiero personal\\!* 🤖\n\n"
            "Estoy aquí para ayudarte a gestionar tus finanzas con la potencia de la IA de Google Gemini\\. Aquí tienes una guía de mis comandos:\n\n"
            "📚 *Comandos Disponibles*:\n"
            "• `/start` \\- _Inicia una nueva sesión o verifica el estado actual del bot y obtén una guía rápida de comandos\\._\n"
            "• `/ayuda` \\- _Muestra este mensaje de ayuda detallado con todos los comandos y su uso\\._\n"
            "• `/presupuesto` \\- _Activa el modo de creación de presupuesto\\. Te guiaré paso a paso para generar un plan financiero personalizado\\._\n"
            "• `/cancel` \\- _Cancela cualquier operación o conversación en curso\\. Útil si necesitas empezar de nuevo o has terminado una tarea\\._\n\n"
            "✨ *Consejo*: Siempre puedes usar `/cancel` si te sientes perdido o quieres reiniciar\\."
        )
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"User {update.effective_user.id} requested help.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels and ends the conversation."""
        await update.message.reply_text(
            'Conversación cancelada. ¡Hasta luego!',
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {update.effective_user.id} cancelled the conversation.")
        return ConversationHandler.END

    async def handle_inline_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        financial_json = context.user_data.get('financial_json', {})

        if data == 'review_transactions':
            transactions = financial_json.get('transacciones', [])
            if not transactions:
                await query.edit_message_text(text="No se encontraron transacciones para revisar.")
                return

            message_text = "Toca una transacción para corregir su categoría:\n"
            buttons = []
            for i, tx in enumerate(transactions):
                buttons.append([
                    InlineKeyboardButton(
                        f"{tx['descripcion']} ({tx['monto']}) -> {tx['categoria_sugerida']}",
                        callback_data=f'correct_{i}'
                    )
                ])
            buttons.append([InlineKeyboardButton("<< Volver al Menú", callback_data='main_menu')])
            reply_markup = InlineKeyboardMarkup(buttons)
            await query.edit_message_text(text=message_text, reply_markup=reply_markup)
            return

        elif data.startswith('correct_'):
            tx_index = int(data.split('_')[1])
            transaction = financial_json['transacciones'][tx_index]

            categories = ["Nómina", "Comida", "Transporte", "Suscripciones", "Préstamo", "Comisiones", "Otro"]
            buttons = [InlineKeyboardButton(cat, callback_data=f'setcat_{tx_index}_{cat}') for cat in categories]

            keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
            keyboard.append([InlineKeyboardButton("<< Volver", callback_data='review_transactions')])

            reply_markup = InlineKeyboardMarkup(keyboard)
            # Escapamos solo la descripción que viene del usuario/documento
            escaped_description = escape_markdown_v2(transaction['descripcion'])
            await query.edit_message_text(
                text=f"Elige la categoría para:\n*{escaped_description}*",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return

        elif data.startswith('setcat_'):
            _, tx_index_str, new_category = data.split('_')
            tx_index = int(tx_index_str)

            original_category = financial_json['transacciones'][tx_index]['categoria_sugerida']
            financial_json['transacciones'][tx_index]['categoria_sugerida'] = new_category
            context.user_data['financial_json'] = financial_json

            logger.info(f"User corrected category for tx index {tx_index} from '{original_category}' to '{new_category}'.")

            # Vuelve a mostrar la lista de transacciones con la categoría actualizada
            transactions = financial_json.get('transacciones', [])
            # Escapamos solo la categoría nueva que es variable
            escaped_category = escape_markdown_v2(new_category)
            message_text = f"Categoría actualizada a *{escaped_category}*\\.\n\nToca otra transacción para corregir o vuelve al menú\\."
            buttons = []
            for i, tx in enumerate(transactions):
                buttons.append([
                    InlineKeyboardButton(
                        f"{tx['descripcion']} ({tx['monto']}) -> {tx['categoria_sugerida']}",
                        callback_data=f'correct_{i}'
                    )
                ])
            buttons.append([InlineKeyboardButton("<< Volver al Menú", callback_data='main_menu')])
            reply_markup = InlineKeyboardMarkup(buttons)
            await query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
            return

        elif data == 'main_menu':
            buttons = self.gemini_borg._get_contextual_buttons(financial_json)
            keyboard = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Opciones basadas en tu análisis:", reply_markup=reply_markup)
            return

        elif data == 'debt_advisor':
            debt_amount = sum(tx['monto'] for tx in financial_json.get('transacciones', []) if tx['categoria_sugerida'] == 'Préstamo' and tx['tipo'] == 'egreso')
            prompt = f"""<role>You are a financial advisor specializing in debt management.</role>
<context>Design a debt repayment plan for someone with {debt_amount}. Format the entire response using Telegram's MarkdownV2, including bold, italics, and code blocks for clarity.</context>
<steps> 1. Suggest repayment strategies (snowball, avalanche), explaining each one.
2. Calculate potential monthly payments.
3. Recommend steps to avoid new debt, using bold and italics for emphasis.</steps>"""
            response = await self.gemini_borg._generate_content_stream(prompt)
            await query.edit_message_text(text=response, parse_mode=ParseMode.MARKDOWN_V2)

        elif data == 'investment_portfolio':
            risk_level = 'medium' if financial_json['resumen'].get('saldo_final', 0) > 10000 else 'low'
            prompt = f"""<role>You are an investment advisor.</role>
<context>Design an investment portfolio for a risk tolerance level of {risk_level}. Format the entire response using Telegram's MarkdownV2.</context>
<steps> 1. Allocate percentages to stocks, bonds, and cash using bold headers.
2. Suggest 3 specific investment options (as bullet points) for each category.
3. Provide diversification tips in italics.</steps>"""
            response = await self.gemini_borg._generate_content_stream(prompt)
            await query.edit_message_text(text=response, parse_mode=ParseMode.MARKDOWN_V2)

        elif data == 'emergency_fund':
            monthly_expenses = financial_json['resumen'].get('total_egresos', 0) / 12
            prompt = f"""<role>You are a personal finance advisor.</role>
<context>Help calculate the ideal emergency fund amount for someone with {monthly_expenses}. Format the entire response using Telegram's MarkdownV2.</context>
<steps> 1. Show calculations for 3, 6, and 12 months of expenses in a code block.
2. Suggest strategies to build the fund using bullet points.
3. Recommend safe accounts to store the fund.</steps>"""
            response = await self.gemini_borg._generate_content_stream(prompt)
            await query.edit_message_text(text=response, parse_mode=ParseMode.MARKDOWN_V2)

        elif data == 'passive_income':
            interest_area = 'digital subscriptions' if any('Netflix' in p for p in financial_json['insights_detectados'].get('pagos_recurrentes', [])) else 'general'
            prompt = f"""<role>You are a wealth strategist.</role>
<context>Generate 5 passive income ideas for someone interested in {interest_area}. Format the entire response using Telegram's MarkdownV2.</context>
<steps> 1. List income streams with bolded titles.
2. Estimate startup costs or time investment in a code block.
3. Highlight long-term earning potential for each idea in italics.</steps>"""
            response = await self.gemini_borg._generate_content_stream(prompt)
            await query.edit_message_text(text=response, parse_mode=ParseMode.MARKDOWN_V2)

    def run(self):
        """Inicia el bot y lo mantiene corriendo."""
        logger.info("Starting bot...")
        # run_polling es bloqueante y maneja el ciclo de vida del bot,
        # incluyendo el apagado con Ctrl+C.
        self.application.run_polling()
        logger.info("Bot has stopped.")

if __name__ == '__main__':
    bot = BorgotronBot()
    bot.run()
