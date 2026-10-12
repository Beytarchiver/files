from ogrenci_islemleri import ( 
    ogrenci_ekle,
    ogrenci_listele,
    ogrenci_ara,
    ogrenci_sil,
    ogrenci_guncelle
)

def menu_goster():
    print("\n" + "=" * 30)
    print("      Öğrenci Sistemi")
    print("=" * 30)
    print("1. Öğrenci Ekle")
    print("2. Öğrenci Listele")
    print("3. Öğrenci Sil")
    print("4. Öğrenci Güncelle")
    print("5. Öğrenci Ara")
    print("6. Çıkış")
    return input("Seçiminizi yapınız: ")

def uygulamayi_calistir():
    while True:
        secim = menu_goster()

        if secim == "1":
            ad     = input("Ad: ")
            soyadi = input("Soyad: ")
            numara = input("Numara: ")
            bolum  = input("Bölüm: ")
            print(ogrenci_ekle(ad, soyadi, numara, bolum))

        elif secim == "2":
            print(ogrenci_listele())

        elif secim == "3":
            numara = input("Silinecek öğrencinin numarası: ")
            print(ogrenci_sil(numara))

        elif secim == "4":
            numara     = input("Güncellenecek öğrencinin numarası: ")
            yeni_ad    = input("Yeni ad (boş bırakmak için Enter): ")
            yeni_soyad = input("Yeni soyad (boş bırakmak için Enter): ")
            yeni_bolum = input("Yeni bölüm (boş bırakmak için Enter): ")
            print(ogrenci_guncelle(
                numara,
                yeni_ad    or None,
                yeni_soyad or None,
                yeni_bolum or None
            ))

        elif secim == "5":
            numara = input("Aranacak öğrencinin numarası: ")
            print(ogrenci_ara(numara))

        elif secim == "6":
            print("Çıkış yapılıyor...")
            break

        else:
            print("Geçersiz seçim, tekrar deneyin.")