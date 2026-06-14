# raspi
raspi用のコードです。

## dht22
Please install CircuitPython-DHT library.
https://learn.adafruit.com/dht-humidity-sensing-on-raspberry-pi-with-gdocs-logging/python-setup
pip3 install adafruit-circuitpython-dht

'''
pip3 install adafruit-circuitpython-dht
sudo apt-get install libgpiod2
'''

## setting.ini
使うデバイスを1にする。
GPIO番号を設定する。
結果を保存するパスを設定する。


## heart beat
raspi-config でSPIを有効にする。
pip3 install spidev

## エアコン制御システムの運用方法

### 現在の基本仕様

- `test_veiws.py`は温度・湿度・CO2などのセンサー値を取得し、SQLite DBへ保存します。
- `test.py`はWeb UI/APIサーバーを起動します。
- エアコン制御スレッドの開始、停止、二重起動防止、状態管理は`AirconStream`が行います。
- `test.py`の起動直後は、エアコン制御は開始されません。
- ブラウザの「開始」ボタン、または`POST /api/aircon/start/`で制御を開始します。
- ブラウザの「停止」ボタン、または`POST /api/aircon/stop/`で制御を停止し、エアコンOFF信号を送信します。
- 開始ボタンを連打しても、制御スレッドは二重起動しません。
- 停止完了後は、再度開始できます。

### 通常起動

Raspberry Pi上で、センサー取得プロセスとWeb UI/APIサーバーをそれぞれ起動します。
ログは`log/`配下へ保存します。

```bash
cd ~/raspi
mkdir -p log

nohup python3 -u test_veiws.py > log/test_veiws_manual_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo "test_veiws.py pid=$!"

nohup python3 -u test.py > log/test_manual_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo "test.py pid=$!"
```

### 起動確認

```bash
pgrep -af "test.py|test_veiws.py|libgpiod_pulsein"
curl http://localhost:8080/api/aircon/status/
```

`test.py`起動直後の`status`の期待状態は次のとおりです。

```json
{
  "state": "stopped",
  "running": false,
  "thread_alive": false,
  "stop_requested": false
}
```

### エアコン制御の開始

ブラウザの「開始」ボタン、または次のAPIで制御を開始します。

```bash
curl -X POST http://localhost:8080/api/aircon/start/
curl http://localhost:8080/api/aircon/status/
```

開始後の`status`の期待状態は次のとおりです。

```json
{
  "state": "running",
  "running": true,
  "thread_alive": true,
  "stop_requested": false
}
```

### エアコン制御の停止

ブラウザの「停止」ボタン、または次のAPIで制御を停止します。

```bash
curl -X POST http://localhost:8080/api/aircon/stop/
sleep 1
curl http://localhost:8080/api/aircon/status/
```

停止操作では制御スレッドを停止するだけでなく、エアコンOFF信号も送信します。
停止完了後の`status`の期待状態は次のとおりです。

```json
{
  "state": "stopped",
  "running": false,
  "thread_alive": false,
  "stop_requested": false
}
```

### プロセスの手動停止・再起動

プロセス自体を停止する場合は、次のコマンドを使用します。

```bash
pkill -f "python3 -u test.py"
pkill -f "python3 -u test_veiws.py"
pkill -f "libgpiod_pulsein"

pgrep -af "test.py|test_veiws.py|libgpiod_pulsein"
```

停止後に再起動する場合は、「通常起動」の手順を再度実行します。

### ログ確認

手動運用時のログは`log/`配下へ出力します。

```bash
ls -lt log | head
tail -f log/test_manual_YYYYMMDD_HHMMSS.log
tail -f log/test_veiws_manual_YYYYMMDD_HHMMSS.log
```

実際の日時部分は、`ls -lt log`で確認したファイル名へ置き換えてください。

### DBロック対策

- SQLiteが一時的に`database is locked`になっても、温度取得プロセスやエアコン制御スレッドは終了しません。
- DBロック時は回数制限付きでリトライします。
- リトライ上限を超えた場合は、その周期のDB書き込みまたは制御だけをスキップし、次周期で処理を継続します。
- ログに`database_locked_retry`や`database_locked_skipped`が出ることがあります。
- これらはプロセスの異常終了ではなく、DBロック中も継続運用するための記録です。

### DBバックアップ時の注意

SQLiteはWALモードを使用します。稼働中は、DB本体に加えて次のファイルが存在する場合があります。

- `temp_humid.sql-wal`
- `temp_humid.sql-shm`

稼働中の`temp_humid.sql`本体だけを単純コピーすると、最新データを含まない、または整合しないバックアップになる可能性があります。
バックアップにはSQLite Backup APIまたはSQLite CLIの`.backup`相当の方法を使用してください。

### GitHubから最新版を反映

`main`へマージ済みの最新版をRaspberry Piへ反映し、実行前に構文を確認します。

```bash
cd ~/raspi
git switch main
git pull --ff-only
python3 -m py_compile test.py controllers/aircon_stream.py controllers/webserver.py models/base.py models/ai_aircon_ctrl.py test_veiws.py
```

### 注意事項

- `test.py`起動直後は自動制御を開始しません。
- 自動制御を開始するには、ブラウザの開始ボタンまたは開始APIを使用してください。
- 停止ボタンと停止APIは、制御スレッドの停止要求に加えてエアコンOFF信号を送信します。
- 実機で開始・停止を確認する際は、赤外線信号が送信される可能性があります。
- 長期運用は将来的にsystemd化する予定です。現時点では手動または`nohup`で運用します。

### 実機確認済み事項

- Raspberry Pi実機で、起動直後が停止状態になることを確認済みです。
- 開始APIで`running`になることを確認済みです。
- 開始操作を連打しても、制御スレッドが二重起動しないことを確認済みです。
- 停止APIで`stopped`になり、停止完了後に停止要求フラグが解除されることを確認済みです。
- 停止後に再開始できることを確認済みです。
