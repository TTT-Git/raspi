#必要なモジュールをインポート
import spidev                       #SPI通信用のモジュールをインポート
import time                         #時間制御用のモジュールをインポート
import sys                          #sysモジュールをインポート
import pandas as pd


#SPI通信を行うための準備
spi = spidev.SpiDev()               #インスタンスを生成
spi.open(0, 0)                      #CE0(24番ピン)を指定
spi.max_speed_hz = 1000000          #転送速度 1MHz
spi.bits_per_word=8

print('start... 30sec left')

def measure():
    dummy = 0xff
    start = 0x47
    sgl = 0x20
    msbf = 0x08
    ch = 0x10
    ad = spi.xfer2([( start + sgl + ch + msbf ), dummy])
    val = (((( ad[0] & 0x03) << 8) + ad[1]) * 3.3 ) / 1023
    return val

# start pulse check of 30sec
pulsecount = 0
prevpulse = 0
pulse_data = []
start = time.time()
for i in range(3000):
    mes_ch = measure()
    print( 'ch = %2.2f' % mes_ch,'[V]')

    if (i == 100):
        print('******************* 20sec left')
    if (i == 200):
        print('******************* 10sec left')
    if (i == 250):
        print('******************* 5sec left')
    # pulse count
    
    if (float(prevpulse) < 2.8 and float(mes_ch) >= 2.8):
        pulsecount = pulsecount + 1
        print('******************* pulsecount = %d' % pulsecount)

    prevpulse = mes_ch
    t = time.time() - start
    pulse_data.append({'time':t, 'v':mes_ch})
   # sleep 0.1sec
    time.sleep(0.01)

# create kitnone request body
request_body = {
    "pulse": {
        "value": pulsecount * 2
    }
}
df = pd.DataFrame(pulse_data)
df.to_csv('data/pulse.csv')

# post kintone request
# post_record_resp = kintone.post_record(kintone_appid, request_body)

print(pulse_data)
print(request_body)
print('finish')
spi.close()