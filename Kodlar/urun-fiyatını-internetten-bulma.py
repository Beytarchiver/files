from serpapi import GoogleSearch

# -------------------------------------------------------------

SERP_API_KEY = "befd5d953c4d0e69ed8425cc145adefdbc1646b73b9ab3c6bc303430548f1d6f"
# -------------------------------------------------------------

def internetten_fiyat_bul(urun_adi):
    """SerpAPI kullanarak Google Shopping üzerinden fiyat arar."""
    params = {
        "engine": "google_shopping",
        "q": urun_adi,
        "hl": "tr",
        "gl": "tr",
        "api_key": SERP_API_KEY  
        
    }

    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        shopping_results = results.get("shopping_results", [])
        
        if shopping_results:
           
            return shopping_results[0].get("price", "Fiyat Yok")
            
        return "Fiyat Bulunamadı"
    except Exception as e:
        return f"Hata Oluştu: {e}"



urunler = []

print("=" * 50)
print("   SERPAPI İLE ÖRNEK ÜRÜN FİYAT TARAMA   ")
print("=" * 50)

while True:
    urun_adi = input("\nÜrün adini girin (Çikiş için 'q'): ").strip()
    
    if urun_adi.lower() == 'q':
        break
        
    if urun_adi == "":
        continue
        
    print(f"'{urun_adi}' için Google Shopping fiyati araniyor...")
    fiyat = internetten_fiyat_bul(urun_adi)
    
    urunler.append({
        "ad": urun_adi,
        "fiyat": fiyat
    })
    
    print(f"-> Sonuç: {fiyat}")



print("\n" + "=" * 50)
print("SONUÇ LİSTESİ:")
for i, urun in enumerate(urunler, 1):
    print(f"{i}. {urun['ad']} -> {urun['fiyat']}")
print("=" * 50)

