""
      
      
students = {
        "233": {
        "name" : "Muhammet",
        "surname" :"Tayyar",
        "phone" :"0538 003 444",
         },
     "444":  {
            "name": "Hayri",
            "surname":"Contar",
            "phone":"0532 500 850",
        },
        "456":  {
        "name":"Kasim",
        "surname":"Muratoglu",
       "phone":"0530 655 830",
         },
     }


print(students)
students = {}
number = input("students numbers: ")
name = input("name: ")
surname = input("surname: ")
phone = input("phone: ")
# students[number] = {
#     "name": name,
#     "surname": surname,
#     "phone": phone

# }


students = {}


number = input("Student number: ")
name = input("Name: ")
surname = input("Surname: ")
phone = input("Phone: ")

students.update({
    number: {
          "name": name,
          "surname": surname,
          "phone number": phone
    }
})
print("\nGüncel Sözlük (1 Öğrenci):", students)
print("-" * 30)


number = input("Student number: ")
name = input("Name: ")
surname = input("Surname: ")
phone = input("Phone: ")

students.update({
    number: {
          "name": name,
          "surname": surname,
          "phone number": phone
    }
})
print("\nGüncel Sözlük (2 Öğrenci):", students)


number = input("Student number: ")
name = input("Name: ")
surname = input("Surname: ")
phone = input("Phone: ")

students.update({
    number: {
          "name": name,
          "surname": surname,
          "phone number": phone
    }
})


print("\nSon Durum - Tüm Öğrenciler:")
print(students)

ogrNo = input("ogrNo: ")
ogrenci = students[number]

print(f"Aradiğiniz {ogrNo} nolu ogrencinin adi: {ogrenci["name"]}, soyadi:{ogrenci["surname"]}, telefon numarasi: {ogrenci["phone number"]}")













    
