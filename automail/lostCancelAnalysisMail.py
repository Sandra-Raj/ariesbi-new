import pandas as pd
import mysql.connector
import matplotlib.pyplot as plt
from email.message import EmailMessage
import smtplib
import os
from config import DB_CONFIG, EMAIL_CONFIG, IMAGE_PATH

def get_analysis_data():
    db = mysql.connector.connect(**DB_CONFIG)
    query = """
    SELECT 
        DATE_FORMAT(enquiry_date, '%Y-%m') AS month,
        division,
        COUNT(CASE WHEN enq_status = 2 THEN 1 END) AS lost_count,
        COUNT(CASE WHEN enq_status = 1 THEN 1 END) AS cancel_count
    FROM `0_client_enquiry`
    WHERE division IN (3, 225)
      AND enquiry_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
    GROUP BY month, division
    ORDER BY month ASC;
    """
    df = pd.read_sql(query, db)
    db.close()
    return df

def generate_comparison_graphs(df):
    # Pivot data for easy plotting
    # Rows: Month, Columns: Division, Values: Count
    lost_df = df.pivot(index='month', columns='division', values='lost_count').fillna(0)
    cancel_df = df.pivot(index='month', columns='division', values='cancel_count').fillna(0)
    
    paths = []
    titles = [("Lost Enquiries", lost_df, "lost_trend.png"), 
              ("Cancelled Enquiries", cancel_df, "cancel_trend.png")]

    for label, data, filename in titles:
        plt.figure(figsize=(10, 5))
        
        # Plot Division 225 (I&M)
        if 225 in data.columns:
            plt.plot(data.index, data[225], marker='o', label='Division 225 (I&M)', color='#d9534f', linewidth=2)
        
        # Plot Division 3 (ONE)
        if 3 in data.columns:
            plt.plot(data.index, data[3], marker='o', label='Division 3 (ONE)', color='#0275d8', linewidth=2)

        plt.title(f"6-Month Trend: {label}", fontsize=14, fontweight='bold')
        plt.ylabel("Number of Enquiries")
        plt.xlabel("Month")
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.legend()
        
        path = os.path.join(f"{IMAGE_PATH}", filename)
        plt.savefig(path)
        plt.close()
        paths.append(path)
    
    return paths

def send_analysis_email():
    df = get_analysis_data()
    if df.empty:
        print("No data found for analysis.")
        return

    graph_paths = generate_comparison_graphs(df)
    
    html_body = """
    <html>
    <body style='font-family: Arial; text-align: center;'>
        <h2>Enquiry Loss & Cancellation Analysis</h2>
        <p>Comparison between Division 225 (I&M) and Division 3 (ONE) over the last 6 months.</p>
        
        <div style='margin-bottom: 40px;'>
            <h3>Lost Enquiries Comparison</h3>
            <img src="cid:lost_trend" style='width: 80%; max-width: 800px;'>
        </div>
        
        <hr>
        
        <div style='margin-top: 40px;'>
            <h3>Cancelled Enquiries Comparison</h3>
            <img src="cid:cancel_trend" style='width: 80%; max-width: 800px;'>
        </div>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg['Subject'] = "Monthly Enquiry Lost/Cancel Analysis"
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['admin_email']
    msg.add_alternative(html_body, subtype='html')

    # Attach Lost Graph
    with open(graph_paths[0], 'rb') as f:
        msg.get_payload()[0].add_related(f.read(), 'image', 'png', cid='lost_trend')
    
    # Attach Cancel Graph
    with open(graph_paths[1], 'rb') as f:
        msg.get_payload()[0].add_related(f.read(), 'image', 'png', cid='cancel_trend')

    with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as smtp:
        if EMAIL_CONFIG['smtp_port'] == 587:
            smtp.starttls()
        smtp.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
        smtp.send_message(msg)
        print("Analysis email sent successfully.")

if __name__ == "__main__":
    send_analysis_email()