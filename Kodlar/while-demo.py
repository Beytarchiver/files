# numbers = [1, 2, 3, 5, 7, 9, 11, 16]
# i = 0
# while i < len(numbers):
#     print(numbers[i])
#     i += 1

# baslangic = int(input("Baslangic degerini giriniz: "))
# bitis = int(input("Bitis degerini giriniz: "))
# if baslangic %2 == 0:
#     baslangic += 1
# sayi = baslangic
# while sayi <= bitis:
#     print(sayi)
#     sayi += 2

# sayi = 100
# while sayi >= 1:
#       print(sayi)
#       sayi -= 1



# sayilar = []
# i = 0
# while i<5:
#     sayi = float(input(f"{i + 1}. sayiyi giriniz: "))
#     sayilar.append(sayi)
#     i += 1
#     sayilar.sort() # Büyükten kücüge icin sayilar.sort() yerine sayılar.sort(reverse = True) yapsak iyi olur.
#     print("\nGirilen sayilarin kücükten büyüge siralanisi:")
#     for s in sayilar:
#         print(s),

urunler = []
print("Ürün ekleme sistemine hoşgeldiniz!")
print('Çikmak için ürün adina "q" yazin.')
while True:
    urun_adi = input("Ürününüzün adini giriniz: ").strip()
    if urun_adi.lower() == "q":
        break
    if not urun_adi:
        print("Ürün adi boş olamaz, lütfen tekrar deneyin.")
        continue
    fiyat = float(input(f"{urun_adi} ürününün fiyati: "))
    urun = {
        "ad": urun_adi,
        "fiyat": fiyat
    }
    urunler.append(urun)

print("\n--- EKLENEN ÜRÜNLERİN LİSTESİ ---")
if len(urunler) == 0:
    print("Hiç ürün eklenmedi.")
else:
    i = 0
    while i < len(urunler):
        u = urunler[i]
        print(f"{i + 1}. {u['ad']} - {u['fiyat']}")
        i += 1

        print("\n--- EKLENEN ÜRÜNLERİN FİYATLARİ ---")
for u in urunler:
    print(f"Ürün: {u["ad"]} - FİYAT: {u["fiyat"]} TL")


