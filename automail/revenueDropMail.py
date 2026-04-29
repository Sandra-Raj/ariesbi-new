import smtplib
import mysql.connector
import os
from datetime import datetime, date, timedelta
from email.message import EmailMessage
from config import EMAIL_CONFIG, DB_CONFIG

import pandas as pd
import sqlalchemy as sa

db = mysql.connector.connect(**DB_CONFIG)
cursor = db.cursor(dictionary=True)
current_month_revenue_query = f"""SELECT 
    dim.name AS division,
    dt.dimension2_id,
    dm.name AS client,
    SUM(ca.alloc_amount * dt.rate) AS current_month_revenue
FROM `0_cust_allocations` ca
INNER JOIN `0_debtor_trans` dt ON ca.trans_no_to = dt.trans_no AND ca.trans_type_to = dt.type
INNER JOIN `0_debtors_master` dm ON dt.debtor_no = dm.debtor_no
INNER JOIN `0_dimensions` dim ON dt.dimension2_id = dim.id
WHERE ca.trans_type_from = 12
  AND ca.date_alloc >= DATE_FORMAT(CURRENT_DATE, '%Y-%m-01')
GROUP BY dim.name, dt.dimension2_id, dm.name;"""
cursor.execute(current_month_revenue_query)
results = cursor.fetchall()
curr_df = pd.DataFrame(results)
PARQUET_FILE = "C:/xampp/htdocs/ariesbi/ariesbi-analytics/data/monthly_revenue.parquet"

if not os.path.exists(PARQUET_FILE):
    print("Parquet file not found. Initializing with last month's data...")
    
    # Query to get ONLY last month's revenue for the initial snapshot
    initial_seed_query = """
    SELECT 
        dim.name AS division,
        dt.dimension2_id,
        dm.name AS client,
        SUM(ca.alloc_amount * dt.rate) AS last_month_revenue
    FROM `0_cust_allocations` ca
    INNER JOIN `0_debtor_trans` dt ON ca.trans_no_to = dt.trans_no AND ca.trans_type_to = dt.type
    INNER JOIN `0_debtors_master` dm ON dt.debtor_no = dm.debtor_no
    INNER JOIN `0_dimensions` dim ON dt.dimension2_id = dim.id
    WHERE ca.trans_type_from = 12
      AND ca.date_alloc >= DATE_FORMAT(CURRENT_DATE - INTERVAL 1 MONTH, '%Y-%m-01')
      AND ca.date_alloc < DATE_FORMAT(CURRENT_DATE, '%Y-%m-01')
    GROUP BY dim.name, dt.dimension2_id, dm.name;
    """
    
    db = mysql.connector.connect(**DB_CONFIG)
    seed_df = pd.read_sql(initial_seed_query, db)
    db.close()
    
    seed_df.to_parquet(PARQUET_FILE)
    print(f"Successfully seeded {len(seed_df)} records into {PARQUET_FILE}.")

last_df = pd.read_parquet(PARQUET_FILE)

# Merge and Calculate Drop
comparison = pd.merge(
    last_df[['dimension2_id', 'client', 'division', 'last_month_revenue']], 
    curr_df[['dimension2_id', 'client', 'current_month_revenue']], 
    on=['dimension2_id', 'client'], 
    how='left'
).fillna(0)
comparison['revenue_drop'] = comparison['last_month_revenue'] - comparison['current_month_revenue']

# Filter for drops
drops = comparison[comparison['revenue_drop'] > 1].copy()

email_225 = drops[drops['dimension2_id'] == 225]
email_3 = drops[drops['dimension2_id'] == 3]
email_others = drops[~drops['dimension2_id'].isin([225, 3])]

# OVERWRITE Parquet for next month
curr_df.rename(columns={'current_month_revenue': 'last_month_revenue'}).to_parquet(PARQUET_FILE)

def send_alert(df, title):
    if df.empty:
        return 
    
    # Determine if this is a single division or the "Others" group
    is_single_div = title in ["I&M", "ONE"]
    
    # Define columns to display based on the recipient
    if is_single_div:
        headers = ["S.No", "Client", "Last Month Revenue", "This Month Revenue", "Revenue Drop"]
    else:
        headers = ["S.No", "Division", "Client", "Last Month Revenue", "This Month Revenue", "Revenue Drop"]

    table_rows = ""
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        last_val = f"{row['last_month_revenue']:,.2f}"
        curr_val = f"{row['current_month_revenue']:,.2f}"
        drop_val = f"{row['revenue_drop']:,.2f}"
        
        table_rows += "<tr>"
        table_rows += f"<td style='text-align:center;'>{i}</td>"
        
        if not is_single_div:
            table_rows += f"<td>{row['division']}</td>"
            
        table_rows += f"""
            <td>{row['client']}</td>
            <td style="text-align:right;">{last_val}</td>
            <td style="text-align:right;">{curr_val}</td>
            <td style="text-align:right; color: #d9534f; font-weight: bold;">{drop_val}</td>
        </tr>
        """

    header_html = "".join([f"<th>{h}</th>" for h in headers])

    html_content = f"""
    <html>
    <head>
        <style>
            table {{ 
                border-collapse: collapse; 
                width: 100%; 
                font-family: Arial, sans-serif; 
            }}
            th, td {{ 
                border: 1px solid #ccc; 
                padding: 8px; 
                word-wrap: break-word; 
            }}
            th {{ background-color: #eee; text-align: center; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <h3>{title} - Revenue Drop Alert</h3>
        <p>The following clients have shown a revenue drop (based on payments) compared to last month:</p>
        <table>
            <thead>
                <tr>{header_html}</tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg['Subject'] = f"Revenue Drop Alert - {title}"
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['admin_email']
    msg.set_content("Please enable HTML to view this report.")
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as smtp:
            smtp.ehlo()
            if EMAIL_CONFIG['smtp_port'] == 587:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
            smtp.send_message(msg)
            print(f"Successfully sent alert for {title}")
    except Exception as e:
        print(f"Error sending {title}: {e}")

send_alert(email_225, "I&M")
send_alert(email_3, "ONE")
send_alert(email_others, "Non Marine")