# week-8.2C — Smooth Plotly Dash accelerometer monitor

## Contents
- `smooth_dash.py` — reusable `run_smooth_dash()` wrapper (extendData + sliding window)
- `dash_accel_live.py` — Arduino Cloud / CSV demo app
- `data/accelerometer_xyz.csv` — sample continuous XYZ data
- `graphs/accelerometer_graphs.png` — generated accelerometer graphs
- `arduino_secrets.example.py` — template for Cloud credentials

## Run (demo)
```
pip install dash plotly arduino-iot-cloud
python dash_accel_live.py --demo
```
Open http://127.0.0.1:8050
