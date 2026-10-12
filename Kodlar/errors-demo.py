liste = ["1", "2", "5a", "10b", "abc", "xyz"]
sayilar = [eleman for eleman in liste if eleman.isdigit()]
print(sayilar)


def sayı_sayı(sayi):
    if sayi.isdigit():
        return True
    else:
        return False

