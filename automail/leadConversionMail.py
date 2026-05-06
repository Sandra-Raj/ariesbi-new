import pandas as pd
import mysql.connector
from email.message import EmailMessage
import smtplib
from datetime import datetime, timedelta
from config import DB_CONFIG, EMAIL_CONFIG

def get_enquiry_details():
    db = mysql.connector.connect(**DB_CONFIG)
    
    # Hardcoded dates for testing (replace with dynamic logic later)
    start_date = "2026-04-06"
    end_date = "2026-04-13"

    # end_date = datetime.now().strftime('%Y-%m-%d')
    # start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    query = f"""
    SELECT 
        dm.name AS client_name, 
        dim1.id AS division_id,
        dim1.name AS division_name, 
        dim2.name AS subdivision_name, 
        ce.enquiry_date, 
        ct.client_type sector,
        CASE 
            WHEN ce.enq_status = 1 THEN 'Cancel'
            WHEN ce.enq_status = 2 THEN 'Lost'
        END AS status,
        (ce.aprox_amount * ce.rate) AS amount
    FROM `0_client_enquiry` ce
    JOIN `0_debtors_master` dm ON ce.debtor_no = dm.debtor_no
    JOIN `0_dimensions` dim1 ON ce.division = dim1.id
    JOIN `0_dimensions` dim2 ON ce.subdivision = dim2.id
    JOIN `0_client_type` ct ON ce.client_type = ct.id
    WHERE ce.enquiry_date BETWEEN '{start_date}' AND '{end_date}'
    AND ce.division IN (3, 225) AND enq_status IN (1,2)
    ORDER BY dim2.name, ce.enquiry_date;
    """
    
    df = pd.read_sql(query, db)
    db.close()
    return df

def send_division_emails():
    df_all = get_enquiry_details()
    
    for div_id in [225, 3]:
        df_div = df_all[df_all['division_id'] == div_id]
        
        if df_div.empty:
            print(f"No data for Division {div_id}. Skipping.")
            continue
            
        div_name = df_div['division_name'].iloc[0]
        grand_total = 0
        email_body = f"<html><body style='font-family: Arial;'><h2>Weekly Enquiry Report: {div_name}</h2>"

        subdivisions = df_div['subdivision_name'].unique()
        
        for sub in subdivisions:
            df_sub = df_div[df_div['subdivision_name'] == sub]
            sub_total = df_sub['amount'].sum()
            grand_total += sub_total
            
            email_body += f"<h3>Subdivision: {sub}</h3>"
            email_body += """
            <table border='1' style='border-collapse: collapse; width: 100%; margin-bottom: 10px;'>
                <tr style='background-color: #f2f2f2;'>
                    <th style='width: 50px;'>S.No</th>
                    <th>Client Name</th>
                    <th>Enquiry Date</th>
                    <th>Status</th>
                    <th>Sector</th>
                    <th style='text-align:right;'>Amount</th>
                </tr>"""
            
            for s_no, (_, row) in enumerate(df_sub.iterrows(),1):
                email_body += f"""
                <tr>
                    <td style='text-align:center;'>{s_no}</td>
                    <td>{row['client_name']}</td>
                    <td>{row['enquiry_date']}</td>
                    <td style='color: red;'>{row['status']}</td>
                    <td>{row['sector']}</td>
                    <td style='text-align:right;'>{row['amount']:,.2f}</td>
                </tr>"""
            
            email_body += f"""
                <tr style='font-weight: bold; background-color: #fafafa;'>
                    <td colspan='5'>Subtotal for {sub}</td>
                    <td style='text-align:right;'>{sub_total:,.2f}</td>
                </tr>
            </table><br>"""

        email_body += f"""
        <div style='margin-top: 20px; padding: 10px; border-top: 2px solid #333;'>
            <h3 style='color: #2c3e50;'>Grand Total for {div_name}: {grand_total:,.2f}</h3>
        </div>
        </body></html>"""

        msg = EmailMessage()
        msg['Subject'] = f"Weekly Enquiries - {div_name} ({datetime.now().strftime('%d %b %Y')})"
        msg['From'] = EMAIL_CONFIG['sender_email']
        msg['To'] = EMAIL_CONFIG['admin_email']
        msg.add_alternative(email_body, subtype='html')

        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as smtp:
            if EMAIL_CONFIG['smtp_port'] == 587:
                smtp.starttls()
            smtp.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
            smtp.send_message(msg)
            print(f"Email sent for Division: {div_name}")

if __name__ == "__main__":
    send_division_emails()