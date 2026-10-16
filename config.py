import os

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN", "8805271903:AAGYQtEf5Q7eCz5a0eODsbvnUL2FtxMV7FM")

# Admin Telegram Configuration
ADMIN_ID = int(os.getenv("ADMIN_ID", "7003028589"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@Abreham_Tesfaye_Asgid")

# Receiver Account Details for Payment Validation
EXPECTED_RECEIVER = os.getenv("EXPECTED_RECEIVER", "Abreham Tesfaye Asgid")
EXPECTED_CBE_ACCOUNT = os.getenv("EXPECTED_CBE_ACCOUNT", "1000123456789")
EXPECTED_TELEBIRR_PHONE = os.getenv("EXPECTED_TELEBIRR_PHONE", "0911223344")

# Financial Rules
DAILY_PENALTY_FEE = float(os.getenv("DAILY_PENALTY_FEE", "50.0")) # 50 ETB/day late fee

# Verify.ET Live Bank API Key
VERIFY_ET_API_KEY = os.getenv("VERIFY_ET_API_KEY", "VERIFY_BANK_ET_P0We-WsiM6S-NHyVsCgFHzWG11D5LCSgdCO3EdM2IPmfsG8jmewsCFr3r7fuc9nK")

# SQLite Database Name
DB_NAME = "ekub_system.db"