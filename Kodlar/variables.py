user1 = "Beytullah"
user2 = "Ahmet"
user3 = "Mehmet"
print(user1)
print(user2)
print(user3)
name = "Kamillerin İbrahim"
example = "My Brother"
print(name)
print(example)
a = 45
b = 13.56
print(a*b)
print(type(a*b))
maasAli = 10000
maasVeli = 20000
vergi = 0.27
print(maasAli - (maasAli * vergi))
print(maasVeli - (maasVeli * vergi))


# Değişken Tanımlama Kuralları

# Rakam ile başlayamaz

number1 = 10
print(number1)

number1 = 20
print(number1)

number1 += 30
print(number1)

# Tanımlarken Büyük Küçük Harf Duyarlılığı Vardır.

age = 12
AGE = 123
print(age)
print(AGE)

# Değişken Tanımlarken Türkçe Karakter Kullanılmamalıdır.

yas = 12
_age = 12

x = 12   # int
y = 21.43 # float
name = "Beytullah" # string
isStudent = True   # bool

 # x, y, name, isStudent = (12, 21.43, "Beytullah", True)


a = "23"
b = "112"
print(a+b) # 23112
firstName = "Beytullah"
LastName = " Yilmaz  "
print(firstName + LastName) # Beytullah Yilmaz

MüsteriAdi = "Beytullah"
MüsteriSoyadi = "Yilmaz"
MüsteriAdiSoyadi = MüsteriAdi + " " + MüsteriSoyadi
Müstericinsiyet = "Erkek"
MüsteriKimlikNo = "12345678901"
MüsteriDogumTarihi = "01.01.2000"
MüsteriAdres = "İstanbul"
MüsteriYas = 24
print(MüsteriAdiSoyadi)
print(Müstericinsiyet)
print(MüsteriKimlikNo)
print(MüsteriDogumTarihi)
print(MüsteriAdres)
print(MüsteriYas)


Siparis1 = 1123
Siparis2 = 1124
Siparis3 = 1125
SiparisToplam = Siparis1 + Siparis2 + Siparis3
print(SiparisToplam)