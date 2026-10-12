
# try:

#     x = int(input("x="))
#     y = int(input("y="))
#     print(x/y)
# except (ZeroDivisionError, ValueError) as e:
#     print("Yanlıs bilgi girdiniz")
#     print(e)

while True:
    try:
        x = int(input("x="))
        y = int(input("y="))
        print(x/y)
    except Exception as ex:
        print("Yanlıs bilgi girdiniz")
    else:
        break
    finally:
        print("try except sonlandı. ")



    