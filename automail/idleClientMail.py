import requests
import smtplib
import pandas as pd
import os
from email.message import EmailMessage
from config import EMAIL_CONFIG, API_IDLE_BASE_URL, DATA_PATH

# Division Mapping: ID -> Name
DIVISIONS = {
    "225": "I&M",
    "3": "ONE"
}

def fetch_idle_clients(division_id):
    """Fetches data from the API for a specific division."""
    params = {
        'division': division_id,
        'type': 'idle_enq'
    }
    try:
        response = requests.get(API_IDLE_BASE_URL, params=params)
        response.raise_for_status()
        return response.json()  # Assumes API returns a list of dicts
    except Exception as e:
        print(f"Failed to fetch data for division {division_id}: {e}")
        return None

PARQUET_FILE = F"{DATA_PATH}/idle_clients_tracking.parquet"

def get_improvements(new_data, division_id):
    """Compares new data with Parquet file to find clients no longer idle."""
    if not os.path.exists(PARQUET_FILE):
        return []
    try:
        df_old = pd.read_parquet(PARQUET_FILE)
        # Filter old data for this specific division
        df_old_div = df_old[df_old['division_id'] == str(division_id)]
        
        if df_old_div.empty:
            return []

        # Create sets of IDs for comparison
        old_ids = set(df_old_div['client_id']) # Adjust 'id' to your actual ID column name
        new_ids = set(item['client_id'] for item in new_data)

        # Improvements = IDs in old list but NOT in new list
        improved_ids = old_ids - new_ids
        
        # Get the full rows for these improved IDs
        improvements = df_old_div[df_old_div['client_id'].isin(improved_ids)].to_dict('records')
        return improvements
    except Exception as e:
        print(f"Error calculating improvements: {e}")
        return []

def save_to_parquet(all_current_data):
    """Overwrites the parquet file with the latest snapshot."""
    df = pd.DataFrame(all_current_data)
    for col in df.columns:
        df[col] = df[col].astype(str)

    try:
        df.to_parquet(PARQUET_FILE, index=False, engine='pyarrow')
        print(f"File updated: {PARQUET_FILE}")
    except Exception as e:
        print(f"Failed to save Parquet: {e}")

def build_html(current_idle, improvements, title):
    html = f"<html><body style='font-family: Arial, sans-serif;'>"
    html += f"<h2>{title} Management Report</h2>"

    # Section 1: Improvements
    if improvements:
        html += "<h3 style='color: #28a745;'>🎉 Improvements (Clients no longer idle)</h3>"
        html += render_table(improvements)
    else:
        html += "<p><em>No improvements recorded since last month.</em></p>"

    html += "<br><hr><br>"

    # 2. Handle Current Idle Table
    if current_idle:
        html += "<h3 style='color: #dc3545;'>Current Idle Clients</h3>"
        html += render_table(current_idle)
    else:
        html += "<p><em>No clients currently idle!</em></p>"

    html += "</body></html>"
    return html

def render_table(data_list):
    """Helper to turn a list of dicts into an HTML table."""
    headers = data_list[0].keys()
    table = "<table border='1' style='border-collapse: collapse; width: 100%; margin-bottom: 20px;'>"
    table += "<tr style='background-color: #f2f2f2;'>"
    for h in headers:
        table += f"<th style='padding: 8px;'>{h.replace('_', ' ').title()}</th>"
    table += "</tr>"
    for row in data_list:
        table += "<tr>" + "".join([f"<td style='padding: 8px;'>{row.get(k, '')}</td>" for k in headers]) + "</tr>"
    table += "</table>"
    return table

def send_notification(data, title, improvements):
    """Sends the formatted HTML email."""
    if not data and not improvements:
        print(f"No data for {title}. Skipping email.")
        return

    msg = EmailMessage()
    msg['Subject'] = f"Idle Clients Report - {title}"
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['admin_email']
    
    html_content = build_html(data, improvements, title)
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
            server.send_message(msg)
            print(f"Success: Sent {title} report.")
    except Exception as e:
        print(f"Email failed for {title}: {e}")

def main():
    all_records_for_storage = []
    
    for div_id, div_name in DIVISIONS.items():
        api_response = fetch_idle_clients(div_id)
        
        if api_response and "top_clients" in api_response:
            current_idle = api_response["top_clients"]
            
            for item in current_idle:
                item['division_id'] = div_id
            
            improvements = get_improvements(current_idle, div_id)
            send_notification(current_idle, div_name, improvements)
            all_records_for_storage.extend(current_idle)

    # Overwrite Parquet
    if all_records_for_storage:
        save_to_parquet(all_records_for_storage)

if __name__ == "__main__":
    main()