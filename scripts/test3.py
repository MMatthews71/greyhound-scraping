import os
import re
import time
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException, NoSuchElementException

# ------------------------------
# Parsing Functions
# ------------------------------

def is_number(s):
    """Checks if a string is a number."""
    try:
        float(s)
        return True
    except ValueError:
        return False

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

# ------------------------------
# Selenium Functions
# ------------------------------

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

def click_race_by_location_time(driver, track_name, race_time, timeout=20, post_click_wait=3, max_retries=1):
    """
    Attempts to click on a race by track name and race time.
    Returns True if successful, False otherwise.
    """
    track_name_clean = track_name.lower().replace(" ", "").replace("-", "")
    
    for attempt in range(max_retries):
        try:
            race_cells = WebDriverWait(driver, timeout).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "td.MuiTableCell-root"))
            )
            
            for cell in race_cells:
                try:
                    try:
                        cell.find_element(By.CSS_SELECTOR, "h5.MuiTypography-root")
                        continue
                    except NoSuchElementException:
                        pass

                    WebDriverWait(driver, timeout).until(
                        lambda d: cell.is_displayed()
                    )
                    try:
                        time_el = cell.find_element(By.CSS_SELECTOR, "p.MuiTypography-root.MuiTypography-body2").text.strip()
                        if not re.match(r"^\d{2}:\d{2}$", time_el):
                            continue
                    except NoSuchElementException:
                        print(f"No <p> tag found in cell for {track_name} at {race_time}: {cell.get_attribute('outerHTML')}")
                        continue
                    try:
                        href = cell.find_element(By.TAG_NAME, "a").get_attribute("href").lower()
                    except NoSuchElementException:
                        print(f"No <a> tag found in cell for {track_name} at {race_time}: {cell.get_attribute('outerHTML')}")
                        continue

                    if time_el == race_time and track_name_clean in href:
                        try:
                            link = cell.find_element(By.TAG_NAME, "a")
                            driver.execute_script("arguments[0].click();", link)
                            print(f"Clicked race at {track_name} for {race_time}")
                            time.sleep(post_click_wait)
                            return True
                        except Exception as e:
                            print(f"Failed to click race at {track_name} for {race_time}: {str(e)}")
                            continue

                except (StaleElementReferenceException, TimeoutException):
                    print(f"Stale or inaccessible cell for {track_name} at {race_time}: {cell.get_attribute('outerHTML')}")
                    continue

            print(f"No race found for {track_name} at {race_time} on attempt {attempt + 1}")
            
        except (TimeoutException, StaleElementReferenceException):
            print(f"Attempt {attempt + 1} failed: Race elements did not load in time or became stale.")
            continue

    print(f"Could not click on race '{track_name}' at '{race_time}' after {max_retries} retries")
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

def build_dataframe(records):
    """
    Builds a DataFrame from race records.
    """
    df = pd.DataFrame(records, columns=["Race", "Dog number", "Name", "Form", "Win", "Place"])
    return df[1:]

def get_location_times(driver, exclude=("Australia",)):
    """
    Retrieves race locations and their corresponding times, excluding specified locations.
    """
    locations = {}
    text = None

    while not text or not locations:
        try:
            element = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-test-id='lobby-table-au']"))
            )
            text = element.text.strip()
            lines = text.splitlines()

            time_pattern = re.compile(r"^\d{2}:\d{2}$")
            number_pattern = re.compile(r"^\d+$")

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
                    if number_pattern.match(line) or line in exclude:
                        continue
                    current_location = line
                    locations[current_location] = []

            time.sleep(2)
        except:
            text, locations = None, []
            time.sleep(2)

    return locations

def scrape_races(driver, locations):
    """
    Iterates over race locations and times, scrapes race & form data.
    Returns two lists of DataFrames.
    """
    all_dfs, forms_dfs = [], []

    for track_name in locations:
        # Try the original click_race method first
        clicked = click_race(driver, track_name)
        if not clicked:
            print(f"Original click failed for {track_name}, attempting individual race clicks by time.")
            # If click_race fails, try clicking each race time for the current location
            for race_time in locations[track_name]:
                clicked = click_race_by_location_time(driver, track_name, race_time)
                if not clicked:
                    print(f"Skipping race at {track_name} for {race_time} as it could not be clicked.")
                    continue
                
                try:
                    race_data, form_data = get_dog_form_elements(driver)
                    
                    race_df = build_dataframe(parse_dog_data(race_data))
                    if not race_df.empty:
                        print(race_df)
                        all_dfs.append(race_df)
                    else:
                        print(f"No race data found for {track_name} at {race_time}, skipping.")

                    form_df = parse_greyhound_data(form_data)
                    if not form_df.empty:
                        print(form_df)
                        forms_dfs.append(form_df)
                    else:
                        print(f"No form data found for {track_name} at {race_time}, skipping.")
                except TimeoutError as e:
                    print(f"Timeout error for {track_name} at {race_time}: {e}")
                    continue
        else:
            # If click_race succeeded, process the race data as before
            try:
                race_data, form_data = get_dog_form_elements(driver)
                
                race_df = build_dataframe(parse_dog_data(race_data))
                if not race_df.empty:
                    print(race_df)
                    all_dfs.append(race_df)
                else:
                    print(f"No race data found for {track_name}, skipping.")

                form_df = parse_greyhound_data(form_data)
                if not form_df.empty:
                    print(form_df)
                    forms_dfs.append(form_df)
                else:
                    print(f"No form data found for {track_name}, skipping.")
            except TimeoutError as e:
                print(f"Timeout error for {track_name}: {e}")
                continue

    return all_dfs, forms_dfs

# ------------------------------
# Main
# ------------------------------

def main():
    driver = webdriver.Chrome()
    url = "https://www.unibet.com.au/racing#/lobby/G"
    try:
        driver.get(url)

        locations = get_location_times(driver)
        print(locations)
        
        scraped_race_data, scraped_form_data = scrape_races(driver, locations)

        race_output = pd.concat(scraped_race_data, ignore_index=True)
        form_output = pd.concat(scraped_form_data, ignore_index=True)[[
            'Greyhound', 'Plc', 'Date', 'Track', 'Days', 'Distance', 'Mgn',
            'Class', 'Box', 'In Run', 'Price', 'Time', 'Placing'
        ]]

        os.makedirs('../data', exist_ok=True)
        form_output.to_csv('../data/full_form_data.csv', index=False)
        race_output.to_csv('../data/race_data.csv', index=False)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()