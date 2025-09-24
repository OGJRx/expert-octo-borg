import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'

import logging
import google.generativeai as genai
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from telegram.constants import ParseMode
from config import Config
from geminiborg import GeminiBorg, ASK_FOR_INPUT, HANDLE_FILE, HANDLE_INCOME, ASK_DEEPER_INSIGHT, escape_markdown_v2 # Import the GeminiBorg class, conversation states, and markdown escape utility

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BorgotronBot:
    def __init__(self):
        self.config = Config()
        self.gemini_borg = GeminiBorg() # Instantiate GeminiBorg
        self.setup_ai()
    
    def setup_ai(self):
        """Configurar conexión con Google AI"""
        # genai.configure is already called within GeminiBorg's setup_ai_client
        # self.gemini_borg.setup_ai_client() # This is already called in GeminiBorg's __init__
        logger.info("Google AI configured via GeminiBorg.")

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
        # La función escape_markdown_v2 se encarga del resto.
        escaped_message = escape_markdown_v2(full_message)
        await update.message.reply_text(escaped_message, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"User {update.effective_user.id} started the bot.")
    
    async def ayuda_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /ayuda - Asistente IA dinámico"""
        message = (
            "🤖 *¡Hola! Soy BORG, tu asistente financiero personal!* 🤖\n\n"
            "Estoy aquí para ayudarte a gestionar tus finanzas con la potencia de la IA de Google Gemini. Aquí tienes una guía de mis comandos:\n\n"
            "📚 *Comandos Disponibles*:\n"
            "• /start - _Inicia una nueva sesión o verifica el estado actual del bot y obtén una guía rápida de comandos._\n"
            "• /ayuda - _Muestra este mensaje de ayuda detallado con todos los comandos y su uso._\n"
            "• /presupuesto - _Activa el modo de creación de presupuesto. Te guiaré paso a paso para generar un plan financiero personalizado._\n"
            "• /cancel - _Cancela cualquier operación o conversación en curso. Útil si necesitas empezar de nuevo o has terminado una tarea._\n\n"
            "✨ *Consejo*: Siempre puedes usar /cancel si te sientes perdido o quieres reiniciar."
        )
        escaped_message = escape_markdown_v2(message)
        await update.message.reply_text(escaped_message, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info(f"User {update.effective_user.id} requested help.")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels and ends the conversation."""
        await update.message.reply_text(
            'Conversación cancelada. ¡Hasta luego!',
            reply_markup=ReplyKeyboardRemove()
        )
        logger.info(f"User {update.effective_user.id} cancelled the conversation.")
        return ConversationHandler.END

    def run(self):
        """Iniciar el bot"""
        application = Application.builder().token(self.config.TELEGRAM_TOKEN).build()
        
        # Registrar comandos
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("ayuda", self.ayuda_command))
        application.add_handler(CommandHandler("cancel", self.cancel))

        # Conversation Handler for /presupuesto
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
                    CommandHandler("presupuesto", self.gemini_borg.handle_deeper_insight), # Allow generating budget from here
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )
        application.add_handler(presupuesto_handler)
        
        # Iniciar polling
        logger.info("Bot started polling...")
        application.run_polling()

if __name__ == '__main__':
    bot = BorgotronBot()
    bot.run()
