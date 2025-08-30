import os
import re
import time
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException


# ------------------------------
# Parsing Functions
# ------------------------------

def parse_australian_race_locations(data_list):
    data = data_list[0].strip().split('\n')
    australian_locations = []
    in_australia_section = False

    for line in data:
        line = line.strip()
        if line.lower() == "australia":
            in_australia_section = True
            continue
        elif line in [
            "Brazil", "Chile", "Italy", "New Zealand", "France", "Germany", "Japan",
            "Korea", "Malaysia", "South Africa", "Turkey", "UK & Ireland",
            "United States", "Canada"
        ]:
            in_australia_section = False
            continue

        if (
            in_australia_section and line
            and not any(char.isdigit() for char in line[0])
            and not line.startswith((':', '-', ','))
        ):
            australian_locations.append(line)

    return australian_locations


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def parse_horse_data(data):
    records = []
    i = 0
    current_race, current_race_name, current_distance, current_track = None, None, None, None

    while i < len(data):
        # Detect race start (time + venue)
        if re.match(r"\d{2}:\d{2}\s+", data[i]):
            current_race = data[i].strip()
            current_race_name = data[i + 1].strip() if i + 1 < len(data) else None
            current_distance = data[i + 2].strip() if i + 2 < len(data) else None
            current_track = data[i + 3].strip() if i + 3 < len(data) else None
            i += 4
            continue

        # Detect runner line: "1. HorseName (3)"
        runner_match = re.match(r"^(\d+)\.\s+(.*?)\s+\((\d+)\)$", data[i].strip())
        if runner_match:
            horse_num = runner_match.group(1)
            horse_name = runner_match.group(2).strip()
            barrier = runner_match.group(3).strip()

            jockey, trainer, form, age_sex = None, None, None, None
            odds, win, place = [], None, None

            # Look ahead
            j = i + 1
            while j < len(data):
                line = data[j].strip()

                if line == 'J' and j + 1 < len(data):
                    jockey = data[j + 1].strip()
                    j += 2
                    continue
                if line == 'T' and j + 1 < len(data):
                    trainer = data[j + 1].strip()
                    j += 2
                    continue
                if re.match(r"^[\dX\-]+$", line):
                    form = line
                    j += 1
                    continue
                if re.match(r"^\d+yo\s+[A-Z]$", line):
                    age_sex = line
                    j += 1
                    continue

                # Scratched runner
                if line == "Scratched":
                    records.append([
                        current_race, current_race_name, horse_num, horse_name, barrier,
                        jockey, trainer, form, age_sex, None, None, "Scratched"
                    ])
                    j += 1
                    break

                # Odds
                if is_number(line):
                    odds.append(line)
                    j += 1
                    continue

                # End of runner if new runner/race detected
                if re.match(r"^\d+\.\s+", line) or re.match(r"\d{2}:\d{2}\s+", line):
                    break

                j += 1

            if odds:
                win, place = (odds[-2], odds[-1]) if len(odds) >= 2 else (odds[-1], None)

            required_fields = [barrier, jockey, trainer, form, age_sex, win, place]
            if all(field is not None for field in required_fields):
                records.append([
                    current_race, current_race_name, horse_num, horse_name, barrier,
                    jockey, trainer, form, age_sex, win, place, "Active"
                ])
            i = j
        else:
            i += 1

    return records


def parse_horse_form(data_list):
    rows = []

    for entry in data_list:
        if 'Race History' not in entry:
            continue

        parts = [p.strip() for p in entry.split('\n') if p.strip()]

        # Horse name = first valid text before "Race History"
        horse_name = None
        for p in parts:
            if p in ["T:", "Race History"]:
                break
            if not p.isdigit() and p != ",":
                horse_name = p
                break

        if not horse_name:
            continue

        race_history_section = entry[entry.find('Race History'):]
        lines = [l.strip() for l in race_history_section.split('\n') if l.strip()]
        i = lines.index('Plc') + 1 if 'Plc' in lines else len(lines)

        while i < len(lines):
            line = lines[i]
            if not re.fullmatch(r'\d+/\d+', line):
                i += 1
                continue

            race_data = {
                'Horse': horse_name,
                'Plc': line,
                'Date': 'N/A',
                'Track': '',
                'Days': 'N/A',
                'Time': 'N/A',
                'Distance': '',
                'Mgn': '',
                'Class': 'N/A',
                'Cond': 'N/A',
                'Bar': '',
                'In Run': '',
                'Jockey': '',
                'Wgt': '',
                'Price': '',
                'Placing': ''
            }

            # Date
            i += 1
            if i < len(lines):
                try:
                    race_data['Date'] = datetime.strptime(lines[i], '%d/%m/%Y').strftime('%Y-%m-%d')
                except ValueError:
                    race_data['Date'] = lines[i]
                i += 1

            # Track + numeric values until Cond
            parts = []
            while i < len(lines) and lines[i] not in ['S', 'G', 'H'] and not lines[i].startswith('$'):
                parts.append(lines[i])
                i += 1

            # Split track vs numeric section
            j = 0
            while j < len(parts) and not re.fullmatch(r"^\d+(\.\d+)?$", parts[j]):
                j += 1
            race_data['Track'] = " ".join(parts[:j])
            values = parts[j:]

            # Map values
            if len(values) == 5:
                race_data['Days'], race_data['Time'], race_data['Distance'], race_data['Mgn'], race_data['Class'] = values
            elif len(values) == 4:
                if re.fullmatch(r"^\d+(\.\d+)?$", values[-1]):
                    race_data['Days'], race_data['Time'], race_data['Distance'], race_data['Mgn'] = values
                else:
                    race_data['Time'], race_data['Distance'], race_data['Mgn'], race_data['Class'] = values
            elif len(values) == 3:
                race_data['Time'], race_data['Distance'], race_data['Mgn'] = values

            # Cond
            if i < len(lines) and lines[i] in ['S', 'G', 'H']:
                race_data['Cond'] = lines[i]
                i += 1

            # Bar
            if i < len(lines) and re.fullmatch(r"\d+", lines[i]):
                race_data['Bar'] = lines[i]
                i += 1

            # In Run
            if i < len(lines) and (',' in lines[i] or re.fullmatch(r"(\d+,)*\d+", lines[i])):
                race_data['In Run'] = lines[i]
                i += 1

            # Jockey
            if i < len(lines):
                race_data['Jockey'] = lines[i]
                i += 1

            # Wgt
            if i < len(lines) and re.fullmatch(r"\d+(\.\d+)?", lines[i]):
                race_data['Wgt'] = lines[i]
                i += 1

            # Price
            if i < len(lines) and lines[i].startswith('$'):
                race_data['Price'] = lines[i]
                i += 1

            # Placing
            placing_lines = []
            while i < len(lines):
                l = lines[i]
                if re.fullmatch(r'\d+/\d+', l) or l in ['Race History', 'Back to top']:
                    break
                if l[0].isdigit() and '.' in l:
                    placing_lines.append(l)
                i += 1

            race_data['Placing'] = "\n".join(placing_lines) if placing_lines else 'N/A'
            rows.append(race_data)

    return pd.DataFrame(rows, columns=[
        'Horse', 'Plc', 'Date', 'Track', 'Days', 'Time', 'Distance',
        'Mgn', 'Class', 'Cond', 'Bar', 'In Run', 'Jockey', 'Wgt', 'Price', 'Placing'
    ])


# ------------------------------
# Selenium Functions
# ------------------------------

def click_race(driver, race_name, timeout=15, post_click_wait=3, max_retries=1):
    xpath = f"//div[contains(@class, 'sc-kVUOzj knIZUY') and .//h5[contains(text(), '{race_name}')]]"
    for attempt in range(max_retries):
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.find_element("xpath", xpath).is_displayed()
            )
            race_div = driver.find_element("xpath", xpath)
            driver.execute_script("arguments[0].click();", race_div)
            print(f"Clicked on {race_name}")
            time.sleep(post_click_wait)
            return True
        except (StaleElementReferenceException, TimeoutException):
            print(f"Attempt {attempt + 1} failed for {race_name}")
    print(f"Could not click on race '{race_name}' after {max_retries} retries")
    return False


def get_horse_form_elements(driver, homepage_url="https://www.unibet.com.au/racing#/lobby/T",
                            css_selector=".css-10arllf", timeout=45):
    start = time.time()
    dog_list = []

    while len(dog_list) < 10:
        if time.time() - start > timeout:
            raise TimeoutError(f"Dog list did not reach 10 items within {timeout} seconds")
        try:
            elements = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, css_selector))
            )
            dog_list = [el.text.strip() for el in elements if el.text.strip()]
            dog_list = '\n'.join(dog_list).split('\n')
        except TimeoutException:
            time.sleep(0.5)

    button = WebDriverWait(driver, 45).until(
        EC.element_to_be_clickable((By.XPATH, "//button[span[normalize-space()='FULL FORM']]"))
    )
    driver.execute_script("arguments[0].click();", button)

    elements = WebDriverWait(driver, 45).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".sc-jNwOwP.drZjiD"))
    )
    form_list = [el.text.strip() for el in elements if el.text.strip()]

    driver.back()
    print("Back navigation triggered...")
    try:
        WebDriverWait(driver, timeout).until(lambda d: d.current_url == homepage_url)
        print("Back to homepage successfully")
    except TimeoutException:
        print(f"Failed to return to homepage within {timeout} seconds (current_url: {driver.current_url})")

    time.sleep(2)
    return dog_list, form_list


def build_dataframe(records):
    df = pd.DataFrame(
        records,
        columns=[
            "Race Time", "Race Name", "Horse Number", "Horse Name", "Barrier",
            "Jockey", "Trainer", "Form", "Age/Sex", "Win Odds", "Place Odds", "Status"
        ]
    )
    return df

def get_location_times(driver, exclude=("Australia",)):
    locations = {}
    text = None

    while not text or not locations:
        try:
            element = WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-test-id='lobby-table-au']"))
            )
            text = element.text.strip()
            lines = text.splitlines()

            time_pattern = re.compile(r"^\d{2}:\d{2}$")
            number_pattern = re.compile(r"^\d+$")  # matches "1", "2", etc.

            locations = {}
            current_location = None

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if time_pattern.match(line):
                    if current_location and current_location not in exclude:
                        locations[current_location].append(line)
                else:
                    # skip numbers and excluded words
                    if number_pattern.match(line) or line in exclude:
                        continue
                    current_location = line
                    locations[current_location] = []

            time.sleep(2)  # Wait before retrying if needed
        except:
            text, locations = None, []
            time.sleep(2)  # Wait before retrying on exception

    return locations

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
import time

def click_race_by_location_time(driver, track_name, race_time, timeout=20, post_click_wait=3, max_retries=1):
    # Ensure race_time is a string to avoid module conflicts
    if not isinstance(race_time, str):
        raise ValueError(f"race_time must be a string, got {type(race_time)}")
    
    # Construct the XPath
    xpath = f"//tr[contains(., '{track_name}')]//td//a[.//p[text()='{race_time}']]"
    
    for attempt in range(max_retries):
        try:
            # Wait for the element to be displayed
            WebDriverWait(driver, timeout).until(
                lambda d: d.find_element(By.XPATH, xpath).is_displayed()
            )
            # Find the button element
            button = driver.find_element(By.XPATH, xpath)
            # Click using JavaScript
            driver.execute_script("arguments[0].click();", button)
            print(f"Clicked on race at {track_name} for time {race_time}")
            time.sleep(post_click_wait)
            return True
        except (StaleElementReferenceException, TimeoutException) as e:
            print(f"Attempt {attempt + 1} failed for {track_name} at {race_time}: {e}")
        except Exception as e:
            print(f"Unexpected error for {track_name} at {race_time}: {e}")
            break
    print(f"Could not click on race at '{track_name}' for time '{race_time}' after {max_retries} retries")
    return False


def scrape_races(driver, locations):
    all_dfs, forms_dfs = [], []
    for race_name in locations:
        click = click_race(driver, race_name)
        if not click:
            print(f"Could not click {race_name}, each race will be clicked individually.")
            for race_time in locations[race_name]:
                click_Race = click_race_by_location_time(driver, race_name, race_time)
                if click_race = 
                race_data, form_data = get_horse_form_elements(driver)
                race_df = build_dataframe(parse_horse_data(race_data))
                if not race_df.empty:
                    print(race_df)
                    all_dfs.append(race_df)
                else:
                    print(f"No data found for {race_name}, skipping.")

                form_df = parse_horse_form(form_data)
                form_df = form_df[form_df['Jockey'] != 'N/A']
                if not form_df.empty:
                    print(form_df)
                    forms_dfs.append(form_df)
                else:
                    print(f"No form data found for {race_name}, skipping.")

        race_data, form_data = get_horse_form_elements(driver)

        race_df = build_dataframe(parse_horse_data(race_data))
        if not race_df.empty:
            print(race_df)
            all_dfs.append(race_df)
        else:
            print(f"No data found for {race_name}, skipping.")

        form_df = parse_horse_form(form_data)
        form_df = form_df[form_df['Jockey'] != 'N/A']
        if not form_df.empty:
            print(form_df)
            forms_dfs.append(form_df)
        else:
            print(f"No form data found for {race_name}, skipping.")

    return all_dfs, forms_dfs


# ------------------------------
# Main
# ------------------------------

def main():
    driver = webdriver.Chrome()
    url = "https://www.unibet.com.au/racing#/lobby/T"
    driver.get(url)
    
    locations = get_location_times(driver)

    scraped_race_data, scraped_form_data = scrape_races(driver, locations)

    race_output = pd.concat(scraped_race_data, ignore_index=True)
    form_output = pd.concat(scraped_form_data, ignore_index=True)

    os.makedirs('../data', exist_ok=True)
    form_output.to_csv('../data/Tfull_form_data.csv', index=False)
    race_output.to_csv('../data/Trace_data.csv', index=False)

    driver.quit()


if __name__ == "__main__":
    main()
