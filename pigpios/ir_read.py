from irrp_m import IRRP

save_file = "codes_aircon"  #保存先のファイル名（パス）
post_time = 130  #これ以上途切れたらコードが終了したと判断する時間
no_confirm = True

gpio = 18  #GPIOピンの番号
id_ = "cooler:27_wind:auto"  #コマンドにつける名前

ir = IRRP(file=save_file, post=post_time, no_confirm=no_confirm)  #インスタンス化、設定できる値はプログラムの方を見て

ir.Record(GPIO=gpio, ID=id_)  #受信、保存、バックアップ  #ここからも保存ファイルとかpre、postの時間の値を設定できる
ir.stop()  #クラス内でpigpio.Piのインスタンスができているので終了する。