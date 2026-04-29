import mysql.connector
import smtplib
from email.message import EmailMessage
from config import DB_CONFIG, EMAIL_CONFIG

def fetch_high_value_enquiries(target_date):
    connection = None
    try:
        # 1. Connect to MySQL
        connection = mysql.connector.connect(**DB_CONFIG)
        cursor = connection.cursor(dictionary=True)

        # 2. Execute Query
        # Using parameterized queries to prevent SQL injection
        query = """
            SELECT 
                e.book_no,
                dc.name AS company,
                dv.name AS division,
                ds.name AS subdivision,
                CASE 
                    WHEN e.debtor_no != 0 AND e.branch_code != 0 THEN d.name
                    WHEN e.enquiry_temp_id != 0 THEN t.client_name
                    ELSE 'Unknown'
                END AS client,
                cn.name AS country,
                CASE e.enq_type
                    WHEN 1 THEN 'Project'
                    WHEN 2 THEN 'Annual Contract'
                    WHEN 3 THEN 'Shutdown'
                    WHEN 4 THEN 'Callout'
                    WHEN 5 THEN 'Tender'
                    ELSE 'Other'
                END AS enquiry_type,
                CASE e.enq_status
                    WHEN 0 THEN 'Open'
                    WHEN 1 THEN 'Cancel'
                    WHEN 2 THEN 'Lost'
                    WHEN 3 THEN 'Transfer'
                    WHEN 4 THEN 'Confirmed'
                    WHEN 5 THEN 'BID Enquiry'
                    ELSE 'Other'
                END AS enquiry_status
            FROM `0_client_enquiry` e
            LEFT JOIN `0_dimensions` dc ON e.company = dc.id
            LEFT JOIN `0_dimensions` dv ON e.division = dv.id
            LEFT JOIN `0_dimensions` ds ON e.subdivision = ds.id
            LEFT JOIN `0_debtors_master` d ON e.debtor_no = d.debtor_no
            LEFT JOIN `0_enquiry_temp_clients` t ON e.enquiry_temp_id = t.temp_clients_id
            LEFT JOIN `0_country` cn ON cn.id = (
                CASE 
                    WHEN e.debtor_no != 0 AND e.branch_code != 0 THEN d.country
                    ELSE t.country
                END
            )
            WHERE e.enquiry_date = %s AND (e.aprox_amount*rate) > 500000 AND parent_id = 0 AND is_active = 1 AND enq_status<=5
        """
        cursor.execute(query, (target_date,))
        results = cursor.fetchall()
        
        return results

    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
        return []
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()

def send_notification(data):
    if not data:
        print("No high-value enquiries found.")
        return

    msg = EmailMessage()
    msg['Subject'] = "High Value Enquiry Summary Report"
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['admin_email']

    # Create HTML Table
    table_rows = ""
    for index, row in enumerate(data, start=1):
        table_rows += f"""
        <tr>
            <td style="border: 1px solid #ddd; padding: 8px;">{index}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row['book_no']}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row['company']}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row['division']}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row['subdivision']}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row['client']}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row['country']}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row['enquiry_type']}</td>
            <td style="border: 1px solid #ddd; padding: 8px;">{row['enquiry_status']}</td>
        </tr>
        """

    html_content = f"""
    <html>
    <body>
        <h2>High Value Enquiry Details (> 500,000)</h2>
        <table style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif;">
            <thead style="background-color: #f2f2f2;">
                <tr>
                    <th style="border: 1px solid #ddd; padding: 8px;">S.No</th>
                    <th style="border: 1px solid #ddd; padding: 8px;">Book No</th>
                    <th style="border: 1px solid #ddd; padding: 8px;">Company</th>
                    <th style="border: 1px solid #ddd; padding: 8px;">Division</th>
                    <th style="border: 1px solid #ddd; padding: 8px;">Subdivision</th>
                    <th style="border: 1px solid #ddd; padding: 8px;">Client</th>
                    <th style="border: 1px solid #ddd; padding: 8px;">Country</th>
                    <th style="border: 1px solid #ddd; padding: 8px;">Enquiry Type</th>
                    <th style="border: 1px solid #ddd; padding: 8px;">Status</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
    </body>
    </html>
    """
    
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
            server.send_message(msg)
            print(f"Success: Sent {len(data)} records via email.")
    except Exception as e:
        print(f"Email failed: {e}")

# --- Execution ---
if __name__ == "__main__":
    # Example: Check for enquiries from yesterday or a specific date
    date_to_check = "2026-03-28"  # yyyy-dd-mm
    enquiry_data = fetch_high_value_enquiries(date_to_check)
    send_notification(enquiry_data)