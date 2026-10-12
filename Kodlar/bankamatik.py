


# 1. Örnek Çok sıradan klasik bir bankamatik uygulaması. Kullanıcıya bakiye gösterme, para yatırma ve para çekme seçenekleri sunar. Kullanıcı seçimine göre işlemler yapılır ve bakiye güncellenir.

# def bakiye_goster(bakiye):
#     print(f"Mevcut bakiyeniz: {bakiye} TL")


# def para_yatir(bakiye, miktar):
#     if miktar <= 0:
#         print("Lütfen geçerli bir miktar giriniz.")
#         return bakiye
#     bakiye += miktar
#     print(f"{miktar} TL yatırıldı. Yeni bakiyeniz: {bakiye} TL")
#     return bakiye


# def bankamatik():
#     bakiye = 1000  
#     while True:
#         print("\n1. Bakiye Göster")
#         print("2. Para Yatır")
#         print("3. Para Çek")
#         print("4. Çıkış")
#         secim = input("Lütfen bir seçenek giriniz (1-4): ")
#         if secim == "1":
#             bakiye_goster(bakiye)
#         elif secim == "2":
#             miktar = float(input("Yatırmak istediğiniz miktarı giriniz: "))
#             bakiye = para_yatir(bakiye, miktar)
#         elif secim == "3":
#             miktar = float(input("Çekmek istediğiniz miktarı giriniz: "))
#             if miktar <= 0:
#                 print("Lütfen geçerli bir miktar giriniz.")
#             elif miktar > bakiye:
#                 print("Yetersiz bakiye.")
#             else:
#                 bakiye -= miktar
#                 print(f"{miktar} TL çekildi. Yeni bakiyeniz: {bakiye} TL")
#         elif secim == "4":
#             print("Çıkış yapılıyor...")
#             break
#         else:
#             print("Geçersiz seçenek. Lütfen tekrar deneyiniz.")


# bankamatik()



# 2. Örnek Daha gelişmiş bir bankamatik uygulaması. Kullanıcıya bakiye gösterme, para yatırma, para çekme ve işlem geçmişini görüntüleme seçenekleri sunar. Kullanıcı seçimine göre işlemler yapılır ve bakiye güncellenir.

def sifre_kontrol(hesaplar, kart_no, sifre):
    if kart_no in hesaplar:
        if hesaplar[kart_no]["sifre"] == sifre:
            return True
        print("Hatalı şifre!")
    else:
        print("Kart numarası bulunamadı!")
    return False


def bakiye_goster(hesap):
    print(f"\nBakiyeniz: {hesap['bakiye']} TL")


def para_yatir(hesap, miktar):
    if miktar <= 0:
        print("Geçersiz miktar!")
        return
    hesap["bakiye"] += miktar
    hesap["gecmis"].append(f"Para Yatırma  : +{miktar} TL  → Yeni Bakiye: {hesap['bakiye']} TL")
    print(f"{miktar} TL yatırıldı. Yeni bakiye: {hesap['bakiye']} TL")


def para_cek(hesap, miktar):
    if miktar <= 0:
        print("Geçersiz miktar!")
        return
    if miktar > hesap["bakiye"]:
        print("Yetersiz bakiye!")
        return
    hesap["bakiye"] -= miktar
    hesap["gecmis"].append(f"Para Çekme    : -{miktar} TL  → Yeni Bakiye: {hesap['bakiye']} TL")
    print(f"{miktar} TL çekildi. Yeni bakiye: {hesap['bakiye']} TL")


def para_transfer(hesaplar, hesap, miktar):
    if miktar <= 0:
        print("Geçersiz miktar!")
        return
    if miktar > gonderen["bakiye"]:
        print("Yetersiz bakiye!")
        return

    alici_kart = input("Alıcı kart numarası: ")
    if alici_kart not in hesaplar:
        print("Alıcı hesap bulunamadı!")
        return

    alici = hesaplar[alici_kart]

    gonderen["bakiye"] -= miktar
    alici["bakiye"]    += miktar

    gonderen["gecmis"].append(f"Transfer Gönderme: -{miktar} TL  → {alici['isim']}  | Yeni Bakiye: {gonderen['bakiye']} TL")
    alici["gecmis"].append(f"Transfer Alma     : +{miktar} TL  ← {gonderen['isim']} | Yeni Bakiye: {alici['bakiye']} TL")

    print(f"{alici['isim']} adlı hesaba {miktar} TL transfer edildi.")
    print(f"Yeni bakiyeniz: {gonderen['bakiye']} TL")


def gecmis_goster(hesap):
    if not hesap["gecmis"]:
        print("Henüz işlem yapılmadı.")
        return
    print("\n--- İŞLEM GEÇMİŞİ ---")
    for i, islem in enumerate(hesap["gecmis"], 1):
        print(f"{i}. {islem}")


def hesap_olustur(hesaplar):
    print("\n--- YENİ HESAP OLUŞTUR ---")
    kart_no = input("Yeni kart numarası: ")
    if kart_no in hesaplar:
        print("Bu kart numarası zaten mevcut!")
        return
    isim  = input("Ad Soyad: ")
    sifre = input("Şifre (4 haneli): ")
    if len(sifre) != 4 or not sifre.isdigit():
        print("Şifre 4 haneli rakamdan oluşmalı!")
        return
    hesaplar[kart_no] = {
        "sifre"  : sifre,
        "bakiye" : 0,
        "isim"   : isim,
        "gecmis" : []
    }
    print(f"Hesap oluşturuldu! Hoş geldiniz, {isim}!")


def tum_hesaplari_listele(hesaplar):
    print("\n--- MEVCUT HESAPLAR ---")
    for kart, bilgi in hesaplar.items():
        print(f"Kart: {kart} | İsim: {bilgi['isim']:10} | Bakiye: {bilgi['bakiye']} TL")


def giris_ekrani(hesaplar):
    while True:
        print("\n========== BANKAMATIK ==========")
        print("1. Giriş Yap")
        print("2. Yeni Hesap Oluştur")
        print("3. Tüm Hesapları Listele")
        print("4. Çıkış")

        secim = input("Seçiminiz: ")

        if secim == "1":
            kart_no = input("Kart numaranızı girin: ")
            sifre   = input("Şifrenizi girin: ")
            if sifre_kontrol(hesaplar, kart_no, sifre):
                hesap_menusu(hesaplar, hesaplar[kart_no])
        elif secim == "2":
            hesap_olustur(hesaplar)
        elif secim == "3":
            tum_hesaplari_listele(hesaplar)
        elif secim == "4":
            print("Güle güle!")
            break
        else:
            print("Geçersiz seçim!")


def hesap_menusu(hesaplar, hesap):
    print(f"\nHoşgeldiniz {hesap['isim']}!")
    while True:
        print("\n1. Bakiye Göster")
        print("2. Para Yatır")
        print("3. Para Çek")
        print("4. Para Transferi")
        print("5. İşlem Geçmişi")
        print("6. Çıkış")
        secim_hesap = input("Lütfen bir seçenek seçiniz: ")

        if secim_hesap == "1":
            bakiye_goster(hesap)
        elif secim_hesap == "2":
            miktar = float(input("Yatırmak istediğiniz miktarı giriniz: "))
            para_yatir(hesap, miktar)
        elif secim_hesap == "3":                                           
            miktar = float(input("Çekmek istediğiniz miktarı giriniz: "))
            para_cek(hesap, miktar)
        elif secim_hesap == "4":                                           
            alici_kart = input("Alıcı kart numarasını giriniz: ")         

            if alici_kart not in hesaplar:
                print("Alıcı kart numarası bulunamadı!")
                continue
            alici_hesap = hesaplar[alici_kart]                           
            miktar = float(input(f"{alici_hesap['isim']} hesabına transfer miktarı: "))
            para_transfer(hesap, alici_hesap, miktar)
        elif secim_hesap == "5":
            islem_gecmisi_goster(hesap)
        elif secim_hesap == "6":
            print("Çıkış yapılıyor...")
            break
        else:
            print("Geçersiz seçenek. Lütfen tekrar deneyiniz.")


def bankamatik():
    hesaplar = {
        "2334": {"sifre": "1234", "bakiye": 9999, "isim": "Beytullah",    "gecmis": []},
        "2932": {"sifre": "5678", "bakiye": 50000, "isim": "Yaşar",   "gecmis": []},
        "3243": {"sifre": "9999", "bakiye": 25000, "isim": "Filiz", "gecmis": []},
    }
    giris_ekrani(hesaplar)


bankamatik()
