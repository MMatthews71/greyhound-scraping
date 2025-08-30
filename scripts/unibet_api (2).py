import json
import requests
import csv
from datetime import datetime, time
import pytz
from tabulate import tabulate
from zoneinfo import ZoneInfo

# Convert UTC time to Melbourne time
def utc_to_melbourne(utc_str):
    utc_dt = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ")
    utc_dt = utc_dt.replace(tzinfo=pytz.utc)
    melbourne_tz = pytz.timezone('Australia/Melbourne')
    melbourne_dt = utc_dt.astimezone(melbourne_tz)
    return melbourne_dt.strftime("%Y-%m-%d %H:%M:%S")

# Fetch live Unibet data
def fetch_unibet_data():
    melbourne_tz = ZoneInfo("Australia/Melbourne")
    now = datetime.now(melbourne_tz)
    today = now.date()
    start = datetime.combine(today, time.min, melbourne_tz)
    end = datetime.combine(today, time.max, melbourne_tz)

    url = "https://rsa.unibet.com.au/api/v1/graphql"
    headers = {"Content-Type": "application/json"}
    payload = {
        "operationName": "LobbyMeetingListQuery",
        "variables": {
            "countryCodes": [],
            "clientCountryCode": "AU",
            "startDateTime": start.isoformat() + "Z",
            "endDateTime": end.isoformat() + "Z",
            "virtualStartDateTime": start.isoformat() + "Z",
            "virtualEndDateTime": end.isoformat() + "Z",
            "isRenderingVirtual": False,
            "fetchTRC": False,
            "raceTypes": ["G", "H"]
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "31a97bd747dd4642dcc2584990eca46a52eb09fc7640d4f47e222df7af3a928d"
            }
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch data: {response.status_code}")
        return None

# Fetch detailed event data
def get_event_json(event_key):
    url = "https://rsa.unibet.com.au/api/v1/graphql"
    headers = {"Content-Type": "application/json"}
    payload = {
        "operationName": "EventQuery",
        "variables": {
            "clientCountryCode": "AU",
            "eventKey": event_key,
            "fetchTRC": False
        },
        "extensions": {
            "persistedQuery": {
                "version": 1,
                "sha256Hash": "4bfddf8b89e49c155f42a1ce45ea8f41ef75704762e82dfc23e4162aaa3f9ed1"
            }
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch data for {event_key}: {response.status_code}")
        return None

# Main processing
live_data = fetch_unibet_data()
if live_data:
    meetings = live_data['data']['viewer']['meetings']
    rows = []

    for meeting in meetings:
        if meeting.get('countryCode') in ['NZL', 'AUS'] and meeting.get('raceType') == 'G':
            meeting_name = meeting.get('name')
            for event in meeting.get('events', []):
                if event.get('status') == 'Open':
                    event_key = event.get('eventKey')
                    race_number = event.get('sequence')
                    distance = event.get('distanceMetres')
                    advertised_time = event.get('advertisedDateTimeUtc')
                    melbourne_time = utc_to_melbourne(advertised_time)

                    event_data = get_event_json(event_key)
                    if not event_data:
                        continue

                    competitors = event_data.get('data', {}).get('viewer', {}).get('event', {}).get('competitors', [])
                    for comp in competitors:
                        name = comp.get('name', 'Unknown')
                        if name == 'Vacant Box':
                            continue

                        sequence = comp.get('sequence')
                        start_pos = comp.get('startPos', 0)

                        if start_pos == 0:
                            continue

                        prices = comp.get('prices', [])
                        for price_entry in prices:
                            if price_entry.get('betType') == 'FixedWin':
                                flucs = price_entry.get('flucs', [])
                                for fluc in flucs:
                                    if fluc.get('productType') == 'Current':
                                        price = fluc.get('price')
                                        rows.append([
                                            meeting_name,
                                            race_number,
                                            melbourne_time,
                                            distance,
                                            name,
                                            sequence,
                                            start_pos,
                                            price
                                        ])
                                        break
                                break

    # Sort and display
    rows.sort(key=lambda x: (x[0], x[1], x[6]))
    headers = ["Meeting", "Race", "Time", "Distance", "Runner", "Rug", "Box", "Price"]
    print(tabulate(rows, headers=headers, tablefmt="pretty"))

    # Save to CSV
    with open('unibet_race_prices.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    print("\n✅ Saved full race data to unibet_race_prices.csv")
