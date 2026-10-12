# 1. demo #

# sayi = int(input("Sayi giriniz: "))
# sonuc = (sayi>=0) and (sayi<=100)
# print(sonuc)

# 2. demo #
# sayi = int(input("Sayi giriniz: "))
# pozitif_cift_mi = (sayi > 0 ) and (sayi %2 == 0)
# print(pozitif_cift_mi)

# 3. demo#

# email = input("email giriniz: ")
# parola = input("parola gir: ")
# kayitli_email = "btlrhyme34@gmail.com"
# kayitli_parola = "hjasko2Bc2*bC"
# giris_basarili_mi = (email == kayitli_email) and (parola == kayitli_parola)
# print(giris_basarili_mi)

# 4. demo #

# a = int(input("1. Sayi: "))
# b = int(input("2. Sayi: "))
# c = int(input("3. Sayi: "))

# en_buyuk = max(a,b,c)
# en_kucuk = min(a,b,c)

# print("En Büyük Sayi:", en_buyuk)
# print("En Küçük Sayi:", en_kucuk)

# 5. demo #

# a = int(input("1. Sayi: "))
# b = int(input("2. Sayi: "))
# c = int(input("3. Sayi: "))

# siralama = sorted([a,b,c])
# print("Kücükten Büyüge", siralama)

# 6. demo #

# vize1 = float(input("Sayi giriniz: "))
# vize2 = float(input("Sayi giriniz: "))
# final = float(input("Sayi giriniz: "))
# vize_ortalama = (vize1+vize2) / 2
# ortalama = (vize_ortalama * 0.4) + (final * 0.6)
# gecme_durumu = (final>= 70) or (ortalama>=50) and (final>=50)
# print("Dersi Geçme Durumu (True: Geçti, False: Kaldi):", gecme_durumu)

# 7. demo #

ad = input("Adiniz: ")
soyad = input("Soyadiniz: ")
kilo = float(input("Kilonuz(kg): "))
boy = float(input("Boyunuz(cm): "))
vki = kilo / (boy**2)
durum = (
    (vki < 18.5 and "Zayif") or
    (18.5 <= vki < 25.0 and "Normal Kilolu") or 
    (25.0 <=vki < 30.0 and "Fazla Kilolu")
    (vki>= 30.0 and "Obez")
)

print(f"\nSayin {ad}, Vücüt Kitle indeksiniz: {vki}")
print(f"Durumunuz: {durum}")








