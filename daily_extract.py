import pandas as pd
from sqlalchemy import create_engine
from datetime import date
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT_DIR))

from app.config import DB_URL, DATA_DIR

engine = create_engine(DB_URL)
run_date=date(2020, 1, 1).isoformat();

DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "enquiry").mkdir(exist_ok=True)
(DATA_DIR / "job").mkdir(exist_ok=True)

""" TABLE DEBTORS MASTER"""

df_debtors_master = pd.read_sql("""
    SELECT debtor_no,debtor_code,name,address,po_box,city,country,phone,fax,email,date(added_date) AS added_date,client_credit_days,curr_code,client_type,area,client_status
    FROM 0_debtors_master
    WHERE inactive =0
""", engine)

""" TABLE SALES ORDER"""

df_sales_order = pd.read_sql("""
    SELECT order_no,trans_type,job_type,job_title,debtor_no,branch_code,reference,ord_date,dimension_id,dimension2_id,dimension3_id,rate
    FROM 0_sales_orders
""", engine)

df_sales_order['ord_date'] = pd.to_datetime(df_sales_order['ord_date'], errors='coerce')

""" TABLE SALES ORDER REFERENCES"""

df_sales_order_references = pd.read_sql("""
    SELECT sales_order_reference_id,trans_type,trans_no,ref_trans_type,ref_trans_no,reference
    FROM 0_sales_order_references
""", engine)

""" TABLE CUST ALLOCATIONS"""

df_cust_allocations = pd.read_sql("""
    SELECT id,alloc_amount,amt,date_alloc,trans_no_from,trans_type_from,trans_no_to,trans_type_to,bank_rate
    FROM 0_cust_allocations
""", engine)

df_cust_allocations['date_alloc'] = pd.to_datetime(df_cust_allocations['date_alloc'], errors='coerce')

""" TABLE CLIENT STATUS"""

df_client_status = pd.read_sql("""
    SELECT id, client_status, dissallow_job, dissallow_enquiry, dissallow_quotation, dissallow_invoice, category
    FROM 0_client_status
""", engine)

""" TABLE CLIENT TYPE"""

df_client_type = pd.read_sql("""
    SELECT id, client_type FROM 0_client_type
""", engine)

""" TABLE CLIENT CREDIT PERIOD"""

df_client_credit_period = pd.read_sql("""
    SELECT id, debtor_no, min_credit_period, date_of_min_payment, min_inv_date, min_trans_no, current_credit_period, date_of_curr_pmnt, curr_trans_no,curr_inv_date
    FROM 0_client_credit_period
""", engine)

""" TABLE COUNTRY"""

df_country = pd.read_sql("""
    SELECT id, name, region_id, colour_code
    FROM 0_country
    WHERE 1
""", engine)

""" TABLE REGION"""

df_region = pd.read_sql("""
    SELECT id, name
    FROM 0_region
    WHERE 1
""", engine)

""" TABLE TEMP_CLIENTS"""

df_temp_clients = pd.read_sql("""
    SELECT temp_clients_id, client_name, country, area, temp_client_type
    FROM 0_enquiry_temp_clients
    WHERE 1
""", engine)

""" TABLE DIMENSIONS"""
df_dimensions = pd.read_sql("""
    SELECT id,reference,name,full_name,sap_name,type_,parent,closed,date_,due_date,po_box,city,telephone,fax,company_currency,country,job_prefix,divisions,asset,
	liability,transfer_account,voucher_name,incentive_account,salary_bank_account,salary_cash_account,folder_name,ratio,branch_id,location_id,email,active,
	is_tree,time_zone,logo_sourcefile,logo_image,letterhead_sourcefile,letterhead_image,trade_license,vat_applicable,display_in_report,
	sort_order,gstin,state_id,pan_number,tax_mode,tax_label,display_client_tax_no,vat_no,des,close_date_,invoice_template_id,added_by,added_date,address,is_sap_company
FROM 0_dimensions
WHERE active=1
""", engine)


""" TABLE 0_client_type"""
df_client_type = pd.read_sql("""
    SELECT id, client_type FROM 0_client_type
""", engine)



df_enquiry = pd.read_sql(f"""
	SELECT 
  client_enquiry_id,
  branch_code,
  debtor_no,
  contact_id,
  temp_contact_id,
  enquiry_date,
  company,
  orginating_company,
  division,
  subdivision,
  received_by,
  person_in_charge,
  mod_of_com,
  description,
  reply_date,
  replied_by,
  vessel_name,
  place_of_survey,
  place_of_survey_country,
  vessel_class_id1,
  vessel_class_id2,
  enq_status,
  status_remarks,
  is_international,
  job_no,
  is_job_alloted,
  is_existing_client,
  followup,
  next_followup_date,
  written_no,
  remarks,
  job_title,
  is_quoted,
  is_email,
  email_date,
  email_remark,
  email_version,
  email_by,
  expected_date,
  book_no,
  aprox_amount,
  enquiry_from,
  activity_code,
  created_date,
  status_date,
  lost_description,
  enquiry_ref_id,
  transfer_to,
  parent_id,
  start_enquiry_id,
  is_shared,
  is_active,
  transfer_username,
  is_shutdown,
  is_annual,
  enq_type,
  file_name,
  main_category_id,
  sub_category_id,
  job_start_date,
  eff_inv_amount,
  currency,
  rate,
  new_rate,
  approval_id,
  approval_comments,
  client_type,
  is_msa,
  new_sub_category_id,
  client_agency,
  agency_percent,
  location_country,
  offshore,
  enquiry_temp_id
FROM 0_client_enquiry
WHERE enquiry_date >= '{run_date}' """, engine)

df_enquiry['enquiry_date'] = pd.to_datetime(df_enquiry['enquiry_date'], errors='coerce')

""" 0_DEBTOR_TRANS """

df_debtor_trans = pd.read_sql(f"""
    SELECT debtor_no,trans_no,tran_date,ov_amount,alloc,rate,tax_amount,total_expense_aed,order_,payment_terms,dimension2_id,dimension_id,dimension3_id
    FROM 0_debtor_trans
    WHERE tran_date >= '{run_date}'
""", engine)

df_debtor_trans['tran_date'] = pd.to_datetime(df_debtor_trans['tran_date'], errors='coerce')

""" 0_CLIENT_ACTIVITY_STATUS """ 

##################################################################################
df_client_activity_status = pd.read_sql("""
   SELECT id,temp_client,debtor_no,division,sub_division,enquiry_date,job_date,enquiry_no,sales_order_no,no_data,not_applicable,f_enquiry_date,f_enquiry_no,
   f_job_date,f_sales_order_no,country_id,region_id,client_type,temp_client_id,enquiry_temp_id,enquiry_amount,job_amount
FROM 0_client_activity_status
""", engine)

def normalize_mysql_dates(df):
    """Convert all object/date columns to datetime64[ns] safely for PyArrow."""
    for col in df.columns:
        if col.lower().endswith(("date", "_date", "date_","enquiry_date","job_date","job_da")):
            df[col] = pd.to_datetime(df[col].astype(str),format='%Y-%m-%d', errors="coerce")
    return df
####################################################################################

df_client_activity_status['enquiry_date'] = pd.to_datetime(df_client_activity_status['enquiry_date'],format='%Y-%m-%d', errors='coerce')
df_client_activity_status['job_date'] = pd.to_datetime(df_client_activity_status['job_date'],format='%Y-%m-%d', errors='coerce')
df_client_activity_status['f_enquiry_date'] = pd.to_datetime(df_client_activity_status['f_enquiry_date'],format='%Y-%m-%d', errors='coerce')
df_client_activity_status['f_job_date'] = pd.to_datetime(df_client_activity_status['f_job_date'],format='%Y-%m-%d', errors='coerce')

""" 0_CLIENT_ACTIVITY_CODE_STATUS """ 

df_client_activity_code_status = pd.read_sql("""
   SELECT id,activity_code,temp_client,debtor_no,division,sub_division,enquiry_date,job_date,enquiry_no,sales_order_no,no_data,
    not_applicable,f_enquiry_date,f_enquiry_no,f_job_date,f_sales_order_no,country_id,region_id,client_type,temp_client_id,
    enquiry_temp_id,status
FROM 0_client_activity_code_status
""", engine)

################################# JOB ACTIVITIES AND CLIENT ENQUIRY ACTIVITIES CLEANING AND SAVING AS PARUET ########################################

df_job_activities = pd.read_sql("""
   SELECT id,name,division_id,sub_division_id,activity_code,status
FROM 0_job_activities
""", engine)

df_client_enquiry_job_activity = pd.read_sql("""
   SELECT id,client_enquiry_id,activity_code
FROM 0_client_enquiry_activity
""", engine)

####################################################################################################
df_client_activity_code_status['enquiry_date'] = pd.to_datetime(df_client_activity_code_status['enquiry_date'],format='%Y-%m-%d', errors='coerce')
df_client_activity_code_status['job_date'] = pd.to_datetime(df_client_activity_code_status['job_date'],format='%Y-%m-%d', errors='coerce')
df_client_activity_code_status['f_enquiry_date'] = pd.to_datetime(df_client_activity_code_status['f_enquiry_date'],format='%Y-%m-%d', errors='coerce')
df_client_activity_code_status['f_job_date'] = pd.to_datetime(df_client_activity_code_status['f_job_date'],format='%Y-%m-%d', errors='coerce')

df_dimensions["date_"] = (pd.to_datetime( df_dimensions["date_"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_dimensions["due_date"] = (pd.to_datetime( df_dimensions["due_date"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_dimensions["close_date_"] = (pd.to_datetime( df_dimensions["close_date_"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_dimensions["added_date"] = (pd.to_datetime( df_dimensions["added_date"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_debtors_master["added_date"] = (pd.to_datetime( df_debtors_master["added_date"].astype(str),format='%Y-%m-%d',errors="coerce"))

df_client_credit_period["date_of_min_payment"] = (pd.to_datetime( df_client_credit_period["date_of_min_payment"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_client_credit_period["min_inv_date"] = (pd.to_datetime( df_client_credit_period["min_inv_date"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_client_credit_period["date_of_curr_pmnt"] = (pd.to_datetime( df_client_credit_period["date_of_curr_pmnt"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_client_credit_period["curr_inv_date"] = (pd.to_datetime( df_client_credit_period["curr_inv_date"].astype(str),format='%Y-%m-%d',errors="coerce"))

df_enquiry["enquiry_date"] = (pd.to_datetime( df_enquiry["enquiry_date"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_enquiry["reply_date"] = (pd.to_datetime( df_enquiry["reply_date"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_enquiry["next_followup_date"] = (pd.to_datetime( df_enquiry["next_followup_date"].astype(str),format='%Y-%m-%d',errors="coerce"))
df_enquiry["email_date"] = (pd.to_datetime( df_enquiry["email_date"].astype(str),format='%Y-%m-%d',errors="coerce"))

df_debtors_master = normalize_mysql_dates(df_debtors_master)
df_country = normalize_mysql_dates(df_country)
df_region = normalize_mysql_dates(df_region)
df_enquiry = normalize_mysql_dates(df_enquiry)
df_dimensions = normalize_mysql_dates(df_dimensions)
df_sales_order = normalize_mysql_dates(df_sales_order)
df_cust_allocations = normalize_mysql_dates(df_cust_allocations)
df_client_type = normalize_mysql_dates(df_client_type)
df_debtor_trans = normalize_mysql_dates(df_debtor_trans)
df_client_activity_status = normalize_mysql_dates(df_client_activity_status)
df_client_activity_code_status = normalize_mysql_dates(df_client_activity_code_status)
df_client_credit_period = normalize_mysql_dates(df_client_credit_period)
df_temp_clients = normalize_mysql_dates(df_temp_clients)
df_job_activities = normalize_mysql_dates(df_job_activities)
df_client_enquiry_job_activity = normalize_mysql_dates(df_client_enquiry_job_activity)

df_debtors_master.to_parquet(DATA_DIR / "debtors_master.parquet", index=False,engine="pyarrow")
df_country.to_parquet(DATA_DIR / "country.parquet", index=False,engine="pyarrow")
df_region.to_parquet(DATA_DIR / "region.parquet", index=False,engine="pyarrow")
df_dimensions.to_parquet(DATA_DIR / "dimensions.parquet", index=False,engine="pyarrow")
df_enquiry.to_parquet(DATA_DIR / "client_enquiry.parquet", index=False,engine="pyarrow")
df_client_type.to_parquet(DATA_DIR / "client_type.parquet", index=False,engine="pyarrow")
df_debtor_trans.to_parquet(DATA_DIR / "debtor_trans.parquet", index=False,engine="pyarrow")
df_client_activity_status.to_parquet(DATA_DIR / "client_activity_status.parquet", index=False,engine="pyarrow")
df_client_activity_code_status.to_parquet(DATA_DIR / "client_activity_code_status.parquet", index=False,engine="pyarrow")
df_temp_clients.to_parquet(DATA_DIR /"temp_clients.parquet", index=False,engine="pyarrow")
df_job_activities.to_parquet(DATA_DIR / "job_activities.parquet", index=False,engine="pyarrow")
df_client_enquiry_job_activity.to_parquet(DATA_DIR / "client_enquiry_job_activity.parquet", index=False,engine="pyarrow")
df_client_status.to_parquet(DATA_DIR / "client_status.parquet", index=False,engine="pyarrow")
df_client_credit_period.to_parquet(DATA_DIR / "client_credit_period.parquet", index=False,engine="pyarrow")
df_sales_order.to_parquet(DATA_DIR / "sales_order.parquet", index=False,engine="pyarrow")
df_cust_allocations.to_parquet(DATA_DIR / "cust_allocations.parquet", index=False,engine="pyarrow")
df_sales_order_references.to_parquet(DATA_DIR / "sales_order_references.parquet", index=False,engine="pyarrow")
df_client_type.to_parquet(DATA_DIR / "sector.parquet", index=False,engine="pyarrow")
print("Daily extract completed")
