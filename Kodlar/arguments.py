# def changeName(old_name, new_name):
#        n = "Beytullah"

# name = "Kamil"

# changeName(name, "Ahmet")
# print(name)

# def change(n):
#     n[0] = "Samsun"
# sehirler = ["Ordu", "Trabzon", "Rize"]
# change(sehirler)
# print(sehirler)

def add (*params):
    # sum = 0

    # for i in params:
    #     sum = sum + n      # Diyez ile belirtilen sum kullanılmadan yapılan parametreye örnektir.
    #     return sum         
    
    
    
    print(params[0])
    print(params[1])
    return sum(params)
print(add(5, 6))
print(add(5, 6, 7))

def displayUser(**params):
    print(type(params))
    for key, value in params.items():
        print("{} is {}".format(key, value)) # İfadeler dictionary e denk gelir. Key ve value şeklinde yazdırılır.


displayUser(name = "Beytullah", age = 25, city = "Ordu", email = "beytullah@example.com")
displayUser(name = "Kamil", age = 30, city = "Trabzon", email = "kamil@example.com")
displayUser(name = "Ahmet", age = 35, city = "Rize", email = "ahmet@example.com")


def myFunc(a, b, *args, **kwargs):

    print(a)
    print(b)
    print(args)
    print(kwargs)

myFunc(10, 20, 30, 40, 50, key1 = "value1", key2 = "value2", key3 = "value3")