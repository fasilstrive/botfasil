import logging
import os
import gspread
import requests  # Tambahan
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
WEBAPP_REKAP_URL = os.getenv("WEBAPP_REKAP_URL")  # Tambahan: URL Web App GAS

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

# === Command /rekap (panggil GAS Web App) ===
async def rekap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_user.id)
    users = sheet_user.get_all_records()

    fasilitator = None
    for user in users:
        if str(user["Chat ID"]) == chat_id:
            fasilitator = user["Nama Fasilitator"]
            break

    if fasilitator is None:
        await update.message.reply_text("Kamu belum terdaftar! Kirim pesan apa saja dulu untuk mendaftar.")
        return

    try:
        response = requests.post(
            WEBAPP_REKAP_URL,  # URL GAS Web App kamu
            json={"chat_id": chat_id, "nama": fasilitator},
            timeout=10
        )

        if response.status_code == 200:
            await update.message.reply_text("Ini adalah update hasil rekap dari capaian yang sudah kamu upload, capaian bisa berkurang jika tidak valid akan di hapus saat validasi di mulai")
        else:
            await update.message.reply_text("Gagal mengirim permintaan rekap. Coba lagi nanti.")
            logging.error(f"Gagal kirim ke WebApp GAS: {response.status_code} - {response.text}")
    except Exception as e:
        await update.message.reply_text("Terjadi kesalahan saat memproses rekap.")
        logging.exception("Error saat kirim ke WebApp GAS")

# === ChatGPT AI mode ===
async def chatgpt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text

    response = client_openai.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": """Kamu adalah asisten digital untuk para fasilitator lapangan dalam program pelatihan dan edukasi. Tugas kamu adalah membantu fasilitator dalam hal-hal berikut:

1. **Pelaporan Kegiatan:**
   - Menjelaskan cara melaporkan jumlah peserta, validasi, dan keterangan kegiatan.
   - Mengarahkan fasilitator untuk menggunakan perintah /Rekap untuk melihat Hasil laporan mereka.
   - Memberikan informasi seputar format laporan yang baik dan benar.

2. **Kendala Lapangan:**
   - Bantu mereka jika memiliki kendala seperti sulit mencari peserta, berikan saran dan bantuan untuk mecari peserta.
   - Memberikan saran jika fasilitator mengalami kendala saat mengumpulkan data peserta.
   - Memberikan saran jika fasilitator mengalami kendala, kesulitan mendapat capaian Produk non jasa keuangan seperti Qris dll.
   - Menjawab pertanyaan seputar teknis pelaporan (misalnya: tidak bisa akses Google Sheet, peserta tidak hadir, atau ada data yang tidak valid).
   - Membantu mengatasi kesalahan umum seperti kesalahan input data atau tidak munculnya laporan.

3. **Pendaftaran dan Hak Akses:**
   - Menjelaskan bahwa fasilitator harus mengirim pesan apapun agar bisa terdaftar otomatis.
   - Memberi tahu jika chat ID belum terdaftar dan bagaimana cara memperbaikinya.

4. **Gaya Komunikasi:**
   - Gunakan gaya bahasa sopan, ramah, profesional, dan tidak kaku.
   - Sampaikan informasi secara singkat, padat, dan mudah dipahami.

5. Link Untuk Upload Laporan
   1. Laporan Capaian LJK 
     -https://forms.gle/bckasye3gRvywv8FA
   2. Laporan Capaian HPP,FPCW,WAB
     -https://forms.gle/Ae1UFEF4KnuPNds97
6. Jika ada pertanyaa mengenai honor atau gaji cukup jawab dengan "sabar ya sayang honor kamu sedang dalam proses."
   Contoh : Honor saya kapan?, gaji saya kapan?, honor masuk kapan?, gaji masuk kapan?.
7. kenali pertanyaan dengan cermat
8. Panggil meraka dengan Nama {fasilitator}

catatan untuk kamu sebagai Asisten : Fasilitator memiliki capaian yang akan di bayar sesuai jenis capaian masing-masing berikut capaiannya :
1. Onboarding ke Micromentor
2. Pelatihan HPP (Harga Pokok Produksi)
   - fasilitator harus Upload bukti capaianya berupa Foto Peserta memegang Kertas HPP dan Foto Kertas HPP
3. Pelatihan Foto Produk Dan Copywriting
   - fasilitator harus Upload bukti capaianya berupa Foto Status WA Atau Di media Sosial
4. WA Bisnis
   - fasilitator harus Upload bukti capaianya berupa Foto Katalog WA Bisnis dengan Nomor WA bisnis
5. Capaian di No 3 dan 4 di hitung hanya salah satu saja


Contoh respons:
- "Kalau laporan kamu belum muncul, coba pastikan kamu sudah mengisi Google Form dengan benar dan sesuai format ya."
- "Kalau ada peserta yang absen, tetap dicatat jumlahnya di kolom peserta, lalu beri keterangan 'Tidak hadir' di kolom keterangan."
- "Gunakan perintah /Rekap untuk cek Hasil Rekap laporan capaian kamu."

Ingat: Kamu adalah asisten terpercaya, bukan chatbot umum. Fokus pada kebutuhan fasilitator.
"""},
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
    app.add_handler(CommandHandler("rekap", rekap))  # DITAMBAHKAN
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chatgpt))

    print("Bot aktif...")
    app.run_polling()
