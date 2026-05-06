import pandas as pd
import mysql.connector
from email.message import EmailMessage
import smtplib
from config import DB_CONFIG, EMAIL_CONFIG

def get_decline_data():
    db = mysql.connector.connect(**DB_CONFIG)
    
    query = """
    SELECT 
        dm.name AS client_name,
        dim.name AS division,
        cp.date_of_curr_pmnt AS last_ord_date,
        last_job.max_job_date AS last_job_date,
        PERIOD_DIFF(
            DATE_FORMAT(last_job.max_job_date, '%Y%m'), 
            DATE_FORMAT(cp.date_of_curr_pmnt, '%Y%m')
        ) AS months_diff
    FROM (
        /* Grouping by BOTH debtor and division ensures the date matches the division */
        SELECT debtor_no, division, MAX(job_date) AS max_job_date 
        FROM `0_client_activity_status` 
        GROUP BY debtor_no, division
    ) AS last_job
    JOIN `0_client_credit_period` cp ON last_job.debtor_no = cp.debtor_no
    JOIN `0_debtors_master` dm ON last_job.debtor_no = dm.debtor_no
    JOIN `0_dimensions` dim ON last_job.division = dim.id
    WHERE cp.date_of_curr_pmnt IS NOT NULL
    HAVING months_diff >= 3
    ORDER BY months_diff DESC;
    """
    
    df = pd.read_sql(query, db)
    db.close()
    
    # Create the 3 lists
    list_3_6 = df[(df['months_diff'] >= 3) & (df['months_diff'] < 6)]
    list_6_12 = df[(df['months_diff'] >= 6) & (df['months_diff'] <= 12)]
    list_plus_year = df[df['months_diff'] > 12]
    
    return list_3_6, list_6_12, list_plus_year

def build_table(df, title, color):
    if df.empty:
        return f"<p>No clients found for {title}.</p>"
    
    rows = ""
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        rows += f"""
        <tr>
            <td>{i}</td>
            <td>{row['client_name']}</td>
            <td>{row['division']}</td>
            <td>{row['last_ord_date']}</td>
            <td>{row['last_job_date']}</td>
            <td style="font-weight:bold; color:{color};">{row['months_diff']} Months</td>
        </tr>
        """
    
    return f"""
    <h3 style="color:{color};">{title}</h3>
    <table border="1" style="border-collapse: collapse; width: 100%; margin-bottom: 20px; font-family: Arial;">
        <tr style="background-color: #eee;">
            <th>S.No</th><th>Client</th><th>Division</th><th>Payment Date</th><th>Job Date</th><th>Delay</th>
        </tr>
        {rows}
    </table>
    """

def send_decline_report():
    l1, l2, l3 = get_decline_data()
    
    html = f"""
    <html>
    <body>
        <h2>Client Activity Delay Report</h2>
        <p>This report identifies clients where the gap between Order Date and Job Date is increasing.</p>
        
        {build_table(l1, "Warning: 3-6 Month Delay", "#f0ad4e")}
        {build_table(l2, "Urgent: 6-12 Month Delay", "#d9534f")}
        {build_table(l3, "Critical: 1+ Year Delay", "#a94442")}
    </body>
    </html>
    """

    msg = EmailMessage()
    msg['Subject'] = "⚠️ Client Lifetime Value Decline: Activity Latency Report"
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['admin_email']
    msg.add_alternative(html, subtype='html')

    with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as smtp:
        smtp.ehlo()
        if EMAIL_CONFIG['smtp_port'] == 587:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
        smtp.send_message(msg)

if __name__ == "__main__":
    send_decline_report()