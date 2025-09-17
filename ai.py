import os
import sqlite3
import threading
import concurrent.futures
import requests
from bs4 import BeautifulSoup
import bz2
import xml.etree.ElementTree as ET
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# ======================
# 1. Veri tabanı hazırlığı
# ======================
DB_PATH = "mega_ai.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kaynak TEXT,
    konu TEXT,
    icerik TEXT
)
''')
conn.commit()

lock = threading.Lock()  # Çoklu thread güvenliği

# ======================
# 2. Wikipedia dump işleme (multithread)
# ======================
def wiki_dump_aktar(dump_path):
    def parse_page(elem):
        title = elem.find("./title").text if elem.find("./title") is not None else ""
        revision = elem.find("./revision")
        text = revision.find("./text").text if revision is not None and revision.find("./text") is not None else ""
        if title and text:
            with lock:
                cursor.execute("INSERT INTO knowledge (kaynak, konu, icerik) VALUES (?, ?, ?)", ("wikipedia", title, text))

    print("[WIKI] Dump işleniyor...")
    with bz2.open(dump_path, "rb") as f, concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for event, elem in ET.iterparse(f, events=("end",)):
            if elem.tag.endswith("page"):
                executor.submit(parse_page, elem)
                elem.clear()
    conn.commit()
    print("[WIKI] Wikipedia veri tabanına aktarıldı!")

# ======================
# 3. Çok kaynaklı wiki scraping
# ======================
def wiki_scrape_async(konu, url_base, kaynak):
    def scrape_task():
        try:
            r = requests.get(f"{url_base}{konu.replace(' ', '_')}")
            r.raise_for_status()
            soup = BeautifulSoup(r.text, 'html.parser')
            if kaynak == "mc_wiki":
                text = "\n".join([p.get_text() for p in soup.find_all('p')])
            elif kaynak == "python_wiki":
                content = soup.find("div", {"id":"content"})
                text = content.get_text() if content else ""
            elif kaynak == "cpp_wiki":
                content = soup.find("div", {"id":"mw-content-text"})
                text = content.get_text() if content else ""
            with lock:
                cursor.execute("INSERT INTO knowledge (kaynak, konu, icerik) VALUES (?, ?, ?)", (kaynak, konu, text))
                conn.commit()
                print(f"[{kaynak.upper()}] {konu} kaydedildi!")
        except Exception as e:
            print(f"[{kaynak.upper()} HATA] {konu} -> {e}")
    threading.Thread(target=scrape_task).start()

# ======================
# 4. GPT Model (yalnızca opsiyonel görevler için)
# ======================
MODEL_NAME = "gpt2"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)

def gpt_cevap(prompt, max_len=300):
    inputs = tokenizer.encode(prompt, return_tensors="pt")
    outputs = model.generate(inputs, max_length=max_len, do_sample=True, temperature=0.7)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

# ======================
# 5. Veri tabanı sorgulama ve çoklu eşzamanlılık
# ======================
def veri_sorgula(kelime):
    with lock:
        cursor.execute("SELECT konu, icerik FROM knowledge WHERE icerik LIKE ?", ('%'+kelime+'%',))
        results = cursor.fetchall()
    if results:
        return "\n\n".join([f"{konu}: {icerik[:500]}..." for konu, icerik in results])
    else:
        return "Veri tabanında ilgili içerik bulunamadı."

# ======================
# 6. Kullanıcı arayüzü
# ======================
def baslat():
    print("Offline Mega AI Başlatıldı 🚀\n")
    while True:
        komut = input("\n[Sen] Soru / GPT: / exit: ")
        if komut.lower() in ["exit", "quit"]:
            print("Kapatılıyor... 👋")
            break
        elif komut.lower().startswith("gpt:"):
            prompt = komut[4:].strip()
            print(f"[GPT] {gpt_cevap(prompt)}")
        else:
            print(f"[VeriTabanı] {veri_sorgula(komut)}")

# ======================
# Örnek kullanım
# ======================
if __name__ == "__main__":
    # wiki_scrape_async("Python", "https://wiki.python.org/moin/", "python_wiki")
    # wiki_scrape_async("Minecraft", "https://minecraft.fandom.com/wiki/", "mc_wiki")
    baslat()
