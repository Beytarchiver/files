arabalar = ["MAZDA","LAMBORGHINI","MERCEDES","TOYOTA"]
result = len(arabalar)
result = arabalar[0]
result = arabalar[3]
result = arabalar[-1]
arabalar[-1]= "MCLAREN"
result = arabalar
result = "Mercedes" in arabalar
result = arabalar[-2]
result = arabalar[0:3]
result = arabalar[:3]
result = arabalar[:-2]
arabalar[-2:] = ["FERRARI","CİTROEN"]
result = arabalar
result = arabalar + ["SAAB", "SEAT"]
del arabalar[-1]
result = arabalar
result = arabalar[::-1]
studentA = ["Yaser","Yilmaz",2014,[60,160,98]]
studentB = ["Asim","Kara",2010,[49,178,89]]
studentC = ["Kasim","Muhbir",2001,[99,195,108]]
result = studentA[0]
result = studentB[1]
result = studentC[0][3]
result = f"{studentA[0]}{studentA[1]}{2014-studentA[2]} yasinda boy ortalamasi {studentA[3][0] + studentA[3][1] + studentA[3][2]//3}"
print(result)