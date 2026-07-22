k, l, m = 31, 66, 22
# k, l = l, k
l = l+5
l +=5  # l= l+5
l -=15 # l= l-5
l *=43 # l= l*43
l **=3 # l= l nın küpü
l /=2 # l:2
l %= 10 # l%10
l //=5  # l//5

# print(k, l, m)

results = 1,2, 3
print(results)
print(type(results))

a, b, *c = results
print(a,b,c)
print(a,b,c[0])