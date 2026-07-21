a, b, c = 31, 66, 22
# a, b = b, a
a = a+5
a +=5  # a= a+5
a -=15 # a= a-5
a *=43 # a= a*43
a **=3 # a= a nın küpü
a /=2 # a:2
a %= 10 # a%10
a //=5  # a//5

# print(a, b, c)

results = 1,2, 3
print(results)
print(type(results))

a, b, *c = results
print(a,b,c)
print(a,b,c[0])