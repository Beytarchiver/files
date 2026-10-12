# def yazdir(kelime, adet):
#     print(kelime * adet)
# yazdir("Merhaba\n", 3)


# def listeye_cevir(*args):
#     liste = []
#     for arg in args:
#         liste.append(arg)
#     return list(args)
# result = listeye_cevir(1, 2, 3, 4, 5, "Merhaba")
# print(result)



# def asal_bul(baslangic, bitis):
#     asal_sayilar = []
#     for sayi in range(baslangic, bitis + 1):
#         if sayi > 1:
#             for i in range(2, sayi):
#                 if (sayi % i) == 0:
#                     break
#             else:
#                 asal_sayilar.append(sayi)
#     return asal_sayilar
# print(asal_bul(1, 100))
# print(asal_bul(100, 200))


def tam_bolenler(sayi):
    bolenler = []
    for i in range(1, sayi + 1):
        if sayi % i == 0:
            bolenler.append(i)
    return bolenler

print(tam_bolenler(12))
print(tam_bolenler(25))
print(tam_bolenler(100))


