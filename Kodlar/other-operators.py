# Identity Operator: is

# a = b = [3,4,5]
# z = [8,9,10]

# print(a==b)
# print(a==z)
# print(a is z)
# print(a is b)

x = [1,2,3]
y = [2,4]


del x[2]
y[1] = 1
y.reverse()
print(x==y)
print(x is y)
print(x is not y)

# Membership Operator: in

x= ["watermelon","melon"]
print("melon" in x)
name = "Mustafa"
nachname = "Yilmaz"
print("Usta" in nachname)
print("Mustafa" in name)
