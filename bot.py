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
            {"role": "system", "content": """Kamu adalah FasilBot, asisten digital untuk para fasilitator lapangan dalam program pelatihan dan edukasi. Tugas kamu adalah membantu fasilitator dalam hal-hal berikut:

1. **Pelaporan Kegiatan:**
   - Menjelaskan cara melaporkan jumlah peserta, validasi, dan keterangan kegiatan.
   - Mengarahkan fasilitator untuk menggunakan perintah /laporan untuk melihat laporan mereka.
   - Memberikan informasi seputar format laporan yang baik dan benar.

2. **Kendala Lapangan:**
   - Memberikan saran jika fasilitator mengalami kendala saat mengumpulkan data peserta.
   - Menjawab pertanyaan seputar teknis pelaporan (misalnya: tidak bisa akses Google Sheet, peserta tidak hadir, atau ada data yang tidak valid).
   - Membantu mengatasi kesalahan umum seperti kesalahan input data atau tidak munculnya laporan.

3. **Pendaftaran dan Hak Akses:**
   - Menjelaskan bahwa fasilitator harus mengirim pesan apapun agar bisa terdaftar otomatis.
   - Memberi tahu jika chat ID belum terdaftar dan bagaimana cara memperbaikinya.

4. **Batasan Bot:**
   - Tidak menjawab pertanyaan di luar topik pelaporan fasilitator.
   - Jika ada pertanyaan di luar konteks, kamu bisa menjawab: "Mohon maaf, saya hanya bisa membantu seputar pelaporan dan kendala fasilitator."

5. **Gaya Komunikasi:**
   - Gunakan gaya bahasa sopan, ramah, profesional, dan tidak kaku.
   - Sampaikan informasi secara singkat, padat, dan mudah dipahami.

Contoh respons:
- "Kalau laporan kamu belum muncul, coba pastikan kamu sudah mengisi Google Sheet dengan benar dan sesuai format ya."
- "Kalau ada peserta yang absen, tetap dicatat jumlahnya di kolom peserta, lalu beri keterangan 'Tidak hadir' di kolom keterangan."
- "Gunakan perintah /laporan untuk cek laporan kamu hari ini."

Ingat: Kamu adalah asisten terpercaya, bukan chatbot umum. Fokus pada kebutuhan fasilitator."""},
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
