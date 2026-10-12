import random

value = random.random()
value = random.randint(1, 10)
value = random.randrange(1, 10)
value = random.uniform(1, 10)
value = int(random.random() * 10)

greetings = ["Hello", "Hi", "Hola", "Bonjour", "Ciao"]
names = ["John", "Mary", "Peter", "Anna", "Mark"]
value = random.choice(names)
# value = names[random.randint(0, len(names) - 1)]
value = random.choice(names)
value = random.choice(greetings)

liste = list(range(10))
random.shuffle(liste)

value = liste   

liste = range(100)
value = random.sample(liste, 5)

value = random.sample(names, 3)

print(value)
