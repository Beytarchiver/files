class Soru:
    def __init__(self, soru, secenekler, dogru_cevap):
        self.soru = soru
        self.secenekler = secenekler
        self.dogru_cevap = dogru_cevap

    def sor(self):
        print(f"\n{self.soru}")
        for i, secenek in enumerate(self.secenekler, 1):
            print(f" {i}. {secenek}")

    def kontrol_et(self, cevap):         
        return cevap == self.dogru_cevap


class Quiz:
    def __init__(self, baslik):
        self.baslik = baslik
        self.sorular = []
        self.puan = 0

    def soru_ekle(self, soru, secenekler, dogru_cevap):
        yeni_soru = Soru(soru, secenekler, dogru_cevap)   
        self.sorular.append(yeni_soru)

    def baslat(self):
        print(f"\n======== {self.baslik} ========")        
        print(f"Toplam {len(self.sorular)} soru bulunmaktadır.")
        print("Cevaplamak için seçeneğin numarasını giriniz.")

        for i, soru in enumerate(self.sorular, 1):
            print(f"\n[Soru {i}/{len(self.sorular)}]")
            soru.sor()

            while True:
                try:
                    cevap = int(input("Cevabınız: "))
                    if 1 <= cevap <= len(soru.secenekler):
                        break
                    print(f"Lütfen 1 ile {len(soru.secenekler)} arasında bir sayı giriniz.")
                except ValueError:
                    print("Lütfen bir sayı giriniz.")

            if soru.kontrol_et(cevap):
                print("Doğru!")
                self.puan += 1
            else:
                print(f"Yanlış! Doğru cevap: {soru.secenekler[soru.dogru_cevap - 1]}")

        self.sonuc_goster()

    def sonuc_goster(self):
        toplam = len(self.sorular)
        yuzde = (self.puan / toplam) * 100
        print("\n========== SONUÇ ==========")
        print(f"Doğru : {self.puan} / {toplam}")
        print(f"Puan  : %{yuzde:.1f}")

        if yuzde == 100:
            print("Mükemmel! Tüm soruları doğru cevapladınız!")
        elif yuzde >= 70:    
            print("İyisin! Az daha çabalarsan tüm soruları doğru cevaplayabilirsin!")
        elif yuzde >= 50:     
            print("İdare eder! Çalışmaya devam et!")
        else:
            print("Sanki bu sonuç kötü oldu gibi... olsun bidakine tüm soruları doğru cevaplarsın!")


quiz = Quiz("Python Bilgi Testi")

quiz.soru_ekle(
    "Python'da bir listeye eleman eklemek için hangi metot kullanılır?",
    ["insert()", "append()", "add()", "push()"],
    dogru_cevap=2
)
quiz.soru_ekle(                              
    "Aşağıdakilerden hangisi Python'da geçerli bir değişken adıdır?",
    ["1sayi", "sayi-1", "sayi_1", "sayi 1"],
    dogru_cevap=3
)
quiz.soru_ekle(
    "Python'da bir fonksiyon tanımlamak için hangi anahtar kelime kullanılır?",
    ["function", "def", "fun", "define"],
    dogru_cevap=2
)
quiz.soru_ekle(
    "range(5) kaç eleman üretir?",
    ["4", "5", "6", "3"],
    dogru_cevap=2
)
quiz.soru_ekle(
    "Python'da sınıf oluşturmak için hangi anahtar kelime kullanılır?",
    ["object", "struct", "class", "type"],
    dogru_cevap=3
)

quiz.baslat()