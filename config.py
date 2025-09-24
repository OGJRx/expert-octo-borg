
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    GOOGLE_AI_KEY = os.getenv('GOOGLE_AI_KEY')
    GROUP_ID = os.getenv('GROUP_ID')
