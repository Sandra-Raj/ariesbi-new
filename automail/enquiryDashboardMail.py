import pandas as pd
import numpy as np
import mysql.connector
import matplotlib.pyplot as plt
from email.message import EmailMessage
from datetime import datetime, timedelta
import smtplib
from config import DB_CONFIG, EMAIL_CONFIG, IMAGE_PATH

today = datetime.now().date()
start_date = today - timedelta(days=8)
end_date = full_end = today
prev_end = start_date - timedelta(days=1)
full_start = prev_end - timedelta(days=7)

# Convert to strings for SQL
sd = start_date.strftime('%Y-%m-%d')
ed = end_date.strftime('%Y-%m-%d')
fe = full_end.strftime('%Y-%m-%d')
pe = prev_end.strftime('%Y-%m-%d')
fs = full_start.strftime('%Y-%m-%d')

def get_weekly_data():
    db = mysql.connector.connect(**DB_CONFIG)
    # start_date = "2026-03-20"
    # end_date = "2026-03-28"
    # full_start = "2026-03-13"
    # full_end = "2026-03-28"
    query = f"""
    SELECT 
        CASE 
            WHEN division = 225 THEN 'I&M'
            WHEN division = 3 THEN 'ONE'
            ELSE 'Other'
        END as div_group,
        COUNT(client_enquiry_id) as enquiry_count,
        SUM(aprox_amount * rate) as total_amt,
        COUNT(CASE WHEN (aprox_amount *rate) > 500000 THEN 1 END) as over_500k
    FROM `0_client_enquiry`
    WHERE enquiry_date >= '{sd}' AND enquiry_date <= '{ed}' AND location_country = 1
    GROUP BY div_group
    """
    
    # Query for Top Subdivision per Group
    sub_query = f"""
    SELECT sub_data.div_group, dim.name as sub_name, sub_data.sub_amt
    FROM (
        SELECT 
            CASE 
                WHEN division = 225 THEN 'I&M' 
                WHEN division = 3 THEN 'ONE' 
                ELSE 'Other' 
            END as div_group,
            subdivision,
            SUM(aprox_amount *rate) as sub_amt,
            ROW_NUMBER() OVER(PARTITION BY CASE WHEN division = 225 THEN 'I&M' WHEN division = 3 THEN 'ONE' ELSE 'Other' END 
                              ORDER BY COUNT(client_enquiry_id) DESC) as rnk
        FROM `0_client_enquiry`
        WHERE enquiry_date >= '{sd}' AND enquiry_date <= '{ed}' AND location_country = 1
        GROUP BY div_group, subdivision
    ) sub_data
    JOIN `0_dimensions` dim ON sub_data.subdivision = dim.id
    WHERE sub_data.rnk = 1
    """

    # Query for Graph (Past 2 weeks counts)
    graph_query = f"""
    SELECT 
        enquiry_date,
        CASE 
            WHEN division = 225 THEN 'I&M' 
            WHEN division = 3 THEN 'ONE' 
            ELSE 'Other' 
        END as div_group,
        COUNT(*) as daily_count
    FROM `0_client_enquiry`
    WHERE enquiry_date BETWEEN '{fs}' AND '{fe}'
      AND location_country = 1
    GROUP BY div_group, enquiry_date
    ORDER BY enquiry_date ASC
    """

    df_summary = pd.read_sql(query, db)
    df_subs = pd.read_sql(sub_query, db)
    df_graph = pd.read_sql(graph_query, db)
    db.close()
    
    return df_summary, df_subs, df_graph

def generate_graphs(df_daily):
    paths = {}
    groups = ['I&M', 'ONE', 'Other']
    
    for group in groups:
        group_df = df_daily[df_daily['div_group'] == group].copy()
        group_df['enquiry_date'] = pd.to_datetime(group_df['enquiry_date'])
        
        # Ensure dates are represented even if count is 0
        idx = pd.date_range(full_start, full_end)
        group_df = group_df.set_index('enquiry_date')
        group_df = group_df.reindex(idx)
        group_df['daily_count'] = group_df['daily_count'].fillna(0)
        group_df['div_group'] = group_df['div_group'].fillna(group)
        
        group_df = group_df.reset_index().rename(columns={'index': 'date'})

        plt.figure(figsize=(12, 5))
        
        plt.plot(group_df['date'], group_df['daily_count'], 
                 marker='o', linestyle='-', color='#0275d8', linewidth=2.5)

        min_val = group_df['daily_count'].min()
        max_val = group_df['daily_count'].max()
        
        y_min = int(np.floor(min_val / 10.0)) * 10
        y_max = max_val + 5
        
        plt.ylim(y_min, y_max)
        plt.yticks(np.arange(y_min, y_max + 5, 5)) # Increment by 5

        # Vertical separator for the weeks
        plt.axvline(pd.Timestamp(start_date), color='#d9534f', linestyle='--', linewidth=1.5, alpha=0.7)
        
        plt.title(f"14-Day Enquiry Timeline: {group} (UAE Region)", fontsize=14, fontweight='bold')
        plt.xlabel("Date")
        plt.ylabel("Enquiries")
        plt.grid(True, linestyle=':', alpha=0.5)
        
        # Format X-axis dates
        plt.xticks(group_df['date'], group_df['date'].dt.strftime('%d %b'), rotation=45)
        
        plt.tight_layout()
        path = f"{IMAGE_PATH}/graph_{group.replace('&', '')}.png"
        plt.savefig(path, dpi=100)
        plt.close()
        paths[group] = path
    return paths

def format_currency(value):
    if value is None or value == 0:
        return "0"
    abs_val = abs(value)
    if abs_val >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    elif abs_val >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.2f}"

def send_mail():
    df_summary, df_subs, df_graph = get_weekly_data()
    graph_paths = generate_graphs(df_graph)
    
    groups = ['I&M', 'ONE', 'Other']
    stats = df_summary.set_index('div_group').to_dict('index')
    subs = df_subs.set_index('div_group').to_dict('index')

    row_count = "".join([f"<td>{stats.get(g, {}).get('enquiry_count', 0)}</td>" for g in groups])
    row_amt = "".join([f"<td>{format_currency(stats.get(g, {}).get('total_amt', 0))}</td>" for g in groups])
    row_500 = "".join([f"<td>{stats.get(g, {}).get('over_500k', 0)}</td>" for g in groups])
    
    row_sub_name = "".join([f"<td>{subs.get(g, {}).get('sub_name', 'N/A')}</td>" for g in groups])
    row_sub_amt = "".join([f"<td>{format_currency(subs.get(g, {}).get('sub_amt', 0))}</td>" for g in groups])

    html = f"""
    <html>
    <head>
        <style>
            table {{ border-collapse: collapse; width: 100%; font-family: sans-serif; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ccc; padding: 10px; text-align: center; }}
            th {{ background-color: #f8f9fa; }}
        </style>
    </head>
    <body>
        <h3>Weekly Division Performance</h3>
        <table>
            <tr><th>Metric</th><th>I&M</th><th>ONE</th><th>Other</th></tr>
            <tr><td>No. of Enquiries</td>{row_count}</tr>
            <tr><td>Total Amount</td>{row_amt}</tr>
            <tr><td> > 500K</td>{row_500}</tr>
        </table>

        <h3>Visual Trends (Timeline Analysis)</h3>
        <div class="chart-box">
            <img src="cid:graph_IM" class="full-img"><br>
            <img src="cid:graph_ONE" class="full-img"><br>
            <img src="cid:graph_Other" class="full-img">
        </div>

        <h3>Top Sub-Division Analysis</h3>
        <table>
            <tr><th>Metric</th><th>I&M</th><th>ONE</th><th>Other</th></tr>
            <tr><td>Top Sub-Division</td>{row_sub_name}</tr>
            <tr><td>Sub-Division Revenue</td>{row_sub_amt}</tr>
        </table>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg['Subject'] = "Weekly Enquiry Dashboard"
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['admin_email']
    msg.add_alternative(html, subtype='html')

    # Embed Images
    for g, path in graph_paths.items():
        with open(path, 'rb') as f:
            cid = f"graph_{g.replace('&', '')}"
            msg.get_payload()[0].add_related(f.read(), 'image', 'png', cid=cid)
    
    with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as smtp:
            smtp.ehlo()
            if EMAIL_CONFIG['smtp_port'] == 587:
                smtp.starttls()
                smtp.ehlo()
            smtp.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
            smtp.send_message(msg)
            print(f"Successfully sent alert")

if __name__ == "__main__":
    send_mail()