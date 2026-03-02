# TuRAC – Dashboard and Control System

Author: Kodanda Ramudu Tailam  
Enrollment Number: 42732  
Project: TuRAC – Turbidostat Retrofit for Algae Cultures  
Course: Embedded Systems Project (ES-PROL / ESD2)

---

## 1. System Overview

This repository contains the integrated control and monitoring system developed for the TuRAC project.

The system provides:

• Real-time Optical Density (OD) acquisition  
• Arduino-based closed-loop control (Manual / Threshold / PID modes)  
• Pump actuation via relay or servo  
• 1 Hz data sampling with 1-minute averaging  
• CSV-based logging  
• Web-based dashboard for live monitoring  
• PID parameter update via dashboard interface  
• CSV export with date and time filtering  

The architecture follows:

OD Sensor → Arduino Controller → Serial Interface → Python Backend → Web Dashboard

---

## 2. Repository Structure


turac-dashboard-control/
│
├── frontend/ # Web dashboard (HTML + JS)
├── backend/ # Python server, logging, serial interface
├── arduino/ # Arduino firmware (PID-based control)
├── README.md
└── .gitignore


---

## 3. System Requirements

### Software

• Python 3.10 or higher  
• Arduino IDE 2.x  
• Google Chrome / Edge browser  
• Git (for version control)

### Python Packages

Install dependencies listed in:


backend/requirements.txt


---

## 4. Backend Setup and Execution

### Step 1 – Create Virtual Environment (Recommended)

Open terminal inside the backend folder:


cd backend
python -m venv .venv
.venv\Scripts\activate


### Step 2 – Install Dependencies


pip install -r requirements.txt


### Step 3 – Run Backend Server


python server.py


The backend will:

• Read OD values from Arduino via serial port  
• Compute 1-minute averages  
• Store timestamped CSV logs  
• Serve dashboard API endpoints  

---

## 5. Frontend Setup and Execution

Open the frontend folder.

If the dashboard is static (HTML + JS only):

Simply open:


index.html


in your browser.

If using Node-based tooling (if applicable):


npm install
npm start


The dashboard will display:

• Live OD values  
• Multi-channel monitoring (if enabled)  
• PID parameter input fields  
• CSV export options  

---

## 6. Arduino Firmware Upload

1. Open Arduino IDE  
2. Open the `.ino` file inside:


arduino/<your-sketch-folder>/


3. Select correct board (e.g., Arduino Mega 2560)  
4. Select correct COM port  
5. Click Upload  

The firmware implements:

• Manual Mode  
• Threshold-Based Control  
• PID-Based Control  
• LED status indicators  
• Pump actuation via relay/servo  
• Serial communication with backend  

---

## 7. Log Storage

Runtime logs are stored in:


backend/logs/


1-minute averaged OD values are stored as CSV files with timestamps.

Example format:


YYYY-MM-DD HH:MM, OD_Value


---

## 8. Reproducing a Demonstration

To reproduce a working demo:

1. Upload Arduino firmware.
2. Connect Arduino via USB.
3. Start backend server.
4. Open dashboard in browser.
5. Observe live OD values.
6. Modify PID parameters via dashboard.
7. Verify pump/relay activation.
8. Export CSV logs for analysis.

Sample CSV files are provided in:


backend/data_samples/


These can be used for offline testing of plotting and export functionality.

---

## 9. Notes on Safety

• Pumps default to OFF at startup.
• Invalid OD readings trigger safe fallback.
• PID output is bounded.
• Manual mode always overrides automatic control.

---

## 10. License

Academic use – University of Applied Sciences Bremerhaven.
