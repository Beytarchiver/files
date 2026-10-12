x = "global x"

def function():
    x = "local x"
    print(x)

function()
print(x) 


################################

# Global

name = "Beytullah"
def change_name(new_name):
    # Local name,

    name = new_name
    print(name)

change_name("Ahmet")
print(name)  

################################

name = "Global String"
def greeting():
    name = "Local String"

    def hello():
        print("Hello " + name)
    hello()
greeting()

################################

x = 50
def test():
    global x 
    
    print(f"x : {x}")
    x = 100
    print(f"changed x to {x}")
test()
print(x)