def sayHello(name):
    return "Hello, " + name

msg = sayHello("Alice")

print(msg)

def total(a, b):
    return a + b

result = total(5, 10)
result = total(20, 30)
print(result)
def yasHesapla(dogumYili):
    return 2024 - dogumYili

ageCinar = yasHesapla(2001)
ageYasar = yasHesapla(1985)
ageKamil = yasHesapla(2014)
print(ageCinar)
print(ageYasar)
print(ageKamil)

def EmeklilikHesapla(dogumYili, isim):
    """
    DOCSTRING: Bu fonksiyon, verilen doğum yılına göre emeklilik yaşını hesaplar ve kullanıcıya kalan yılları bildirir.
    INPUT: dogumYili (int) - Kullanıcının doğum yılı, isim (str) - Kullanıcının adı
    OUTPUT: Kullanıcıya kalan emeklilik yılı veya emekli olup olmadığını bildirir.
    """
    
    
    
    
    yas = yasHesapla(dogumYili)
    emeklilikYasi = 65
    kalanYil = emeklilikYasi - yas
    if emeklilikYasi > yas:
        print(f"{isim}, emekliliğe {kalanYil} yıl kaldı.")
    else:
        print(f"{isim}, zaten emekli oldunuz.")
EmeklilikHesapla(2001, "Muhammed")
EmeklilikHesapla(1950, "Ahmet")
print(help(EmeklilikHesapla))


