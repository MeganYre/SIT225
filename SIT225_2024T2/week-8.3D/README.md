# D6 — Annotate smartphone accelerometer data with activity images

## What this folder does

1. Stream phone accelerometer (X/Y/Z) via Arduino IoT Cloud into Python  
2. Every **10 seconds**, plot that window, snap a **webcam** photo, show both on Dash  
3. Save matching files: `captures/1_yyyymmddHHMMss.csv` + `.jpg`  
4. Annotate images → `annotations.csv`  
5. Analyse patterns across **no-activity / waving / shaking**

## Setup

```powershell
cd "C:\Users\HP\OneDrive - Deakin University\Documents\Deakin\SIT225-Data Capture Technologies\D6"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy arduino_secrets.example.py arduino_secrets.py
# Edit arduino_secrets.py with your Arduino Cloud Device ID + Secret Key
```

Confirm Cloud variable names in `capture_dashboard.py` match your Thing:
`accelerometer_x`, `accelerometer_y`, `accelerometer_z` (change `VAR_X/Y/Z` if needed).

## Record (30+ minutes)

1. Phone streaming to Arduino IoT Cloud (Week 8 setup)  
2. Sit in front of the laptop camera with the phone in hand  
3. Run:

```powershell
python capture_dashboard.py
```

Open http://127.0.0.1:8050  

Alternate balanced blocks (~equal time each):

| Label | Activity |
|------:|----------|
| 0 | no-activity (still) |
| 1 | waving |
| 2 | shaking |

Keep going **> 30 minutes**. Files appear under `captures/`.

**Demo without phone/Cloud** (tests webcam + saving only):

```powershell
python capture_dashboard.py --demo
```

## Annotate

```powershell
python annotate.py
```

Open http://127.0.0.1:8051 → pick label per image → **Save annotations.csv**.

If a photo is unclear, open the matching `.csv` (or run analysis) and use the motion pattern.

## Analyse (steps 7–8)

```powershell
python analyse_activities.py
```

Prints class feature means and writes:

- `graphs/class_feature_comparison.png`  
- `graphs/example_windows_by_class.png`  

Use those numbers/plots in your report contrasts:
1. no-activity vs waving  
2. no-activity vs shaking  
3. waving vs shaking  

## Why 10-second windows

Enough time for one clear gesture in frame, and short enough to collect many balanced samples in a 30+ minute session (about 6 windows per minute).

## Files to submit / put in the report

- `capture_dashboard.py` (and helpers)  
- Sample `captures/*` pairs  
- `annotations.csv`  
- Analysis graphs + short written pattern discussion  
- Screenshots of the live Dash page (graph + image)
