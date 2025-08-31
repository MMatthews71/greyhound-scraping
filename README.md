# 🐾 Unibet Racing Web Scrapers

This repository contains two custom-built Python web scrapers for **Unibet Australia**, designed to extract structured data from highly dynamic and unstructured racing pages.  

The scrapers cover both **Greyhound Racing** and **Thoroughbred Racing**, enabling automated collection of race and form data for analytics, betting strategies, and data science projects.

---

## 🔹 Features

### Greyhound Scraper
- Extracts: **dog number, name, form, win odds, place odds**
- Collects **full historical form data** for each runner
- Handles edge cases:
  - Scratched runners  
  - Abandoned races  
  - Races in progress/finished  
- Outputs structured CSVs:
  - `race_data.csv`  
  - `full_form_data.csv`  

### Thoroughbred Scraper
- Extracts: **horse number, name, barrier, jockey, trainer, age/sex, win/place odds, status (scratched/active)**
- Parses historical form data including:
  - Track, distance, conditions, jockeys, placings
- Supports **multiple races and venues**
- Outputs structured CSVs:
  - `Trace_data.csv`  
  - `Tfull_form_data.csv`  

---

## 🔹 Purpose
These scrapers transform messy, dynamic web pages into clean datasets, unlocking opportunities for:

- 🏇 **Predictive modelling** of race outcomes  
- 📊 **Historical performance analysis**  
- 💰 **Odds tracking & betting strategy development**  

---

## 🔹 Output
Both scrapers generate CSV files suitable for:

- 📈 Data science workflows  
- 🎨 Visualization dashboards  
- ⚡ Automation pipelines  

---

## ⚙️ Installation & Setup

### Requirements
- Python 3.9+
- [Google Chrome](https://www.google.com/chrome/)  
- [ChromeDriver](https://chromedriver.chromium.org/) (ensure it matches your Chrome version)

### Install Dependencies
```bash
pip install -r requirements.txt
