# นายนพดล เพ่งพิศ 6604101404

#ไม่ต้องใช้ global variables เพราะทุกอย่างอยู่ในคลาสหมด
#ฟังก์ชันดึงข้อมูล, คำนวณ indicator, ซื้อ/ขาย, ปิด ทุกอย่างกลายเป็น เมธอดของ bot
#ลดโค้ดซ้ำ เช่น get_market_data() ช่วยดึงข้อมูลและคำนวณ indicator ในที่เดียว
#ถ้าต้องการสร้าง bot เพิ่มอีกตัว ก็แค่สร้าง instance ใหม่ ไม่กระทบตัวเก่า
#เราสร้าง คลาส CryptoStrategyBot เก็บทุกอย่างที่ bot ต้องใช้
#สำหรับแต่ละสัญลักษณ์ (เช่น BTCUSD) เราสร้าง instance ของ CryptoStrategyBot
#จากนั้นสร้าง Thread แยกสำหรับ bot แต่ละตัว และเรียก bot.run()
#bot แต่ละตัวจะดึงข้อมูล, คำนวณ Indicator, ตรวจสอบสัญญาณ และส่งคำสั่งเทรดพร้อมกัน
#main program ยังสามารถรัน logic อื่น ๆ ไปพร้อมกัน
#Main Program
#|
#|-- Thread 1 --> CryptoStrategyBot(symbol="BTCUSD").run()
#| |--> get_market_data()
#| |--> calculate MA & RSI
#| |--> check_signal() (Buy/Close)
#|
#|-- Thread 2 --> CryptoStrategyBot(symbol="ETHUSD").run()
#|--> get_market_data()
#|--> calculate MA & RSI
#|--> check_signal() (Buy/Close)
# แต่ละ Thread ทำงาน อิสระต่อกัน
# CryptoStrategyBot แต่ละตัวเหมือน นักวิเคราะห์ทางเทคนิคแยกกัน แต่ใช้ MT5 client เดียว






import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import time
import threading
import os # เพิ่ม import os

# ==============================================================================
# == CLASS DEFINITION: CryptoStrategyBot (ประกาศคลาสเพียงครั้งเดียว)
# ==============================================================================
class CryptoStrategyBot:
    """
    บอทเทรดคริปโตบน MT5 โดยใช้กลยุทธ์ MA ตัดกับ RSI
    """
    def __init__(self, path, login, server, password, symbol, volume,
                 timeframe=mt5.TIMEFRAME_M15,
                 ma_period=50,
                 rsi_period=14,
                 rsi_overbought=70,
                 rsi_oversold=30):

        # ---- ส่วนเชื่อมต่อ ----
        self.path = path
        self.login = login
        self.server = server
        self.password = password
        self.symbol = symbol
        self.volume = volume

        # ---- Parameters สำหรับกลยุทธ์ ----
        self.timeframe = timeframe
        self.ma_period = ma_period
        self.rsi_period = rsi_period
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold

        # ---- ตัวแปรภายในคลาส ----
        self.is_connected = False
        self._connect() # เรียกใช้เมธอดเชื่อมต่อ

    # --- เมธอดทั้งหมดจะถูกจัดเรียงอยู่ภายในคลาสนี้ ---

    def _connect(self):
        """เมธอดสำหรับเชื่อมต่อกับ MT5"""
        if mt5.initialize(path=self.path, login=self.login, server=self.server, password=self.password):
            print(f"[{self.symbol}] เชื่อมต่อ MT5 สำเร็จ")
            self.is_connected = True
        else:
            print(f"[{self.symbol}] เชื่อมต่อ MT5 ล้มเหลว, retcode = {mt5.last_error()}")
            self.is_connected = False

    def get_market_data(self, count=100):
        """ดึงข้อมูลแท่งเทียนย้อนหลังและคำนวณ Indicators"""
        try:
            rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, count)
            if rates is None:
                print(f"[{self.symbol}] ไม่สามารถดึงข้อมูลราคาได้")
                return None

            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df = df.set_index('time')

            # --- คำนวณ Indicators ด้วย pandas_ta ---
            # จะสร้างคอลัมน์ใหม่ตามชื่อ Indicator เช่น 'SMA_50' และ 'RSI_14'
            df.ta.sma(length=self.ma_period, append=True)
            df.ta.rsi(length=self.rsi_period, append=True)

            return df
        except Exception as e:
            print(f"[{self.symbol}] เกิดข้อผิดพลาดในการดึงข้อมูล: {e}")
            return None

    def check_signal(self):
        """ตรวจสอบสัญญาณ Buy/Sell/Close จากข้อมูลล่าสุด"""
        df = self.get_market_data()
        if df is None or len(df) < max(self.ma_period, self.rsi_period):
            print(f"[{self.symbol}] ข้อมูลไม่เพียงพอสำหรับการคำนวณ")
            return "NO_DATA"

        last_candle = df.iloc[-2] # ใช้แท่งเทียนที่ปิดแล้วล่าสุด

        current_positions = mt5.positions_get(symbol=self.symbol)
        has_open_position = len(current_positions) > 0

        # --- ตรรกะการเทรด ---
        ma_col = f'SMA_{self.ma_period}'
        rsi_col = f'RSI_{self.rsi_period}'

        # เงื่อนไขปิดสถานะ (เช็คก่อนเสมอ)
        if has_open_position and current_positions[0].type == mt5.ORDER_TYPE_BUY:
            if last_candle['close'] < last_candle[ma_col]:
                return "CLOSE_BUY"

        # เงื่อนไขเปิดสถานะ (เมื่อยังไม่มี position)
        if not has_open_position:
            if (last_candle['close'] > last_candle[ma_col] and
                last_candle[rsi_col] < self.rsi_overbought):
                return "BUY"

        return "HOLD"

    def execute_trade(self, signal):
        """ส่งคำสั่งเทรดตามสัญญาณที่ได้รับ"""
        if signal == "BUY":
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                print(f"[{self.symbol}] ไม่สามารถดึงราคา Tick ได้")
                return

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": self.volume,
                "type": mt5.ORDER_TYPE_BUY,
                "price": tick.ask,
                "deviation": 20,
                "magic": 2023,
                "comment": "Python MA/RSI Bot",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            print(f"[{self.symbol}] สัญญาณ BUY -> ส่งคำสั่งซื้อ -> Result: {result.comment if result else 'Failed'}")

        elif signal == "CLOSE_BUY":
            positions = mt5.positions_get(symbol=self.symbol)
            if not positions:
                return # ไม่มี position ให้ปิด

            position = positions[0]
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                print(f"[{self.symbol}] ไม่สามารถดึงราคา Tick ได้")
                return

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": position.ticket,
                "symbol": self.symbol,
                "volume": position.volume,
                "type": mt5.ORDER_TYPE_SELL, # ปิด Buy ต้องส่ง Sell
                "price": tick.bid,
                "deviation": 20,
                "magic": 2023,
                "comment": "Python MA/RSI Bot Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            print(f"[{self.symbol}] สัญญาณ CLOSE_BUY -> ส่งคำสั่งปิด -> Result: {result.comment if result else 'Failed'}")


    def run(self):
        """Main loop ของบอท"""
        if not self.is_connected:
            print(f"[{self.symbol}] ไม่สามารถเริ่มทำงานได้: การเชื่อมต่อล้มเหลว")
            return

        print(f"[{self.symbol}] Bot เริ่มทำงาน... Timeframe: {self.timeframe.name}, MA: {self.ma_period}, RSI: {self.rsi_period}")
        while True:
            try:
                # 1. ตรวจสอบสัญญาณ
                signal = self.check_signal()

                # 2. แสดงสถานะ
                if signal != "HOLD" and signal != "NO_DATA":
                    print(f"[{self.symbol}] พบสัญญาณ: {signal}")
                    # 3. ส่งคำสั่งเทรด
                    self.execute_trade(signal)

                # 4. หน่วงเวลา 1 นาที
                time.sleep(60)

            except Exception as e:
                print(f"[{self.symbol}] เกิดข้อผิดพลาดใน Main Loop: {e}")
                time.sleep(60)

# ==============================================================================
# == MAIN PROGRAM: ส่วนสำหรับรันบอท
# ==============================================================================
if __name__ == "__main__":
    # --- ตั้งค่า ---
    try:
        os.chdir("C:/Users/onyou/Downloads/grid/")
        key = open("xmkey.txt", "r").read().split()
        path = r"C:\Program Files\XM Global MT5\terminal64.exe"

        # --- สร้าง Bot สำหรับ BTCUSD ---
        btcusd_bot = CryptoStrategyBot(
            path=path,
            login=int(key[0]),
            server=key[1],
            password=key[2],
            symbol="BTCUSD",
            volume=0.01,
            timeframe=mt5.TIMEFRAME_H1, # เทรดที่กราฟ 1 ชั่วโมง
            ma_period=50,
            rsi_period=14
        )

        # --- เริ่มการทำงานของ Bot ใน Thread แยก ---
        btcusd_thread = threading.Thread(target=btcusd_bot.run, daemon=True)
        btcusd_thread.start()
        print("บอทเทรด BTCUSD กำลังทำงาน...")
        
        # (ตัวอย่าง) หากต้องการเพิ่มบอท ETHUSD ก็ทำเหมือนกัน
        # ethusd_bot = CryptoStrategyBot(...)
        # ethusd_thread = threading.Thread(target=ethusd_bot.run, daemon=True)
        # ethusd_thread.start()
        # print("บอทเทรด ETHUSD กำลังทำงาน...")

        # ทำให้โปรแกรมหลักทำงานต่อไปเรื่อยๆ
        while True:
            time.sleep(1)

    except FileNotFoundError:
        print("ข้อผิดพลาด: ไม่พบไฟล์ xmkey.txt หรือโฟลเดอร์ grid/")
    except Exception as e:
        print(f"เกิดข้อผิดพลาดร้ายแรง: {e}")