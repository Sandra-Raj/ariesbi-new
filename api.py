from fastapi import APIRouter, Query
import pandas as pd
from app.config import DATA_DIR
from app.constants import (
    ACTIVE_FROM_DATE, ACTIVE_TO_DATE,
    INACTIVE_FROM_DATE, INACTIVE_TO_DATE,
    LOST_TO_DATE,PREV_JOB_TO_DATE,PREV_JOB_FROM_DATE,PREV_ENQUIRY_FROM_DATE,JOB_FROM_DATE,
    JOB_TO_DATE, NON_MARINE_DIVISION
)
import duckdb
import numpy as np

con = duckdb.connect()
router = APIRouter(prefix="/client_activity", tags=["Client Activity"])

# ---- Load & normalize data ONCE ----

df_client_activity_status = pd.read_parquet(
    DATA_DIR / "client_activity_status.parquet"
)

df_debtors_master = pd.read_parquet(
    DATA_DIR / "debtors_master.parquet"
)

df_client_enquiry = pd.read_parquet(
    DATA_DIR / "client_enquiry.parquet"
)
############################################################################
df_debtor_trans = pd.read_parquet(
    DATA_DIR / "debtor_trans.parquet"
)

df_client_activity_code_status = pd.read_parquet(
    DATA_DIR / "client_activity_code_status.parquet"
)
df_temp_clients = pd.read_parquet(
    DATA_DIR / "temp_clients.parquet"
)

df_region = pd.read_parquet(
    DATA_DIR / "region.parquet"
)

df_country = pd.read_parquet(
    DATA_DIR / "country.parquet"
)

query = f"""

    SELECT
        c.country_id as country,
        d.name AS country_name,
        ANY_VALUE(r.name) AS region_name,
        ANY_VALUE(c.debtor_no) AS debtor_no,
        MAX(c.enquiry_date) enquiry_date,
        MAX(c.job_date) job_date,
        ANY_VALUE(c.client_type),
       ANY_VALUE(c.division),
       ANY_VALUE(c.sub_division)
        
    FROM '{DATA_DIR}/client_activity_status.parquet' c
    LEFT JOIN '{DATA_DIR}/country.parquet' d
        ON c.country_id = d.id
    LEFT JOIN '{DATA_DIR}/region.parquet' r
        ON c.region_id = r.id
    WHERE c.country_id IS NOT NULL AND c.country_id > 0 AND c.client_type!=5 
    GROUP BY c.country_id, country_name
    """
   
df_client_country_status = con.execute(query).fetchdf()

############################# CLIENT STATUS###############################################
query = f"""
    SELECT
        COALESCE(c.debtor_no, ANY_VALUE(c.temp_client_id)) AS debtor_no,
        MAX(c.enquiry_date) AS enquiry_date,
        MAX(c.job_date) AS job_date,
        ANY_VALUE(c.division) AS division,
        ANY_VALUE(c.sub_division) AS sub_division,
        ANY_VALUE(d.client_status) AS client_category,
        ANY_VALUE(IF(c.temp_client_id>0, CONCAT('TMP', CAST(c.temp_client_id AS VARCHAR)), '')) AS client_status,
        ANY_VALUE(CASE
            WHEN c.debtor_no IS NOT NULL
                THEN CAST(c.debtor_no AS VARCHAR)
            ELSE  CAST(c.temp_client_id AS VARCHAR)
        END ) AS client_id,
        ANY_VALUE(COALESCE(d.name, tm.client_name)) AS client_name,
        ANY_VALUE(ty.client_type) AS client_type,
        ANY_VALUE(c.temp_client_id) AS temp_client_id

    FROM '{DATA_DIR}/client_activity_status.parquet' c
    LEFT JOIN '{DATA_DIR}/debtors_master.parquet' d
        ON c.debtor_no = d.debtor_no
    LEFT JOIN '{DATA_DIR}/temp_clients.parquet' tm
        ON tm.temp_clients_id = c.temp_client_id
    LEFT JOIN '{DATA_DIR}/client_type.parquet' ty
        ON c.client_type = ty.id
    WHERE c.country_id > 0
    AND c.enquiry_date >= DATE '2020-01-01'
    AND c.client_type != 5 
GROUP BY c.debtor_no,c.temp_client_id"""
df_client_status = con.execute(query).fetchdf()
###########################################################################

df_debtor_trans["ov_amount"] = pd.to_numeric(
    df_debtor_trans["ov_amount"], errors="coerce"
).fillna(0)
df_debtor_trans["rate"] = pd.to_numeric(
    df_debtor_trans["rate"], errors="coerce"
).fillna(0)
df_debtor_trans["total_expense_aed"] = pd.to_numeric(
    df_debtor_trans["total_expense_aed"], errors="coerce"
).fillna(0)
#####################################################################
df_client_enquiry["aprox_amount"] = pd.to_numeric(
    df_client_enquiry["aprox_amount"], errors="coerce"
).fillna(0)
df_client_enquiry["rate"] = pd.to_numeric(
    df_client_enquiry["rate"], errors="coerce"
).fillna(0)
df_client_enquiry["enq_status"] = pd.to_numeric(
    df_client_enquiry["enq_status"], errors="coerce"
).fillna(0)

df_client_enquiry["enquiry_date"] = pd.to_datetime(df_client_enquiry["enquiry_date"])
filter_client_enquiry_prev_data = df_client_enquiry[
    (df_client_enquiry['enquiry_date']>=PREV_ENQUIRY_FROM_DATE) &
    (df_client_enquiry['enquiry_date']<INACTIVE_TO_DATE) &
    (df_client_enquiry['enq_status']!=3)
]

# Sum of approx_amnt * rate
total_prev_enquiry_amount = (filter_client_enquiry_prev_data["aprox_amount"] * 
                          filter_client_enquiry_prev_data["rate"]).sum()

filter_client_enquiry_curr_data = df_client_enquiry[
    (df_client_enquiry['enquiry_date']>ACTIVE_FROM_DATE) &
    (df_client_enquiry['enquiry_date']<ACTIVE_TO_DATE) &
    (df_client_enquiry['enq_status']!=3)
]


# Sum of approx_amnt * rate
total_curr_enquiry_amount = (filter_client_enquiry_curr_data["aprox_amount"] * 
                          filter_client_enquiry_curr_data["rate"]).sum()

growth_value = total_curr_enquiry_amount-total_prev_enquiry_amount

growth_per = round(((total_curr_enquiry_amount-total_prev_enquiry_amount)/total_prev_enquiry_amount)*100,1)
#############################CLIENT ENQUIRY PERCENTAGE###################################
  # Join
df_client_enquiry_merged = pd.merge(
	df_client_enquiry,
	df_debtors_master,
	how="left",
	on=["debtor_no"],
    suffixes=("_ce", "_dm")
)

filter_client_enquiry_one = df_client_enquiry_merged[
    (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
    (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
    (df_client_enquiry_merged['client_type_ce']!=5) &
    (df_client_enquiry_merged['division']==3)
]
# Sum of approx_amnt * rate
total_one_enquiry = (filter_client_enquiry_one["aprox_amount"] * 
                          filter_client_enquiry_one["rate"]).sum()

one_enquiry_per = round((total_one_enquiry/total_curr_enquiry_amount)*100,2)

#######################################IM DIVISIONENQUIRY ########################
filter_client_enquiry_IM = df_client_enquiry_merged[
    (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
    (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
    (df_client_enquiry_merged['client_type_ce']!=5) &
    (df_client_enquiry_merged['division']==225)
]
# Sum of approx_amnt * rate
total_IM_enquiry = (filter_client_enquiry_IM["aprox_amount"] * 
                          filter_client_enquiry_IM["rate"]).sum()

IM_enquiry_per = round((total_IM_enquiry/total_curr_enquiry_amount)*100,2)
################################CLIENT ENQUIRY SECTOR ############################
filter_client_enquiry_renewable = df_client_enquiry_merged[
    (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
    (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
    (df_client_enquiry_merged['client_type_ce']==12) 
]
# Sum of approx_amnt * rate
total_renewable_enquiry = (filter_client_enquiry_IM["aprox_amount"] * 
                          filter_client_enquiry_IM["rate"]).sum()

#--------------------------------OIL-------------------------------------

filter_client_enquiry_oilgas = df_client_enquiry_merged[
    (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
    (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
    (df_client_enquiry_merged['client_type_ce']==3) 
]
# Sum of approx_amnt * rate
total_oilgas_enquiry = (filter_client_enquiry_oilgas["aprox_amount"] * 
                          filter_client_enquiry_oilgas["rate"]).sum()
#--------------------------------INDUSTRIAL-------------------------------------
filter_client_enquiry_industrial = df_client_enquiry_merged[
    (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
    (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
    (df_client_enquiry_merged['client_type_ce']==1) 
]
# Sum of approx_amnt * rate
total_industrial_enquiry = (filter_client_enquiry_industrial["aprox_amount"] * 
                          filter_client_enquiry_industrial["rate"]).sum()
#--------------------------------PETROCHEMICAL-------------------------------------
filter_client_enquiry_petrochemical = df_client_enquiry_merged[
    (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
    (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
    (df_client_enquiry_merged['client_type_ce']==10) 
]
# Sum of approx_amnt * rate
total_petrochecmical_enquiry = (filter_client_enquiry_petrochemical["aprox_amount"] * 
                          filter_client_enquiry_petrochemical["rate"]).sum()
#--------------------------------OFFSHORE-------------------------------------
filter_client_enquiry_offshore = df_client_enquiry_merged[
    (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
    (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
    (df_client_enquiry_merged['client_type_ce']==6) 
]
# Sum of approx_amnt * rate
total_offshore_enquiry = (filter_client_enquiry_offshore["aprox_amount"] * 
                          filter_client_enquiry_offshore["rate"]).sum()
#--------------------------------MARINE-------------------------------------
filter_client_enquiry_marine = df_client_enquiry_merged[
    (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
    (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
    (df_client_enquiry_merged['client_type_ce']==2) 
]
# Sum of approx_amnt * rate
total_marine_enquiry = (filter_client_enquiry_marine["aprox_amount"] * 
                          filter_client_enquiry_marine["rate"]).sum()
##########################################PREV INVOICE########################################
df_debtor_trans["tran_date"] = pd.to_datetime(df_debtor_trans["tran_date"])
df_debtor_trans["dimension2_id"] = pd.to_numeric(
    df_debtor_trans["dimension2_id"], errors="coerce"
).fillna(0)
 # Join
df_invoice_merged = pd.merge(
	df_debtor_trans,
	df_debtors_master,
	how="left",
	on=["debtor_no"],
    suffixes=("_dt", "_dm")
)
df_invoice_merged['client_type'] = df_invoice_merged['client_type'].astype(int)
filter_invoice_prev_data = df_invoice_merged[
    (df_invoice_merged['tran_date']>=PREV_JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=PREV_JOB_TO_DATE) &
    (df_invoice_merged['client_type']!=5)
]
# Sum of approx_amnt * rate
total_prev_invoice_amount = ((filter_invoice_prev_data["ov_amount"] * 
                          filter_invoice_prev_data["rate"])-filter_invoice_prev_data['total_expense_aed']).sum()

# Sum of ov_amount * rate
total_prev_gross_invoice_amount = ((filter_invoice_prev_data["ov_amount"]*filter_invoice_prev_data["rate"])).sum()

filter_invoice_curr_data = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']!=5)
]
# Sum of approx_amnt * rate
total_curr_invoice_amount = ((filter_invoice_curr_data["ov_amount"] * 
                          filter_invoice_curr_data["rate"])-filter_invoice_curr_data['total_expense_aed']).sum()

total_curr_gross_invoice_amount = ((filter_invoice_curr_data["ov_amount"]*filter_invoice_curr_data["rate"])).sum()

invoice_growth_value = total_curr_invoice_amount-total_prev_invoice_amount
invoice_gross_growth_value = total_curr_gross_invoice_amount-total_prev_gross_invoice_amount
invoice_gross_growth_per=round((invoice_gross_growth_value/total_prev_gross_invoice_amount)*100,2)
invoice_growth_per = round((invoice_growth_value/total_prev_invoice_amount)*100,2)

#---------------------------------------------RENEWABLE ENERGY__________________
filter_invoice_renewable = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']==12)
]

# Sum of approx_amnt * rate
total_renewable_invoice_amount = ((filter_invoice_renewable["ov_amount"] * 
                          filter_invoice_renewable["rate"])-filter_invoice_renewable['total_expense_aed']).sum()
#---------------------------------------------OILGAS__________________
filter_invoice_oilgas = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']==3)
]

# Sum of approx_amnt * rate
total_oilgas_invoice_amount = ((filter_invoice_oilgas["ov_amount"] * 
                          filter_invoice_oilgas["rate"])-filter_invoice_oilgas['total_expense_aed']).sum()
#---------------------------------------------INDUSTRIAL__________________
filter_invoice_industrial = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']==1)
]
# Sum of approx_amnt * rate
total_industrial_invoice_amount = ((filter_invoice_industrial["ov_amount"] * 
                          filter_invoice_industrial["rate"])-filter_invoice_industrial['total_expense_aed']).sum()
#---------------------------------------------PETROCHECMICAL__________________
filter_invoice_petrochemical = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']==10)
]
# Sum of approx_amnt * rate
total_petrochemical_invoice_amount = ((filter_invoice_petrochemical["ov_amount"] * 
                          filter_invoice_petrochemical["rate"])-filter_invoice_petrochemical['total_expense_aed']).sum()
#---------------------------------------------OFFSHORE__________________
filter_invoice_offshore = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']==6)
]
# Sum of approx_amnt * rate
total_offshore_invoice_amount = ((filter_invoice_offshore["ov_amount"] * 
                          filter_invoice_offshore["rate"])-filter_invoice_offshore['total_expense_aed']).sum()
#---------------------------------------------MARINE__________________
filter_invoice_marine = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']==2)
]
# Sum of approx_amnt * rate
total_marine_invoice_amount = ((filter_invoice_marine["ov_amount"] * 
                          filter_invoice_marine["rate"])-filter_invoice_marine['total_expense_aed']).sum()
###########################################ONE DIVISIOn ###############################################
filter_invoice_one_data = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']!=5) &
    (df_invoice_merged['dimension2_id']==3)
    ]

total_one_invoice_amount = ((filter_invoice_one_data["ov_amount"] * 
                          filter_invoice_one_data["rate"])-filter_invoice_one_data['total_expense_aed']).sum()
one_per = round((total_one_invoice_amount/total_curr_invoice_amount)*100,2)
########################################I&M DIVISION ######################################
filter_invoice_IM_data = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']!=5) &
    (df_invoice_merged['dimension2_id']==225)
    ]
total_IM_invoice_amount = ((filter_invoice_IM_data["ov_amount"] * 
                          filter_invoice_IM_data["rate"])-filter_invoice_IM_data['total_expense_aed']).sum()
IM_per = round((total_IM_invoice_amount/total_curr_invoice_amount)*100,2)
########################################NON MARINE DIVISION ######################################
filter_invoice_non_marine_data = df_invoice_merged[
    (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
    (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
    (df_invoice_merged['client_type']!=5) &
    (df_invoice_merged['dimension2_id'].isin(NON_MARINE_DIVISION))
    ]
total_nonmarine_invoice_amount = ((filter_invoice_non_marine_data["ov_amount"] * 
                          filter_invoice_non_marine_data["rate"])-filter_invoice_non_marine_data['total_expense_aed']).sum()
nonmarine_per = round((total_nonmarine_invoice_amount/total_curr_invoice_amount)*100,2)
#################################################################################################

query = f"""
    SELECT
        ja.activity_code,
        ANY_VALUE(d.name) AS country_name,
        ANY_VALUE(r.name) AS region_name,
        ANY_VALUE(c.debtor_no) AS debtor_no,
        MAX(c.enquiry_date) enquiry_date,
        MAX(c.job_date) job_date,
        ANY_VALUE(c.client_type) AS client_type,
        ANY_VALUE(c.division) AS division,
        ANY_VALUE(c.sub_division) AS sub_division,
        ANY_VALUE(d.region_id) AS region_id,
        ANY_VALUE(ja.status) AS status
    FROM '{DATA_DIR}/job_activities.parquet' ja
    LEFT JOIN '{DATA_DIR}/client_activity_code_status.parquet' c
    ON c.activity_code = ja.activity_code
    LEFT JOIN '{DATA_DIR}/country.parquet' d
        ON c.country_id = d.id
    LEFT JOIN '{DATA_DIR}/region.parquet' r
        ON c.region_id = r.id
    WHERE ja.activity_code IS NOT NULL AND ja.activity_code!='' AND c.client_type!=5  AND ja.status=1
    GROUP BY ja.activity_code
     
 """
df_client_activity_code_status = con.execute(query).fetchdf()
# Clean enquiry_date
df_client_activity_code_status = df_client_activity_code_status[
    df_client_activity_code_status["enquiry_date"] != "0000-00-00"
]


df_client_activity_code_status["enquiry_date"] = pd.to_datetime(
    df_client_activity_code_status["enquiry_date"],
    errors="coerce"
)

df_client_activity_code_status = df_client_activity_code_status.dropna(
    subset=["enquiry_date"]
)


# Clean enquiry_date
df_job_status = df_client_activity_code_status[
    df_client_activity_code_status["job_date"] != "0000-00-00"
]

df_job_status["job_date"] = pd.to_datetime(
    df_job_status["job_date"],
    errors="coerce"
)

df_job_status = df_job_status.dropna(
    subset=["job_date"]
)

# Total enquiry activity
df_client_activity_code_status = df_client_activity_code_status[
    (df_client_activity_code_status["enquiry_date"] >= pd.to_datetime("2020-01-01"))    
]

total_enquiry_activities = df_client_activity_code_status[
        (df_client_activity_code_status["enquiry_date"] >pd.to_datetime("2020-01-01")) 
    ]["activity_code"].nunique()

# Active-----------------------------------------------------------

enquiry_active_activity = df_client_activity_code_status[
        (df_client_activity_code_status["enquiry_date"] >= ACTIVE_FROM_DATE) &
        (df_client_activity_code_status["enquiry_date"] <= ACTIVE_TO_DATE)
    ]["activity_code"].nunique()   
# InActive-----------------------------------------------------------

enquiry_inactive_activity = df_client_activity_code_status[
        (df_client_activity_code_status["enquiry_date"] >= INACTIVE_FROM_DATE) &
        (df_client_activity_code_status["enquiry_date"] <= INACTIVE_TO_DATE)
    ]["activity_code"].nunique()   
# Lost-----------------------------------------------------------

enquiry_lost_activity = df_client_activity_code_status[
        (df_client_activity_code_status["enquiry_date"] <= LOST_TO_DATE)
    ]["activity_code"].nunique()

#------------------------------------------------------------------------
df_client_activity_code_status = df_client_activity_code_status[
    (df_client_activity_code_status["job_date"] >= pd.to_datetime("2020-01-01"))    
]
total_job_activity = df_client_activity_code_status[
        (df_client_activity_code_status["job_date"] >pd.to_datetime("2020-01-01")) 
    ]["activity_code"].nunique()
# Active-----------------------------------------------------------

job_active_activity = df_client_activity_code_status[
        (df_client_activity_code_status["job_date"] >= ACTIVE_FROM_DATE) &
        (df_client_activity_code_status["job_date"] <= ACTIVE_TO_DATE)
    ]["activity_code"].nunique() 
# InActive-----------------------------------------------------------

job_inactive_activity = df_client_activity_code_status[
        (df_client_activity_code_status["job_date"] >= INACTIVE_FROM_DATE) &
        (df_client_activity_code_status["job_date"] <= INACTIVE_TO_DATE)
    ]["activity_code"].nunique() 
# Lost-----------------------------------------------------------

job_lost_activity = df_client_activity_code_status[
        (df_client_activity_code_status["job_date"] <= LOST_TO_DATE)
    ]["activity_code"].nunique()
#---------------------------------------------------------------------------------------------------
# Clean enquiry_date
df_client_activity_status = df_client_activity_status[
    df_client_activity_status["enquiry_date"] != "0000-00-00"
]


df_client_activity_status["enquiry_date"] = pd.to_datetime(
    df_client_activity_status["enquiry_date"],
    errors="coerce"
)

df_client_activity_status = df_client_activity_status.dropna(
    subset=["enquiry_date"]
)


# Clean enquiry_date
df_job = df_client_activity_status[
    df_client_activity_status["job_date"] != "0000-00-00"
]

df_job["job_date"] = pd.to_datetime(
    df_job["job_date"],
    errors="coerce"
)

df_job = df_job.dropna(
    subset=["job_date"]
)


    # Join
df_merged = pd.merge(
        df_client_activity_status,
        df_debtors_master,
        how="inner",
        on=["debtor_no"]
    )
    
    # Total enquiry countries
total_enquiry_countries = df_client_country_status[
        (df_client_country_status["enquiry_date"] >pd.to_datetime("2020-01-01")) 
    ]["country"].nunique()
    
	#total_enquiry_clients 
df_client_status = df_client_status.loc[df_client_status["enquiry_date"] > pd.to_datetime("2020-01-01")].copy()

df_client_status['debtor_no'] = pd.to_numeric(df_client_status['debtor_no'], errors='coerce')
df_client_status['temp_client_id'] = pd.to_numeric(df_client_status['temp_client_id'], errors='coerce')
df_filtered = df_client_status.loc[df_client_status["enquiry_date"] > pd.to_datetime("2020-01-01")].copy()
unique_debtors = df_filtered.loc[df_filtered['debtor_no'] > 0, 'debtor_no'].nunique()
unique_temps = df_filtered.loc[df_filtered['temp_client_id'] > 0, 'temp_client_id'].nunique()

total_enquiry_clients = int(unique_debtors + unique_temps)

total_black_listed_clients=df_client_status[
        (df_client_status["enquiry_date"] >pd.to_datetime("2020-01-01")) 
        & (df_client_status["client_category"]==6)
    ]["debtor_no"].nunique()
total_closed_clients=df_client_status[
        (df_client_status["enquiry_date"] >pd.to_datetime("2020-01-01")) 
        & (df_client_status["client_category"].isin([2,4,11,12]))
    ]["debtor_no"].nunique()
    # Active
enquiry_active_countries = (
		df_merged
			.groupby("country", as_index=False)["enquiry_date"]
			.max()
	)
enquiry_active_countries = df_client_country_status[
        (df_client_country_status["enquiry_date"] >= ACTIVE_FROM_DATE) &
        (df_client_country_status["enquiry_date"] <= ACTIVE_TO_DATE)
    ]["country"].nunique()
    
	 # Active Enquiry Clients ------------------------------------------

enquiry_active_clients = df_client_status[
        (df_client_status["enquiry_date"] >= ACTIVE_FROM_DATE) &
        (df_client_status["enquiry_date"] <= ACTIVE_TO_DATE)
    ]

unique_debtors = enquiry_active_clients.loc[enquiry_active_clients['debtor_no'] > 0, 'debtor_no'].nunique()
unique_temp = enquiry_active_clients.loc[enquiry_active_clients['temp_client_id'] > 0, 'temp_client_id'].nunique()

enquiry_active_clients = unique_debtors + unique_temp
	 # Active Enquiry Clients -----------End-------------------------------
    # Inactive
enquiry_inactive_countries = (
		df_merged
			.groupby("country", as_index=False)["enquiry_date"]
			.max()
	)
enquiry_inactive_countries = df_client_country_status[
        (df_client_country_status["enquiry_date"] >= INACTIVE_FROM_DATE) &
        (df_client_country_status["enquiry_date"] <= INACTIVE_TO_DATE)
    ]["country"].nunique()
    
	# InActive Enquiry Clients ------------------------------------------

enquiry_inactive_clients = df_client_status[
        (df_client_status["enquiry_date"] >= INACTIVE_FROM_DATE) &
        (df_client_status["enquiry_date"] <= INACTIVE_TO_DATE)
    ]
unique_debtors = enquiry_inactive_clients.loc[enquiry_inactive_clients['debtor_no'] > 0, 'debtor_no'].nunique()
unique_temp = enquiry_inactive_clients.loc[enquiry_inactive_clients['temp_client_id'] > 0, 'temp_client_id'].nunique()

enquiry_inactive_clients = unique_debtors + unique_temp
    
	# InActive Enquiry Clients -----------End-------------------------------
    # Lost

enquiry_lost_countries = df_client_country_status[
        (df_client_country_status["enquiry_date"] <= LOST_TO_DATE)
    ]["country"].nunique()
    
	# Lost Enquiry Clients ------------------------------------------

# Filter the dataframe for the date range first
df_lost_enq = df_client_status[df_client_status["enquiry_date"] <= LOST_TO_DATE]

debtor_count = df_lost_enq.loc[df_lost_enq['debtor_no'] > 0, 'debtor_no'].nunique()
temp_count = df_lost_enq.loc[df_lost_enq['temp_client_id'] > 0, 'temp_client_id'].nunique()
enquiry_lost_clients = debtor_count + temp_count
    
	# Lost Enquiry Clients -----------End-------------------------------
    
    # job 
df_job_merged = pd.merge(
    df_job,
        df_debtors_master,
        how="inner",
        on=["debtor_no"]
)
    
    # Total enquiry countries
total_job_countries = df_client_country_status[
        (df_client_country_status["job_date"] >pd.to_datetime("2020-01-01")) 
    ]["country"].nunique()
    
    # total_job_clients 
df_filtered = df_client_status.loc[df_client_status["job_date"] > pd.to_datetime("2020-01-01")].copy()
df_filtered['debtor_no'] = pd.to_numeric(df_filtered['debtor_no'], errors='coerce')
total_job_clients = df_filtered.loc[df_filtered['debtor_no'] > 0, 'debtor_no'].nunique()
# df_client_status[(df_client_status["job_date"] >pd.to_datetime("2020-01-01")) 
    
total_job_black_listed_clients=df_client_status[
        (df_client_status["job_date"] >pd.to_datetime("2020-01-01")) 
        & (df_client_status["client_category"]==6)
    ]["debtor_no"].nunique()
total_job_closed_clients=df_client_status[
        (df_client_status["job_date"] >pd.to_datetime("2020-01-01")) 
        & (df_client_status["client_category"].isin([2,4,11,12]))
    ]["debtor_no"].nunique()
    # Active

job_active_countries = df_client_country_status[
        (df_client_country_status["job_date"] >= ACTIVE_FROM_DATE) &
        (df_client_country_status["job_date"] <= ACTIVE_TO_DATE)
    ]["country"].nunique()
    
    # ACTIVE JOB CLIENTS
    
    # Active

job_active_clients = df_client_status[
        (df_client_status["job_date"] >= ACTIVE_FROM_DATE) &
        (df_client_status["job_date"] <= ACTIVE_TO_DATE)
    ]["debtor_no"].nunique()
    # INACTIVE JOB CLIENTS
    
    # Inactive

job_inactive_countries = df_client_country_status[
        (df_client_country_status["job_date"] >= INACTIVE_FROM_DATE) &
        (df_client_country_status["job_date"] <= INACTIVE_TO_DATE)
    ]["country"].nunique()
    
    # INACTIVE JOB CLIENTS
    # Inactive

job_inactive_clients = df_client_status[
        (df_client_status["job_date"] >= INACTIVE_FROM_DATE) &
        (df_client_status["job_date"] <= INACTIVE_TO_DATE)
    ]["debtor_no"].nunique()
    # Lost

job_lost_countries = df_client_country_status[
        (df_client_country_status["job_date"] <= LOST_TO_DATE)
    ]["country"].nunique()
    
    # LOST JOB CLIENTS

job_lost_clients = df_client_status[
        df_client_status["job_date"] <= LOST_TO_DATE
    ]["debtor_no"].nunique()

# ---- API Endpoint ----
@router.get("/counties")
def enquiry_country_stats(
):
    return {
        "total_counries":df_client_country_status["country"].nunique(),
        "total_enquiry_countries": total_enquiry_countries,
        "enquiry_active_countries": enquiry_active_countries,
        "enquiry_inactive_countries": enquiry_inactive_countries,
        "enquiry_lost_countries": enquiry_lost_countries,
        'total_job_countries' :total_job_countries,
        "job_active_countries":job_active_countries,
        "job_inactive_countries":job_inactive_countries,
        "job_lost_countries":job_lost_countries,
        "total_enquiry_clients":total_enquiry_clients,
        "enquiry_active_clients":enquiry_active_clients,
        "enquiry_inactive_clients":enquiry_inactive_clients,
        "enquiry_lost_clients" : enquiry_lost_clients,
        "total_job_clients":total_job_clients,
        "job_active_clients":job_active_clients,
        "job_inactive_clients":job_inactive_clients,
        "job_lost_clients":job_lost_clients,
        "total_prev_enquiry_amount":total_prev_enquiry_amount,
        "total_curr_enquiry_amount":total_curr_enquiry_amount,
        "growth_value":growth_value,
        "growth_per":growth_per,
        "PREV_ENQUIRY_FROM_DATE":PREV_ENQUIRY_FROM_DATE,
        "INACTIVE_TO_DATE":INACTIVE_TO_DATE,
        "total_enquiry_activities":total_enquiry_activities,
        "total_prev_invoice_amount":total_prev_invoice_amount,
        "total_curr_invoice_amount":total_curr_invoice_amount,
        "invoice_growth_value":invoice_growth_value,
        "invoice_growth_per":invoice_growth_per,
        "total_prev_gross_invoice_amount":total_prev_gross_invoice_amount,
        "total_curr_gross_invoice_amount":total_curr_gross_invoice_amount,
        "invoice_gross_growth_value":invoice_gross_growth_value,
        "invoice_gross_growth_per":invoice_gross_growth_per,
        "total_one_enquiry":total_one_enquiry,
        "one_enquiry_per":one_enquiry_per,
        "total_IM_enquiry":total_IM_enquiry,
        "IM_enquiry_per":IM_enquiry_per,
        "total_one_invoice_amount":total_one_invoice_amount,
        "one_per":one_per,
        "total_IM_invoice_amount":total_IM_invoice_amount,
        "IM_per":IM_per,
        "total_nonmarine_invoice_amount":total_nonmarine_invoice_amount,
        "total_renewable_enquiry":total_renewable_enquiry,
        "total_oilgas_enquiry":total_oilgas_enquiry,	
        "total_industrial_enquiry":total_industrial_enquiry,
        "total_petrochecmical_enquiry":total_petrochecmical_enquiry,
        "total_offshore_enquiry":total_offshore_enquiry,
        "total_marine_enquiry":total_marine_enquiry,
        "total_renewable_invoice_amount":total_renewable_invoice_amount,
        "total_oilgas_invoice_amount":total_oilgas_invoice_amount,
        "total_industrial_invoice_amount":total_industrial_invoice_amount,
        "total_petrochemical_invoice_amount":total_petrochemical_invoice_amount,
        "total_offshore_invoice_amount":total_offshore_invoice_amount,
        "total_marine_invoice_amount":total_marine_invoice_amount,
        "total_enquiry_activities":total_enquiry_activities,
        "enquiry_active_activity":enquiry_active_activity,
        "enquiry_inactive_activity":enquiry_inactive_activity,
        "enquiry_lost_activity":enquiry_lost_activity,
        "total_job_activity":total_job_activity,
        "job_active_activity":job_active_activity,
        "job_inactive_activity":job_inactive_activity,
        "job_lost_activity":job_lost_activity,
        "total_black_listed_clients":total_black_listed_clients,
        "total_closed_clients":total_closed_clients,
        "total_job_black_listed_clients":total_job_black_listed_clients,
        "total_job_closed_clients":total_job_closed_clients
    }
#TOP 10 Clients on the basis of enquiry amount less than a year
# Sequential merge: enquiry -> debtors_master -> temp_clients
df_top_clients_merged = pd.merge(
    df_client_enquiry,
    df_debtors_master,
    on="debtor_no",
    how="left",
    suffixes=("_ce", "_dm")
).rename(columns={"name": "client_name"})

# Second merge: add temp_clients data
df_top_clients_merged = pd.merge(
    df_top_clients_merged,
    df_temp_clients,
    left_on="enquiry_temp_id",
    right_on="temp_clients_id",
    how="left",
    suffixes=("", "_tc")
)

# Filter by active period (last 365 days)
df_top_clients_filtered = df_top_clients_merged[
    (df_top_clients_merged["enquiry_date"] >= ACTIVE_FROM_DATE) &
    (df_top_clients_merged["enquiry_date"] <= ACTIVE_TO_DATE)
]

# Determine country_id based on debtor_no and enquiry_temp_id
# If debtor_no is 0 and enquiry_temp_id > 0, use temp_client's country; otherwise use debtors_master's country
df_top_clients_filtered["country_id"] = df_top_clients_filtered.apply(
    lambda row: row["country_tc"] if (row["debtor_no"] == 0 and row["enquiry_temp_id"] > 0) else row["country"],
    axis=1
)


# Convert country_id to int64 for proper merging
df_top_clients_filtered["country_id"] = pd.to_numeric(df_top_clients_filtered["country_id"], errors="coerce").fillna(0).astype(int)

# Merge with country table to get country name and region_id
df_top_clients_filtered = pd.merge(
    df_top_clients_filtered,
    df_country[["id", "name", "region_id","colour_code"]],
    left_on="country_id",
    right_on="id",
    how="left",
    suffixes=("", "_country")
).rename(columns={"name": "country_name"})

# Merge with region table to get region name
df_top_clients_filtered = pd.merge(
    df_top_clients_filtered,
    df_region[["id", "name"]],
    left_on="region_id",
    right_on="id",
    how="left",
    suffixes=("", "_region")
).rename(columns={"name": "region_name"})

# Calculate enquiry amount (aprox_amount * rate) per client
df_top_clients_filtered["enquiry_amount"] = (
    df_top_clients_filtered["aprox_amount"] * df_top_clients_filtered["rate"]
)
df_top_clients_filtered["enquiry_amount"] = pd.to_numeric(df_top_clients_filtered["enquiry_amount"], errors="coerce").fillna(0)
df_top_clients_filtered["enquiry_amount"] = round(df_top_clients_filtered["enquiry_amount"]/1000000, 2)
# Determine client identifier and name based on debtor_no and enquiry_temp_id
# If debtor_no is 0 and enquiry_temp_id > 0, use temp client; otherwise use debtor client
df_top_clients_filtered["client_id"] = df_top_clients_filtered.apply(
    lambda row: f"TMP{int(row['enquiry_temp_id'])}" if (row["debtor_no"] == 0 and row["enquiry_temp_id"] > 0) else row["debtor_no"],
    axis=1
)

df_top_clients_filtered["client_name_final"] = df_top_clients_filtered.apply(
    lambda row: row["client_name_tc"] if (row["debtor_no"] == 0 and row["enquiry_temp_id"] > 0) else row["client_name"],
    axis=1
)
df_top_enquiry_clients_filtered_gcc_by_region = df_top_clients_filtered[
    df_top_clients_filtered["country_id"].isin([1,5,16,2,3,4])
]
# Group by client and sum enquiry amounts, keeping other columns
top_10_clients = (
    df_top_clients_filtered
    .groupby(["client_id"], as_index=False)
    .agg({
        "enquiry_amount": "sum",
        "client_name_final": "first",
        "country_name": "first",
        "region_name": "first"
    })
    .sort_values("enquiry_amount", ascending=False)
    .head(10)
)

# Group by client and sum enquiry amounts, keeping other columns
top_10_enquiry_clients_by_region = (
    df_top_clients_filtered
    .groupby(["id_region"], as_index=False)
    .agg({
        "enquiry_amount": "sum",
        "region_name": "first",
        "colour_code": "first",
        
    })
    .sort_values("enquiry_amount", ascending=False)
    .head(10)
)

# Gcc countries status in less than a year
df_top_enquiry_clients_filtered_gcc_by_region = ( 
    df_top_enquiry_clients_filtered_gcc_by_region
    .groupby(["country_id"], as_index=False)    
    .agg({
        "enquiry_amount": "sum",
        "country_name": "first",
        "colour_code": "first"
    })  
    .sort_values("enquiry_amount", ascending=False)
    .head(10)
)

##############################################################################################
#TOP 10 Clients on the basis of invoice amount less than a year
# Sequential merge: invoice -> debtors_master
df_top_job_clients_merged = pd.merge(
    df_debtor_trans,
    df_debtors_master,
    on="debtor_no",
    how="left",
    suffixes=("_dt", "_dm")
).rename(columns={"name": "client_name", "country": "country_dm"})
df_top_job_clients_merged['client_type'] = df_top_job_clients_merged['client_type'].astype(int)
# Filter by active period (last 365 days)
df_top_job_clients_filtered = df_top_job_clients_merged[
    (df_top_job_clients_merged["tran_date"] >= JOB_FROM_DATE) &
    (df_top_job_clients_merged["tran_date"] <= JOB_TO_DATE)&
    (df_top_job_clients_merged["client_type"]!=5)
]

# Merge with country table to get country name and region_id
df_top_job_clients_filtered = pd.merge(
    df_top_job_clients_filtered,
    df_country[["id", "name", "region_id","colour_code"]],
    left_on="country_dm",
    right_on="id",
    how="left",
    suffixes=("", "_country")
).rename(columns={"name": "country_name","id":"id_country"})

# Merge with region table to get region name
df_top_job_clients_filtered = pd.merge(
    df_top_job_clients_filtered,
    df_region[["id", "name"]],
    left_on="region_id",
    right_on="id",
    how="left"
).rename(columns={"name": "region_name"})

# Calculate invoice amount (ov_amount * rate)-total_expense_aed per client

df_top_job_clients_filtered = df_top_job_clients_filtered[df_top_job_clients_filtered["ov_amount"]>0]
df_top_job_clients_filtered["invoice_amount"] = (
    (df_top_job_clients_filtered["ov_amount"] * df_top_job_clients_filtered["rate"])-df_top_job_clients_filtered["total_expense_aed"]
)
df_top_job_clients_filtered["invoice_amount"] = pd.to_numeric(df_top_job_clients_filtered["invoice_amount"], errors="coerce").fillna(0)
top_job_clients = (
    df_top_job_clients_filtered
    .groupby(["debtor_no"], as_index=False)
    .agg({
        "invoice_amount": "sum",
        "client_name": "first",
        "country_name": "first",
        "region_name": "first",
        "total_expense_aed": "sum"
    })
    .sort_values("invoice_amount", ascending=False)
)
#top_job_clients.to_csv("top_job_clients.csv", index=False)
df_top_job_clients_filtered["invoice_amount"] = round(df_top_job_clients_filtered["invoice_amount"]/1000000, 2)
df_top_job_clients_filtered_gcc = df_top_job_clients_filtered[
    df_top_job_clients_filtered["id_country"].isin([1,5,16,2,3,4])   
]

# Group by client and sum enquiry amounts, keeping other columns
top_10_job_clients = (
    df_top_job_clients_filtered
    .groupby(["debtor_no"], as_index=False)
    .agg({
        "invoice_amount": "sum",
        "client_name": "first",
        "country_name": "first",
        "region_name": "first"
    })
    .sort_values("invoice_amount", ascending=False)
    .head(10)
)
# Group by client and sum enquiry amounts, keeping other columns

# Group by client and sum enquiry amounts, keeping other columns
top_10_job_clients_by_region = (
    df_top_job_clients_filtered
    .groupby(["id"], as_index=False)
    .agg({
        "invoice_amount": "sum",
        "region_name": "first",
        "colour_code": "first"
    })
    .sort_values("invoice_amount", ascending=False)
    .head(10)
)
# Gcc countries status in less than a year
df_top_job_clients_filtered_gcc_by_region = (
    df_top_job_clients_filtered_gcc
    .groupby(["id_country"], as_index=False)
    .agg({
        "invoice_amount": "sum",
        "country_name": "first",
        "colour_code": "first"
    })
    .sort_values("invoice_amount", ascending=False)
    .head(10)
)

############################################################################################

####################################################################
# ---- API Endpoint ----
@router.get("/client_lessthanayear")    
def get_top_clients():
    """Returns top 10 clients sorted by enquiry amount (aprox_amount * rate) in last 365 days"""
    return {
        "period": f"{ACTIVE_FROM_DATE} to {ACTIVE_TO_DATE}",
        "top_10_clients_enquiry": top_10_clients.to_dict(orient="records"),
        "top_10_clients_invoice": top_10_job_clients.to_dict(orient="records"),
        "top_10_clients_invoice_by_region": top_10_job_clients_by_region.to_dict(orient="records"),
        "top_10_clients_enquiry_by_region": top_10_enquiry_clients_by_region.to_dict(orient="records"),
        "top_10_gcc_clients_enquiry_by_country": df_top_enquiry_clients_filtered_gcc_by_region.to_dict(orient="records"),
        "top_10_gcc_clients_invoice_by_country": df_top_job_clients_filtered_gcc_by_region.to_dict(orient="records"),
    }