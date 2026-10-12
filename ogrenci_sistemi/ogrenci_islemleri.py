from veritabani import ogrenciler  

def ogrenci_ekle(ad, soyadi, numarasi, bolumu):
    yeni_ogrenci = {
        "ad": ad,
        "soyadi": soyadi,
        "numarasi": numarasi,
        "bolumu": bolumu
    }
    ogrenciler.append(yeni_ogrenci)
    return f"✅ {ad} {soyadi} başarıyla eklendi"

def ogrenci_listele():
    if not ogrenciler:
        return "⚠️ Kayıtlı öğrenci bulunamadı"
    liste = "\n----- Kayıtlı Öğrenciler -----\n"
    for i, ogr in enumerate(ogrenciler, start=1):
        liste += f"{i}. {ogr['ad']} {ogr['soyadi']} - No: {ogr['numarasi']} ({ogr['bolumu']})\n"
    return liste

def ogrenci_ara(numara):
    for ogr in ogrenciler:
        if ogr["numarasi"] == numara:
            return f"🔍 {ogr['ad']} {ogr['soyadi']} - No: {ogr['numarasi']} ({ogr['bolumu']})"
    return "❌ Öğrenci bulunamadı."

def ogrenci_sil(numara):
    for i, ogr in enumerate(ogrenciler):
        if ogr["numarasi"] == numara:
            silinen = ogrenciler.pop(i)
            return f"🗑️ {silinen['ad']} {silinen['soyadi']} silindi."
    return "❌ Silinecek öğrenci bulunamadı."

def ogrenci_guncelle(numara, yeni_ad=None, yeni_soyad=None, yeni_bolum=None):
    for ogr in ogrenciler:
        if ogr["numarasi"] == numara:
            if yeni_ad:    ogr["ad"]     = yeni_ad
            if yeni_soyad: ogr["soyadi"] = yeni_soyad
            if yeni_bolum: ogr["bolumu"] = yeni_bolum
            return f"🔄 Güncellendi: {ogr['ad']} {ogr['soyadi']}"
    return "❌ Güncellenecek öğrenci bulunamadı."