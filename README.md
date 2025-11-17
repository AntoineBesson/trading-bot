# trading-bot
This project is my first time tackling a trading bot. 

Data Handler: Connects to the broker's API (e.g., Alpaca) to get a live, real-time data feed.

Strategy Engine: Runs your math model (e.g., the HMM or the O-U process) on the live data to generate a signal (e.g., BUY, SELL, HOLD).

Execution Handler: When the Strategy Engine generates a signal, this module forms a proper order (e.g., "BUY 100 shares of AAPL at market") and sends it to the broker's API.

Position Manager: Keeps track of your current holdings, cash balance, and live Profit & Loss (P&L).