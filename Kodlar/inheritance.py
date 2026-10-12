# Inheritance (Kalıtım): Miras alma

# Person => name, lastname, age, run(), eat(), age

class Person():
    def __init__(self, fname, lname):
        self.firstName = fname
        self.lastName = lname
        print("Person Created")
    
    def who_am_i(self):
        print("I am a person")
    
    def sayHello(self):
        print("Hello! I'm a student.")

class Teacher(Person):
    def __init__(self, fname, lname, branch):
        super().__init__(fname, lname)
        self.branch = branch


    def who_am_i(self):
        print(f"Hello! I'm a new {self.branch} teacher in this school students.")


    def eat(self):
        print("I'm eating")


class Student(Person):
    def __init__(self, fname, lname, number):
        
        Person.__init__(self, fname, lname)
        self.studentNumber = number
        print("Student Created")
    
    # override
    def who_am_i(self):
        print("I'm a student")

p1 = Person("Ali", "Yılmaz")
s1 = Student("Beytullah", "Yılmaz", 844)
t1 = Teacher("Yaşar", "Yılmaz", "Math")


print(p1.firstName + " " + p1.lastName)
print(s1.firstName + " " + s1.lastName + " " + str(s1.studentNumber))
p1.who_am_i()
s1.who_am_i()
t1.eat()
s1.sayHello()
t1.who_am_i()