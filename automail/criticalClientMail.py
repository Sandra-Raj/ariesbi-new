import duckdb
import smtplib
from email.message import EmailMessage
from config import EMAIL_CONFIG

def fetch_outstanding_debtors(file_path):
    con = duckdb.connect(database=':memory:')
    
    # CURRENT_DATE to calculate the 6-month window
    query = f"""
        SELECT 
            m.name AS debtor_name,
            c.client_status AS status,
            d.name AS company,
            d2.name AS division,
            d3.name AS subdivision,
            p.current_credit_period AS credit_period,
            -- Balance within last 6 months
            CASE 
                WHEN t.tran_date >= (CURRENT_DATE - INTERVAL '6 months') 
                THEN (t.ov_amount - t.alloc) * t.rate 
                ELSE 0 
            END AS bal_6m,
            (t.ov_amount - t.alloc) * t.rate AS bal_total
        FROM read_parquet('{file_path}/debtors_master.parquet') AS m
        JOIN read_parquet('{file_path}/client_status.parquet') AS c ON m.client_status = c.id
        JOIN read_parquet('{file_path}/debtor_trans.parquet') AS t ON m.debtor_no = t.debtor_no
        JOIN read_parquet('{file_path}/client_credit_period.parquet') AS p ON m.debtor_no = p.debtor_no
        LEFT JOIN read_parquet('{file_path}/dimensions.parquet') AS d ON t.dimension_id = d.id
        LEFT JOIN read_parquet('{file_path}/dimensions.parquet') AS d2 ON t.dimension2_id = d2.id
        LEFT JOIN read_parquet('{file_path}/dimensions.parquet') AS d3 ON t.dimension3_id = d3.id
        WHERE c.category = 2
    """
    
    try:
        results = con.execute(query).fetchall()
        columns = [desc[0] for desc in con.description]
        return [dict(zip(columns, row)) for row in results]
    except Exception as e:
        print(f"DuckDB Error: {e}")
        return []

def process_debtor_stats(raw_data):
    clients = {}

    for row in raw_data:
        name = row['debtor_name']
        if name not in clients:
            clients[name] = {
                'status': row['status'],
                'company': row['company'],
                'credit_period': row['credit_period'] or 0,
                'bal_6m': 0,
                'bal_total': 0,
                'mappings': {} # { 'Division': set(Subdivisions) }
            }
        
        # Update Balances
        clients[name]['bal_6m'] += row['bal_6m']
        clients[name]['bal_total'] += row['bal_total']
        
        # Update Division/Subdivision Mapping
        div = row['division'] or "No Division"
        sub = row['subdivision'] or "No Subdiv"
        
        if div not in clients[name]['mappings']:
            clients[name]['mappings'][div] = set()
        clients[name]['mappings'][div].add(sub)

    # Convert mappings to the "Div: [Sub1, Sub2]" string format
    final_list = []
    for name, info in clients.items():
        if info['bal_6m'] > 0:  # Only include if they have 6-month outstanding
            div_strings = []
            for div, subs in info['mappings'].items():
                div_strings.append(f"<b>{div}:</b> [{', '.join(subs)}]")
            
            info['debtor_name'] = name
            info['formatted_mappings'] = "<br>".join(div_strings)
            final_list.append(info)
            
    return sorted(final_list, key=lambda x: x['bal_6m'], reverse=True)

def generate_html_table(processed_data):
    table_rows = ""
    grand_total_6m = 0
    grand_total_abs = 0

    for i, row in enumerate(processed_data, start=1):
        grand_total_6m += row['bal_6m']
        grand_total_abs += row['bal_total']
        
        table_rows += f"""
        <tr>
            <td style="border:1px solid #ddd; padding:8px;">{i}</td>
            <td style="border:1px solid #ddd; padding:8px;">{row['debtor_name']}</td>
            <td style="border:1px solid #ddd; padding:8px;">{row['company']}</td>
            <td style="border:1px solid #ddd; padding:8px;">{row['status']}</td>
            <td style="border:1px solid #ddd; padding:8px; text-align:right;">{row['credit_period']}</td>
            <td style="border:1px solid #ddd; padding:8px; text-align:right;">{row['bal_6m']:,.2f}</td>
            <td style="border:1px solid #ddd; padding:8px; text-align:right;">{row['bal_total']:,.2f}</td>
            <td style="border:1px solid #ddd; padding:8px;">{row['formatted_mappings']}</td>
        </tr>
        """

    # Add the Footer Totals Row
    table_rows += f"""
    <tr style="background-color: #eee; font-weight: bold;">
        <td colspan="5" style="border:1px solid #ddd; padding:8px; text-align:right;">GRAND TOTAL</td>
        <td style="border:1px solid #ddd; padding:8px; text-align:right;">{grand_total_6m:,.2f}</td>
        <td style="border:1px solid #ddd; padding:8px; text-align:right;">{grand_total_abs:,.2f}</td>
        <td style="border:1px solid #ddd; padding:8px;">-</td>
    </tr>
    """

    return f"""
    <html>
    <body>
        <h2>Outstanding Debtors Report</h2>
        <table style="border-collapse: collapse; width: 100%; font-family: sans-serif;">
            <thead style="background-color: #f2f2f2;">
                <tr>
                    <th>S.No</th>
                    <th>Client</th>
                    <th>Company</th>
                    <th>Status</th>
                    <th>Current Credit Period</th>
                    <th>Outstanding (6 months, AED)</th>
                    <th>Total Outstanding (AED)</th>
                    <th><b>Division</b> And Subdivisions</th>
                </tr>
            </thead>
            <tbody>{table_rows}</tbody>
        </table>
    </body>
    </html>
    """


def send_notification(data):
    if not data:
        print("No critical clients found.")
        return

    msg = EmailMessage()
    msg['Subject'] = "Critical Clients Report"
    msg['From'] = EMAIL_CONFIG['sender_email']
    msg['To'] = EMAIL_CONFIG['admin_email']
    
    msg.add_alternative(generate_html_table(data), subtype='html')

    try:
        with smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['sender_email'], EMAIL_CONFIG['password'])
            server.send_message(msg)
            print(f"Success: Sent {len(data)} records via email.")
    except Exception as e:
        print(f"Email failed: {e}")

# --- Execution ---
folder_path = "c:/xampp/htdocs/ariesbi/ariesbi-analytics/data"
raw_data = fetch_outstanding_debtors(folder_path)
debtor_data = process_debtor_stats(raw_data)

if debtor_data:
    send_notification(debtor_data)
else:
    print("No outstanding transactions found for category 2 in the last 6 months.")