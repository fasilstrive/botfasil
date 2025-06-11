import logging
import os
import gspread
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from openai import OpenAI

# === Load .env ===
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME")

# === Setup Google Sheets ===
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
client_gsheet = gspread.authorize(CREDS)
sheet_user = client_gsheet.open(SPREADSHEET_NAME).worksheet("UserList")
sheet_laporan = client_gsheet.open(SPREADSHEET_NAME).worksheet("Laporan")

# === Setup OpenAI ===
client_openai = OpenAI(api_key=OPENAI_API_KEY)

# === Logging ===
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

# === Auto Register Chat ID ===
async def register_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    name = update.effective_user.first_name

    users = sheet_user.col_values(1)
    if chat_id not in users:
        sheet_user.append_row([chat_id, name])
        await update.message.reply_text(f"Halo {name}! Kamu sudah terdaftar sebagai fasilitator.")
    else:
        await update.message.reply_text(f"Halo {name}!")

# === Command /laporan ===
async def laporan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    users = sheet_user.get_all_records()

    fasilitator = None
    for user in users:
        if str(user["Chat ID"]) == chat_id:
            fasilitator = user["Nama Fasilitator"]
            break

    if fasilitator is None:
        await update.message.reply_text("Kamu belum terdaftar! Silakan kirim pesan apapun dulu untuk auto-register.")
        return

    data_laporan = sheet_laporan.get_all_records()
    laporan_fasilitator = [f"{d['Tanggal']}: {d['Total Peserta']} peserta, Validasi: {d['Validasi']}, Keterangan: {d['Keterangan']}"
                            for d in data_laporan if d["Nama Fasilitator"] == fasilitator]

    if laporan_fasilitator:
        await update.message.reply_text(f"📊 Laporan kamu ({fasilitator}):\n" + "\n".join(laporan_fasilitator))
    else:
        await update.message.reply_text(f"Belum ada laporan untuk {fasilitator}")

# === ChatGPT AI mode ===
async def chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    response = client_openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Kamu asisten pelaporan fasilitator."},
            {"role": "user", "content": user_message}
        ]
    )

    reply = response.choices[0].message.content
    await update.message.reply_text(reply)

# === Main ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", register_user))
    app.add_handler(CommandHandler("laporan", laporan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt))

    print("Bot aktif...")
    app.run_polling()