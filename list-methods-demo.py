years = ["1998","1998","1889","1932"]
games = ["Valorant","The Witcher","NFS","Watching Dogs"]
result = "1990"
years.append(result)
print(years)
result = ["1923"] + years
print(result)
years.remove("1998")
print(years)
indeks = result.index("1889")
print(indeks)
print("1932" in years)
years.reverse()
print(years)
years.sort()
print(years)
games.sort()
print(games)
str = "Toyota,Renault"
result = str.split(",")
print(result)
val = min(years)
print(val)
val = max(years)
print(val)
result = years.count("1998")
print(result)
years.clear()
print(years)
isimler = []
isim = input("isim: ")
isimler.append(isim)
print(isim)
