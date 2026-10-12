# def check_password(psw):
#     import re
    
#     if len(psw) < 8:
#         raise Exception("Şifre en az 8 karakter olmalıdır.")
#     elif not re.search(r"[A-Z]", psw):
#         raise Exception("Şifre en az bir büyük harf içermelidir.")
#     elif not re.search(r"[a-z]", psw):
#         raise Exception("Şifre en az bir küçük harf içermelidir.")
#     elif not re.search(r"[0-9]", psw):
#         raise Exception("Şifre en az bir rakam içermelidir.")
#     else:
#         return True
        


# password = "12345678"

# try:
#     check_password(password)
# except Exception as e:
#     print(e)
# else:
#     print("Şifre doğrulandı.")
# finally:
#     print("Programın sonunda geri dönüyor.")

class Person:
    def __init__(self, name, age):
        if len(name) < 2:
            raise Exception("Ad en az 2 karakter olmalıdır.")
        else:
            self.name = name

p = Person("Ahmet", 20)

try:
    p.name = "Ahmet"
except Exception as e:
    print(e)
else:
    print("Ad değiştirildi.")
finally:
    print("Programın sonunda geri dönüyor.")
