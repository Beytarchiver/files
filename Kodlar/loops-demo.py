
# Sayı tahmin etme oyunu:

# import random
# secret = random.randint(1,100)
# attemps = 0
# while True:
#     try:
#         can_sayisi = int(input("\nKaç can istiyorsunuz? (1-5 arası önerilir.)"))
#         if can_sayisi < 1:
#             print("Can sayisi en az 1 olmali! ")
#             continue
#         break
#     except ValueError:
#         print("Lütfen Sayi giriniz! ")
# toplam_puan = 0
# soru_sayisi = 5
# puan_per_soru = 20
# soru_no = 1
# print(f"\nToplam {soru_sayisi} soru sorulacak. Her soru = {puan_per_soru} puan")
# print(f"Başlangıç canınız: {can_sayisi}")
# print("=" * 50)
# while soru_no <= soru_sayisi:
#     print(f"\nSORU {soru_no}/{soru_sayisi}")
#     print(f"Kalan can: {can_sayisi} | Toplam Puan: {toplam_puan}")
#     print("-" * 50)
#     tutulan_sayi = random.randint(1, 100)
#     tahmin_sayisi = 0
#     soru_bitti = False
#     while not soru_bitti:
#         try:
#             tahmin = int(input("1-100 arasında sayi tahmin ediniz: "))
#             if tahmin < 1 or tahmin > 100:
#                 print("1 - 100 arasında sayı giriniz! ")
#                 continue

#             tahmin_sayisi += 1
#             if tahmin == tutulan_sayi:
#                 print(f"Doğru! sayi {tutulan_sayi} idi! ")
#                 print(f"{tahmin_sayisi} tahminde bulundunuz! ")
#                 toplam_puan += puan_per_soru
#                 print(f"+{puan_per_soru} puan kazandınız! ")

#                 soru_bitti = True
#             elif tahmin < tutulan_sayi:
#                 print(f"YUKARIDA! ({tahmin} < Tutulan sayı)")
#                 can_sayisi -= 1
#                 print(f"Kalan can: {can_sayisi}")
#                 if can_sayisi == 0:
#                     print(f"Canınız bitti! Sayı: {tutulan_sayi}")
#                     soru_bitti = True
#             else:
#                 print(f"AŞAĞIDA! ({tahmin} > Tutulan sayı)")
#                 can_sayisi -= 1
#                 print(f"Kalan can: {can_sayisi}")
#                 if can_sayisi == 0:
#                     print(f"Canınız bitti! Sayı: {tutulan_sayi}")
#                     soru_bitti = True
#         except ValueError:
#             print("Lütfen geçerli sayi girin! ")
#             continue

#     if can_sayisi == 0 and soru_no < soru_sayisi:
#         print(f"\nCanınız bitti! Kalan: {soru_sayisi - soru_no} soru atlanılıyor...")
#         break

#     soru_no += 1



# print("\n" + "=" * 50)
# print("OYUN BİTTİ!")
# print("=" * 50)
# print(f"Final puanınız: {toplam_puan}/100")



# if toplam_puan == 100:
#     print("MÜKEMMEL! Tüm soruları doğru bildiniz! ")
# elif toplam_puan >= 80:
#     print("HARİKA! Çok iyi performans! ")
# elif toplam_puan >= 60:
#     print("İYİ! Daha iyi olabilirsiniz! ")
# elif toplam_puan >= 40:
#     print("KABUL! Biraz daha çalışın! ")
# else:
#     print("Bir daha deneyin, emin olacaksınız! ")

# print("=" * 50)

# Tas-Kağıt-Makas oyunu:


import random
secenekler = ["taş", "kağıt","makas"]

oyuncu_skor = 0
bilgisayar_skor = 0

print("=" * 50)
print("Taş-Kağıt-Makas Oyunu")
print("=" * 50)
print("Çıkmak için çıkış yazabilirsiniz.\n")


while True:
    oyuncu_secimi = input("Taş mı Kağıt mı, Makas mı? ").lower().strip()
    if oyuncu_secimi == "çıkış":
        print("\nOYUN BİTTİ!")
        print(f"Son skor -> Siz: {oyuncu_skor} | Bilgisayar: {bilgisayar_skor}")
        break
    
    
    if oyuncu_secimi not in secenekler:
        print("Lütfen geçerli bir seçim yapınız (taş,kağıt,makas).\n")
        continue
    bilgisayar_secimi = random.choice(secenekler)
    print(f"Bilgisayarın seçimi: {bilgisayar_secimi.capitalize()}")



    if oyuncu_secimi == bilgisayar_secimi:
        print("Berabere! ")
    elif (
        (oyuncu_secimi == "taş" and bilgisayar_secimi == "makas")
        or (oyuncu_secimi == "kağıt" and bilgisayar_secimi == "taş")
        or (oyuncu_secimi == "makas" and bilgisayar_secimi == "kağıt")
    ):
        print("Tebrikler, bu turu kazandınız! ")
        oyuncu_skor += 1
    else:
        print("Bu turu bilgisayar kazandı! ")
        bilgisayar_skor += 1

        print(
            f"Skor -> Siz: {oyuncu_skor} | Bilgisayar: {bilgisayar_skor}\n"
            + "-" * 50
        )

    


    



