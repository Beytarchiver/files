# 1. Demo:

# note = int(input("Notunuzu giriniz: "))
# if note < 60:
#     print("FF")
# elif 60 <= note <= 69:
#     print("CC")
# elif 70 <= note <= 79:
#     print("BB")
# elif 80 <= note <= 89:
#     print("BA")
# elif 90  <= note:
#     print("AA")

# 2. demo:

# num = int(input("Sayi giriniz: "))
# if num > 0:
#     print("sayi pozitif")
# elif num == 0:
#     print("Sayi sifir")
# else:
#     print("Sayi negatif")
 

# if num % 2 == 0:
#     print("Sayi cift")
# else:
#     print("Sayi tek")

# 3. demo:

# user = input("Kullanici adi giriniz: ")
# password = input("Password giriniz: ")
# dogru_user = "beytu2855"
# dogru_password = "112233"
# if user == dogru_user and password == dogru_password:
#     print("Giris basarili")
# elif user != dogru_user :
#     print("Kullanici adi hatali")
# elif password != dogru_password :
#     print("Sifre hatali")

# 4. demo:

# müsteri_yas = int(input("Yaşinizi giriniz: "))
# if 0 <= müsteri_yas <= 5:
#    print("Ücretsiz")
# elif 6 <= müsteri_yas <= 17:
#     print("50 TL (ogrenci indirimi)")
# elif 18 <= müsteri_yas <= 64:
#     print("100 TL")
# elif müsteri_yas >= 65:
#     print("60 TL (Yasli indirimi)")
# elif müsteri_yas < 0:
#     print("Gecersiz yaş")

# 5. demo:

# a = int(input("1. sayi: "))
# b = int(input("2. sayi: "))
# c = int(input("3. sayi: "))

# if a>b and a>c:
#     print("En buyuk a")
# elif b>a and b>c:
#     print("En buyuk b")
# else:
#     print("En buyuk c")

# 7. demo:

# isim = input("İsminizi giriniz: ")
# yaş = int(input("Yaşinizi giriniz: "))
# egitim_bilgisi = int(input("Eğitim bilginizi giriniz (1-4): \n1= İlkokul, 2=Ortaokul, 3=Lise, 4=Üniversite\n "))
# if yaş >= 18:
#     print(f"{isim}, ehliyet alabilirsiniz! ")
# elif yaş >= 16:
#     print(f"{isim}, Sadece motorsiklet ehliyeti alabilirsiniz! ")
# elif egitim_bilgisi == "Üniversite":
#     print(f"{isim} ehliyet alabilirsiniz! ")
# else:
#     print(f"{isim}, ehliyet alamazsiniz ")

# 8. demo

# birinci_sinav_notu = int(input("Sinav notunuzu giriniz: "))
# ikinci_sinav_notu = int(input("Sinav notunuzu giriniz: "))
# ortalama = birinci_sinav_notu + ikinci_sinav_notu/2
# if  0 <= ortalama <= 24:
#     print("0")
# elif 25 <= ortalama <= 44:
#     print("1")
# elif 45 <= ortalama <= 54:
#     print("2")
# elif 55 <= ortalama <= 69:
#     print("3")
# elif 70 <= ortalama <= 84:
#     print("4")
# elif 85 <= ortalama <= 100:
#     print("5")

# 9. demo [cok ekstra datetime modulu falan var.]

from datetime import datetime

print("=" * 45)
print("     ARAÇ SERVİS ZAMANLAMASI HESAPLAMA")
print("=" * 45)

tarih_str = input("\nAracın çıkış tarihini giriniz (GG/AA/YYYY): ")

try:
    
    trafik_tarihi = datetime.strptime(tarih_str, "%d/%m/%Y")
    bugun = datetime.now()

    
    gecen_yil = (bugun - trafik_tarihi).days / 365.25

    print("\n" + "=" * 45)
    print("    SERVİS DURUMU")
    print("=" * 45)
    print(f"\n📅 Trafik Çıkış Tarihi: {trafik_tarihi.strftime('%d/%m/%Y')}")
    print(f"📅 Bugün: {bugun.strftime('%d/%m/%Y')}")
    print(f"⏱️  Geçen Süre: {gecen_yil:.1f} yıl")  

    
    if gecen_yil >= 3:
        print(f"\n3. BAKIM ZAMANI VEYA SONRASI")
        print("Son bakım tarihi geçmiştir veya 3.+ bakımları gelmiştir!")
    elif gecen_yil >= 2:
        print(f"\n2. BAKIM YAPILMALI / YAPILDI")
        print(f"3. bakıma yaklaşık {3 - gecen_yil:.1f} yıl (veya {(3 - gecen_yil) * 12:.0f} ay) kaldı.")
    elif gecen_yil >= 1:
        print(f"\n1. BAKIM YAPILMALI / YAPILDI")
        print(f"2. bakıma yaklaşık {2 - gecen_yil:.1f} yıl (veya {(2 - gecen_yil) * 12:.0f} ay) kaldı.")
    else:
        print(f"\nHenüz 1 yıl dolmadı, bakım gerekmiyor.")
        print(f"1. bakıma yaklaşık {1 - gecen_yil:.1f} yıl (veya {(1 - gecen_yil) * 12:.0f} ay) kaldı.")

except ValueError:
    print("\nLütfen tarihi GG/AA/YYYY formatında doğru giriniz!")
    print("   Örnek: 15/03/2020")











