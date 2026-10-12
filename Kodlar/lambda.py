# def square(num): return num ** 2
 

# numbers = [1, 3, 5, 9]
# result = list(map(lambda x: x ** 2, numbers))

# # for item in map(square, numbers):
# #     print(item)       # 2. yol olarak da yazabiliriz.



# print(result)



def check_even(num): return num % 2 == 0
# list(filter(check_even, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
# print(list(filter(check_even, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10])))
result = list(filter(lambda x: x % 2 == 0, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
print(result)
