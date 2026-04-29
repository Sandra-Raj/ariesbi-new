import smtplib
import mysql.connector
from datetime import datetime, date, timedelta
from email.message import EmailMessage
from config import EMAIL_CONFIG, DB_CONFIG

def fetch_inactive_client_data():
    try:
        db = mysql.connector.connect(**DB_CONFIG)
        cursor = db.cursor(dictionary=True) # Returns results as dictionaries
        
        inactive_query = """
        SELECT 
            m.debtor_no, 
            m.name AS client_name, 
            m.client_status AS status_id,
            la.division AS div_id,
            la.last_job_date, 
            la.last_enquiry_date,
            p.current_credit_period,
            d2.name AS div_name,
            -- Financials calculated only for the filtered clients
            (SELECT SUM(ov_amount * rate) FROM `0_debtor_trans` WHERE debtor_no = m.debtor_no) AS total_business,
            (SELECT SUM((ov_amount - alloc) * rate) FROM `0_debtor_trans` WHERE debtor_no = m.debtor_no) AS total_outstanding
        FROM (
            SELECT debtor_no, division, 
            MAX(job_date) AS last_job_date, 
            MAX(enquiry_date) AS last_enquiry_date
            FROM `0_client_activity_status`
            GROUP BY debtor_no, division
            HAVING MAX(job_date) BETWEEN (CURRENT_DATE - INTERVAL 36 MONTH) AND (CURRENT_DATE - INTERVAL 12 MONTH)
        ) la
        JOIN `0_debtors_master` m ON la.debtor_no = m.debtor_no
        JOIN `0_client_credit_period` p ON la.debtor_no = p.debtor_no
        JOIN `0_dimensions` d2 ON la.division = d2.id
        WHERE m.client_type != 5
        """

        improvement_query = """
            SELECT 
                t.debtor_no, 
                m.name AS client_name, 
                d.name AS div_name, 
                t.division_id,
                MAX(s.job_date) AS recovered_date
            FROM `0_inactive_tracking` t
            JOIN `0_debtors_master` m ON t.debtor_no = m.debtor_no
            JOIN `0_dimensions` d ON t.division_id = d.id
            JOIN `0_client_activity_status` s ON s.debtor_no = t.debtor_no AND s.division = t.division_id
            WHERE s.job_date > t.last_job_date
            AND s.job_date > (CURRENT_DATE - INTERVAL 11 MONTH)
            GROUP BY t.debtor_no, m.name, d.name, t.division_id
        """
        cursor.execute(improvement_query)
        improvements = cursor.fetchall()

        # 2. DELETE RECOVERED CLIENTS
        if improvements:
            for imp in improvements:
                cursor.execute(
                    "DELETE FROM `0_inactive_tracking` WHERE debtor_no = %s AND division_id = %s",
                    (imp['debtor_no'], imp['division_id'])
                )

        # 3. FETCH THIS MONTH'S INACTIVE LIST (Using optimized query above)
        cursor.execute(inactive_query) # The query from section 1
        current_inactive_list = cursor.fetchall()

        # 4. UPDATE TRACKING TABLE FOR NEXT MONTH
        # Use 'INSERT IGNORE' to prevent duplicates if the script runs twice
        insert_sql = """
            INSERT IGNORE INTO `0_inactive_tracking` (debtor_no, division_id, last_job_date, logged_at)
            VALUES (%s, %s, %s, NOW())
        """
        data_to_insert = [(row['debtor_no'], row['div_id'], row['last_job_date']) for row in current_inactive_list]
        if data_to_insert:
            cursor.executemany(insert_sql, data_to_insert)

        db.commit()
        cursor.close()
        db.close()
        return current_inactive_list, improvements

    except mysql.connector.Error as err:
        print(f"MySQL Error: {err}")
        return [], []

def build_improvement_html(improvements, current_div_name):
    # Filter for the specific division
    if current_div_name == "Non Marine":
        div_imps = [i for i in improvements if i['div_name'] not in ["I&M", "ONE"]]
    else:
        div_imps = [i for i in improvements if i['div_name'] == current_div_name]

    if not div_imps:
        return ""

    rows = ""
    for i, imp in enumerate(div_imps, start=1):
        date_str = imp['recovered_date'].strftime('%d-%b-%Y') if imp['recovered_date'] else "N/A"
        rows += f"""
        <tr>
            <td>{i}</td>
            <td>{imp['client_name']}</td>
            <td>{date_str}</td>
        </tr>
        """

    return f"""
    <div style="margin-bottom: 30px; border: 1px solid #d6e9c6; padding: 15px; border-radius: 4px; background-color: #f9fdf9;">
        <h3 style="color: #3c763d; margin-top: 0;">🎉 Monthly Improvement: Recovered Clients</h3>
        <p style="font-size: 0.9em; color: #555;">The following clients were previously inactive but have provided new business in the last month.</p>
        <table style="width: 100%; border-collapse: collapse; font-family: Arial, sans-serif;">
            <thead>
                <tr style="background-color: #dff0d8; color: #3c763d;">
                    <th style="border: 1px solid #ccc; padding: 8px; width: 50px;">S.No</th>
                    <th style="border: 1px solid #ccc; padding: 8px;">Client Name</th>
                    <th style="border: 1px solid #ccc; padding: 8px; width: 150px;">New Job Date</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
    </div>
    <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
    """

def build_html(data, title, imp_section):
    is_single = title in ["I&M", "ONE"]
    table_rows = ""
    for i, (name, info) in enumerate(data.items(), start=1):
        # BOLD LOGIC for Status 6
        is_urgent = info['status_id'] == 6
        row_style = 'style="font-weight: bold; color: #d9534f;"' if is_urgent else ""
        biz_val = info.get('biz') or 0
        out_val = info.get('out') or 0
        last_job_str = info['last_job'].strftime('%d-%b-%Y') if info['last_job'] else 'N/A'
        last_enq_str = info['last_enq'].strftime('%d-%b-%Y') if info['last_enq'] else 'N/A'
        table_rows += f"""
        <tr {row_style}>
            <td>{i}</td>
            <td>{name} {'⚠️' if is_urgent else ''}</td>
            <td>{last_job_str}</td>
            <td>{last_enq_str}</td>
            <td>{info['credit_period'] or 0}</td>
            <td style="text-align:right;">{biz_val:,.2f}</td>
            <td style="text-align:right;">{out_val:,.2f}</td>
        </tr>
        """

    return f"""
    <html>
    <head>
        <style>
            table {{ 
                border-collapse: collapse; 
                width: 100%; 
                table-layout: fixed; /* CRITICAL: Forces columns to respect set widths */
                font-family: Arial, sans-serif; 
            }}
            th, td {{ 
                border: 1px solid #ccc; 
                padding: 8px; 
                word-wrap: break-word; /* Ensures long names wrap to next line instead of stretching the cell */
            }}
            th {{ background-color: #eee; text-align: center; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <h3>{title} Inactive Client Report</h3>
        {imp_section}
        <table border="1" style="border-collapse: collapse; width: 100%;">
            <tr style="background-color: #eee;">
                <th>S.No</th><th>Client Name</th><th>Last Job</th><th>Last Enquiry</th>
                <th>Credit</th><th>Business</th><th>Outstanding</th>
            </tr>
            {table_rows}
        </table>
    </body>
    </html>
    """

# --- [Keep your existing fetch and helper functions until bucket_data] ---

def bucket_data(data_list):
    # Mapping to separate our three emails
    buckets = {"I&M": {}, "ONE": {}, "Non Marine": {}}
    
    for row in data_list:
        div = row.get('div_name')
        # Assign to specific bucket or default to 'Non Marine'
        if div == "I&M":
            target = buckets["I&M"]
        elif div == "ONE":
            target = buckets["ONE"]
        else:
            target = buckets["Non Marine"]
        
        name = row['client_name']
        current_job_date = row['last_job_date']
        current_enq_date = row['last_enquiry_date']

        if name not in target:
            # First time seeing this client in this bucket
            target[name] = {
                'client_name': name,
                'status_id': row['status_id'],
                'last_job': current_job_date,
                'last_enq': current_enq_date,
                'credit_period': row['current_credit_period'] or 0,
                'biz': row['total_business'] or 0,
                'out': row['total_outstanding'] or 0,
            }
        else:
            # Update to the MAX Job Date
            if current_job_date and (not target[name]['last_job'] or current_job_date > target[name]['last_job']):
                target[name]['last_job'] = current_job_date
            
            # Update to the MAX Enquiry Date
            if current_enq_date and (not target[name]['last_enq'] or current_enq_date > target[name]['last_enq']):
                target[name]['last_enq'] = current_enq_date
        
    return buckets

# --- [Keep your get_improvements_and_update and build_improvement_html] ---

def send_notification(data, title, imp_section):
    """Modified to accept the pre-built imp_section and data"""
    if not data and not imp_section:
        print(f"No data or improvements for {title}. Skipping.")
        return

    msg = EmailMessage()
    msg['Subject'] = f"Inactive Clients Report - {title}"
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['admin_email']
    
    # We call build_html here and pass the section
    html_content = build_html(data, title, imp_section)
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
            server.send_message(msg)
            print(f"Success: Sent {title} report.")
    except Exception as e:
        print(f"Email failed for {title}: {e}")

# --- MAIN EXECUTION FLOW ---

def main():
    # 1. Get inactive list for this month
    raw_data, improvements = fetch_inactive_client_data()
    buckets = bucket_data(raw_data)

    # 3. Process each email category
    for category in ['I&M', 'ONE', 'Non Marine']:
        data_for_email = buckets[category]
        imp_section = build_improvement_html(improvements, category)
        
        # Send notification (Logic handles empty data inside)
        send_notification(data_for_email, category, imp_section)

if __name__ == "__main__":
    main()