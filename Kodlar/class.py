# class
class Person:
    pass
    # class attributes
    address = "no information"
    # methods



    # constuctor (yapıcı metod)
    def __init__(self, name, year):
        # object attributes
        self.name = name
        self.year = year
        print("init metodu calıstı.")
    
    # methods
    
    
# object, (instance)


p1 = Person(name = "Beytullah", year = 1992)
p2 = Person(name ="Yekta", year = 1998)



# updating
p1.name = "Gabriel"
p1.address = "Samsun"
# accessing object attributes
print(f"p1 :name: {p1.name} year: {p1.year} address: {p1.address}")
print(f"p2 :name: {p2.name} year: {p2.year} address: {p2.address}")



print(p1)
print(p2)
print(type(p1))
print(type(p2))
print(p1 == p2)