print("=" * 40)
print("Asal Sayı Bulma Programı")
print("=" * 40)

sayi = int(input("Sayi giriniz: "))

if sayi <= 1:
    print(f"{sayi} bir asal sayı değildir. ")
else:
    asal_mi = True
    bolen = 2
    while bolen < sayi:
        if sayi % bolen == 0:
            asal_mi = False
            break
            
            
            
        bolen += 1
    if asal_mi:
        print(f"{sayi} bir ASAL sayıdır! ")
    else:
        print(f"{sayi} bir ASAL sayı değildir! ")


