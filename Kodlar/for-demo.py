# numbers = [1, 3, 5, 7, 9, 12, 15, 21]
# for num in numbers:
#     if num % 3 == 0:
#         print(num)
# toplam = 0
# for num in numbers:
#     toplam+= num
#     print("Sayilarin toplami:", toplam)
# for num in numbers:
#     if num % 2 != 0:
#         karesi = num ** 2
#         print(f"{num} sayinin karesi: {karesi} ")

# sehirler = ["Samsun", "Trabzon", "Yalova", "Ankara", "Rize"]
# for sehir in sehirler:
#     if len(sehir) <= 5:
#         print(f"5 veya daha az karakterli: {sehir} ({len(sehir)}karakter)")
#     if len(sehir) >= 5:
#         print(f"5 veya daha fazla karakterli: {sehir} ({len(sehir)}karakter)")

veriler = [
    {"name":" Samsung S6", "price": "3000"},
    {"name":" Samsung S7", "price": "4000"},
    {"name":" Samsung S8", "price": "5000"},
    {"name":" Samsung S9", "price": "6000"},
    {"name":" Samsung S10", "price": "7000"}
]
toplam = 0
for veri in veriler:
    fiyat = int(veri["price"])
    toplam += fiyat
    print(f"{veri['name']}: {fiyat} TL")

print(f"\n=== Genel Toplam: {toplam} TL ===")
print("=== Fiyati 5000 TL'den Fazla Olan Ürünler ===\n")
for veri in veriler:
    fiyat = int(veri["price"])
    if fiyat > 5000:
        print(f"{veri['name']}: {fiyat} TL")