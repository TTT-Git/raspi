# 室温制御システムの改善点

## 1. 目標温度範囲内でのエアコン制御

### 問題点
- 現在の実装では、温度が`temp_lower_limit`と`temp_upper_limit`の間にある場合、何も処理されない
- エアコンがオンのままになり、目標温度を超えて冷却/加熱が続く可能性がある

### 改善案
- 目標温度範囲内（`temp_lower_limit <= temperature <= temp_upper_limit`）の場合、エアコンをオフにする処理を追加
- または、現在の設定温度を維持しつつ、必要に応じて弱運転に切り替える

```python
# 改善例
if self.temp_lower_limit <= self.temperature <= self.temp_upper_limit:
    # 目標温度範囲内なので、エアコンをオフにする
    self.aircon.off()
    # または、現在のモードを維持しつつ弱運転にする
```

## 2. 積分項（I制御）の無効化

### 問題点
- 71行目で`corr = 0`に固定されている
- 過去10分の平均温度と目標温度の差を考慮するはずだったが、無効化されている
- 長期的な温度偏差が補正されない

### 改善案
- 積分項を有効化し、長期的な温度偏差を補正する
- ただし、積分項が大きくなりすぎないように上限を設定（アンチワインドアップ）

```python
# 改善例
corr = df2['temperature'].mean() - settings.target_temp
# 積分項の上限を設定（例: ±2度）
corr = max(-2.0, min(2.0, corr))
self.temperature = coef_1[0]*predict_time + coef_1[1] + corr
```

## 3. 設定温度の変更が大きすぎる

### 問題点
- `math.ceil(gap_temp)`で設定温度を変更しているため、温度差が大きい場合に急激に変化する
- 例: 温度差が3.5度の場合、設定温度が4度も変化する

### 改善案
- 設定温度の変更量を制限する（例: 最大1-2度/回）
- または、比例制御（P制御）を使用して、温度差に比例した変更量にする

```python
# 改善例
temp_change = min(2.0, gap_temp * 0.5)  # 最大2度、温度差の50%
self.heater_setting_temp = self.heater_setting_temp - math.ceil(temp_change)
```

## 4. ヒステリシス（履歴効果）の欠如

### 問題点
- 目標温度範囲の境界付近で頻繁にオン/オフが切り替わる可能性がある
- エアコンに負担がかかり、温度が安定しない

### 改善案
- オン/オフの切り替えに異なる閾値を設定する（ヒステリシス）
- 例: オンになる閾値とオフになる閾値を分ける

```python
# 改善例
# エアコンをオンにする閾値（より広い範囲）
on_upper_limit = self.target_temp + settings.temp_range + 0.5
on_lower_limit = self.target_temp - settings.temp_range - 0.5
# エアコンをオフにする閾値（より狭い範囲）
off_upper_limit = self.target_temp + settings.temp_range - 0.3
off_lower_limit = self.target_temp - settings.temp_range + 0.3
```

## 5. データ取得エラーのハンドリング

### 問題点
- 3分のデータが取得できない場合（データが少ない、データベースエラーなど）の処理がない
- エラーが発生すると予測温度が計算できず、制御が失敗する

### 改善案
- データが少ない場合のフォールバック処理を追加
- 最新の温度データを使用する、または前回の予測温度を使用する

```python
# 改善例
if len(df) < 3:  # データが3点未満の場合
    # 最新の温度データを使用
    temp_humid_data = temp_humid_cls.latest_record()
    if temp_humid_data:
        self.temperature = temp_humid_data.value['temperature']
        self.data_time = temp_humid_data.value['time']
    else:
        logger.warning("温度データが取得できませんでした")
        return  # 制御をスキップ
```

## 6. 制御間隔の最適化

### 問題点
- 制御間隔が短すぎるとエアコンに負担がかかる
- 長すぎると温度変化に対応できない

### 改善案
- 温度差に応じて制御間隔を調整する
- 温度差が大きい場合は短い間隔、小さい場合は長い間隔

```python
# 改善例
gap_temp = abs(self.temperature - self.target_temp)
if gap_temp > 2:
    sleep_interval = settings.time_interval_aircon_ai_sec  # 通常の間隔
elif gap_temp > 1:
    sleep_interval = settings.time_interval_aircon_ai_sec * 1.5  # 1.5倍
else:
    sleep_interval = settings.time_interval_aircon_ai_sec * 2  # 2倍
```

## 7. モード切り替え時の遷移

### 問題点
- 暖房から冷房への切り替えが急激（例: 96-99行目）
- エアコンに負担がかかり、温度が不安定になる可能性がある

### 改善案
- モード切り替え前に一度エアコンをオフにする
- または、切り替え時の設定温度を段階的に変更する

```python
# 改善例
if self.heater_mode and self.temperature > self.temp_upper_limit:
    # 暖房から冷房に切り替える前に、一度オフにする
    self.aircon.off()
    sleep(5)  # 5秒待機
    self.cooler_setting_temp = self.cooler_setting_upper_limit
    self.aircon.cooler(temp=self.cooler_setting_temp, fan='low')
    self.heater_mode = False
```

## 8. 予測精度の向上

### 問題点
- 3分のデータで1次フィッティングを行っているが、データが少ない場合に精度が低い
- 外乱（ドアの開閉、人の出入りなど）の影響を受けやすい

### 改善案
- より長い期間のデータを使用する（例: 5-10分）
- 移動平均を取る、または外れ値を除外する
- 複数の予測モデルを組み合わせる（アンサンブル）

## 9. ログとモニタリングの改善

### 問題点
- 制御の効果を評価するためのデータが不足している
- 温度の変動幅、制御回数、エアコンの稼働時間などの統計情報がない

### 改善案
- 温度の変動幅、制御回数、エアコンの稼働時間などの統計情報を記録
- グラフで可視化し、制御の効果を確認できるようにする

## 10. PID制御の導入

### 問題点
- 現在は比例制御（P制御）のみで、積分項（I制御）と微分項（D制御）がない
- より安定した制御が可能

### 改善案
- PID制御を実装する
- P（比例）: 現在の温度差
- I（積分）: 過去の温度差の累積
- D（微分）: 温度変化の速度

```python
# 改善例（簡易版）
class PIDController:
    def __init__(self, kp, ki, kd):
        self.kp = kp  # 比例ゲイン
        self.ki = ki  # 積分ゲイン
        self.kd = kd  # 微分ゲイン
        self.integral = 0
        self.prev_error = 0
    
    def calculate(self, current_temp, target_temp):
        error = target_temp - current_temp
        self.integral += error
        derivative = error - self.prev_error
        self.prev_error = error
        
        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        return output
```

## 優先度の高い改善項目

1. **目標温度範囲内でのエアコン制御** - エネルギー効率と温度安定性に直結
2. **データ取得エラーのハンドリング** - システムの安定性に重要
3. **設定温度の変更量の制限** - 急激な変化を防ぎ、エアコンに優しい
4. **ヒステリシスの導入** - 頻繁なオン/オフを防ぎ、温度を安定させる

## 実装の順序

1. まず、目標温度範囲内でのエアコン制御を追加
2. データ取得エラーのハンドリングを追加
3. 設定温度の変更量を制限
4. ヒステリシスを導入
5. その他の改善を段階的に実装



