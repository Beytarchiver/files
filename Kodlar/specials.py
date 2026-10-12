myList = [1, 2, 3]
# myString = "my string"

# print(len(myList))
# print(len(myString))   # burdaki len methodu her obje için farklı çalışır.    
# print(type(myList))
# print(type(myString))

class Movie():
    def __init__(self, title, director, duration):
        self.title = title
        self.director = director
        self.duration = duration
        print("Movie object was created. ")

    def __str__(self):
        return f"{self.title} by {self.director}"


    def __len__(self):
        return self.duration

    def __del__(self):
        print("Movie was deleted")

m = Movie("Movie name", "Director name", 120)

# print(str(myList))
print(str(m))
# print(len(myList))
# print(len(m))

del m

# Diğer special methods icin python special methods list yazıp bakılabilir.