import os
import re
import time
from datetime import datetime

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException


def parse_australian_race_locations(data_list):
    """
    Extracts Australian race locations from the given data list.
    """
    data = data_list[0].strip().split('\n')
    australian_locations = []
    in_australia_section = False

    for line in data:
        line = line.strip()
        if line.lower() == "australia":
            in_australia_section = True
            continue
        elif line in [
            "New Zealand", "France", "Germany", "Japan", "Korea", "Malaysia",
            "South Africa", "Turkey", "UK & Ireland", "United States", "Canada"
        ]:
            in_australia_section = False
            continue

        if (
            in_australia_section
            and line
            and not any(char.isdigit() for char in line[0])
            and not line.startswith((':', '-', ','))
        ):
            australian_locations.append(line)

    return australian_locations


def is_number(s):
    """Checks if a string is a number."""
    try:
        float(s)
        return True
    except ValueError:
        return False


def click_race(driver, race_name, timeout=10, post_click_wait=3, max_retries=1):
    """
    Attempts to click on a race by name.
    Returns True if successful, False otherwise.
    """
    xpath = f"//div[contains(@class, 'sc-kVUOzj knIZUY') and .//h5[contains(text(), '{race_name}')]]"

    for attempt in range(max_retries):
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.find_element(By.XPATH, xpath).is_displayed()
            )
            race_div = driver.find_element(By.XPATH, xpath)
            driver.execute_script("arguments[0].click();", race_div)
            print(f"Clicked on {race_name}")
            time.sleep(post_click_wait)
            return True
        except (StaleElementReferenceException, TimeoutException):
            print(f"Attempt {attempt + 1} to click '{race_name}' failed.")
            time.sleep(1)

    return False


def get_dog_form_elements(
    driver,
    homepage_url="https://www.unibet.com.au/racing#/lobby/G",
    css_selector=".css-10arllf",
    timeout=45
):
    """
    Scrapes dog list and full form data from the current race page.
    Returns two lists: dog_list and form_list.
    """
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


def parse_greyhound_data(data_list):
    """
    Parses full form greyhound data into a DataFrame.
    """
    rows = []

    for entry in data_list:
        greyhound_name = entry.split('\n')[0].strip()
        race_history_section = entry[entry.find('Race History'):]
        lines = race_history_section.split('\n')
        race_start_idx = lines.index('Plc') + 1 if 'Plc' in lines else len(lines)
        i = race_start_idx

        while i < len(lines):
            line = lines[i].strip()
            if not line or line in ['Back to top', 'Race History']:
                i += 1
                continue

            line_upper = line.upper()
            if 'SPELL' in line_upper or 'LET-UP' in line_upper:
                i += 1
                continue

            if re.fullmatch(r'\d+/\d+', line):
                race_data = {
                    'Greyhound': greyhound_name,
                    'Plc': line,
                    'Date': '',
                    'Track': '',
                    'Days': '',
                    'Distance': '',
                    'Mgn': '',
                    'Class': '',
                    'Box': '',
                    'In Run': '',
                    'Wgt': 'N/A',
                    'Price': '',
                    'Sect': '',
                    'Time': '',
                    'Best': '',
                    'Placing': ''
                }

                i += 1
                # Date
                if i < len(lines):
                    try:
                        race_data['Date'] = datetime.strptime(lines[i].strip(), '%d/%m/%Y').strftime('%Y-%m-%d')
                    except ValueError:
                        race_data['Date'] = lines[i].strip()
                    i += 1

                # Track and subsequent fields
                if i < len(lines):
                    parts = []
                    while i < len(lines) and not lines[i].strip().startswith('$'):
                        if lines[i].strip():
                            parts.append(lines[i].strip())
                        i += 1

                    track_parts = []
                    j = 0
                    while j < len(parts) and not parts[j].replace('.', '').isdigit():
                        track_parts.append(parts[j])
                        j += 1
                    race_data['Track'] = ' '.join(track_parts)

                    values = parts[j:]
                    if i < len(lines):
                        race_data['Price'] = lines[i].strip()
                        i += 1

                    if len(values) == 6:
                        race_data['Days'], race_data['Distance'], race_data['Mgn'], race_data['Class'], race_data['Box'], race_data['In Run'] = values
                    elif len(values) == 5:
                        race_data['Days'] = 'N/A'
                        race_data['Distance'], race_data['Mgn'], race_data['Class'], race_data['Box'], race_data['In Run'] = values
                    else:
                        race_data['In Run'] = 'N/A'
                        print(
                            f"Warning: Invalid number of values ({len(values)}) "
                            f"between Track and Price for {greyhound_name} on {race_data['Date']}"
                        )

                    if race_data['In Run'] and not (
                        re.fullmatch(r'(\d+,)*\d*', race_data['In Run'])
                        or race_data['In Run'] == 'N/A'
                    ):
                        print(
                            f"Warning: Invalid In Run data '{race_data['In Run']}' "
                            f"for {greyhound_name} on {race_data['Date']}"
                        )
                        race_data['In Run'] = 'N/A'

                # Sect
                if i < len(lines):
                    race_data['Sect'] = lines[i].strip()
                    i += 1

                # Time
                if i < len(lines):
                    race_data['Time'] = lines[i].strip()
                    i += 1

                # Best
                if i < len(lines):
                    next_line = lines[i].strip()
                    if next_line.replace('.', '').isdigit() or next_line in ['N/A', '0']:
                        race_data['Best'] = next_line
                        i += 1
                    else:
                        race_data['Best'] = 'N/A'

                # Placing
                placing_lines = []
                while i < len(lines):
                    l = lines[i].strip()
                    if not l or re.fullmatch(r'\d+/\d+', l) or 'SPELL' in l.upper() or 'LET-UP' in l.upper():
                        break
                    if l[0].isdigit() and l[1] == '.':
                        placing_lines.append(l)
                    i += 1
                race_data['Placing'] = '\n'.join(placing_lines) if placing_lines else 'N/A'

                rows.append(race_data)
            else:
                i += 1

    return pd.DataFrame(rows, columns=[
        'Greyhound', 'Plc', 'Date', 'Track', 'Days', 'Distance', 'Mgn',
        'Class', 'Box', 'In Run', 'Wgt', 'Price', 'Sect', 'Time', 'Best', 'Placing'
    ])


def parse_dog_data(data):
    """
    Parses race data into structured records.
    """
    records = []
    i = 0
    current_race = None

    while i < len(data):
        if re.match(r"\d{2}:\d{2}\s+", data[i]):
            current_race = data[i].strip()
            i += 1
            continue

        runner_match = re.match(r"^(.*?)\((\d+)\)$", data[i].strip())
        if runner_match:
            name_with_num = runner_match.group(1).strip()
            dog_num = runner_match.group(2).strip()
            potential_form = data[i + 3] if i + 3 < len(data) else None
            form = potential_form.strip() if potential_form and re.match(r'^[\dX\-]+$', potential_form.strip()) else None

            odds = []
            j = i + 5
            while (
                j < len(data)
                and not ("(" in data[j] and ")" in data[j])
                and not re.match(r"\d{2}:\d{2}\s+", data[j])
            ):
                if is_number(data[j]):
                    odds.append(data[j])
                j += 1

            win, place = (odds[-2], odds[-1]) if len(odds) >= 2 else (None, None)
            records.append([current_race, dog_num, name_with_num, form, win, place])
            i = j
        else:
            i += 1

    return records


def build_dataframe(records):
    """
    Builds a DataFrame from race records.
    """
    df = pd.DataFrame(records, columns=["Race", "Dog number", "Name", "Form", "Win", "Place"])
    return df[1:]


def scrape_races(driver, australian_locations):
    """
    Iterates over Australian race locations and scrapes race & form data.
    Returns two lists of DataFrames.
    """
    all_dfs, forms_dfs = [], []

    for race_name in australian_locations:
        click_success = click_race(driver, race_name)

        if not click_success:
            print(f"Skipping {race_name}, could not click race.")
            continue

        race_data, form_data = get_dog_form_elements(driver)

        race_df = build_dataframe(parse_dog_data(race_data))
        if not race_df.empty:
            print(race_df)
            all_dfs.append(race_df)
        else:
            print(f"No race data found for {race_name}, skipping.")

        form_df = parse_greyhound_data(form_data)
        if not form_df.empty:
            print(form_df)
            forms_dfs.append(form_df)
        else:
            print(f"No form data found for {race_name}, skipping.")

    return all_dfs, forms_dfs


def main():
    driver = webdriver.Chrome()
    url = "https://www.unibet.com.au/racing#/lobby/G"
    driver.get(url)

    text = None
    australian_locations = []

    while not text or not australian_locations:
        try:
            element = WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".css-1kd0cbg"))
            )
            text = element.text.strip()
            australian_locations = parse_australian_race_locations([text])
            time.sleep(2)
        except Exception:
            text, australian_locations = None, []
            time.sleep(2)

    scraped_race_data, scraped_form_data = scrape_races(driver, australian_locations)

    race_output = pd.concat(scraped_race_data, ignore_index=True)
    form_output = pd.concat(scraped_form_data, ignore_index=True)[[
        'Greyhound', 'Plc', 'Date', 'Track', 'Days', 'Distance', 'Mgn',
        'Class', 'Box', 'In Run', 'Price', 'Time', 'Placing'
    ]]

    os.makedirs('../data', exist_ok=True)
    form_output.to_csv('../data/full_form_data.csv', index=False)
    race_output.to_csv('../data/race_data.csv', index=False)

    driver.quit()


if __name__ == "__main__":
    main()
