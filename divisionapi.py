from fastapi import APIRouter, Query, params
from typing import Optional
import numpy as np
import pandas as pd
from app.config import DATA_DIR
import math
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from app.constants import (
    ACTIVE_FROM_DATE, ACTIVE_TO_DATE,
    INACTIVE_FROM_DATE, INACTIVE_TO_DATE,
    LOST_TO_DATE,PREV_JOB_TO_DATE,PREV_JOB_FROM_DATE,PREV_ENQUIRY_FROM_DATE,JOB_FROM_DATE,
    JOB_TO_DATE, NON_MARINE_DIVISION
)
import duckdb
import numpy as np

con = duckdb.connect()

router_division = APIRouter(prefix="/division", tags=["Division API"])

def safe_percent(numerator, denominator, precision=2):
    if denominator in (0, None):
        return 0.0
    if numerator in (None,):
        return 0.0

    try:
        value = (numerator / denominator) * 100
        if math.isnan(value) or math.isinf(value):
            return 0.0
        return round(float(value), precision)
    except Exception:
        return 0.0
    
def safe_divide(numerator, denominator):
    if denominator is None:
        return 0
    if isinstance(denominator, (int, float, np.number)):
        if denominator == 0 or np.isnan(denominator):
            return 0
    return numerator / denominator
# ---- Load & normalize data ONCE ----

df_idle_list = df_client_activity_status = pd.read_parquet(
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
# Register pandas dataframe
con.register(
    "df_client_activity_code_status",
    df_client_activity_code_status
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


# ---- API Endpoint ----
@router_division.get("/counties")
def enquiry_country_stats(
    division:  Optional[int] = Query(None),
    country: Optional[int] = Query(None),       # OPTIONAL 
    region: Optional[int] = Query(None),        # OPTIONAL
    subdivision: Optional[int] = Query(None), # OPTIONAL
    sector: Optional[int] = Query(None)      # OPTIONAL
):
    
    conditions = []
    params = []
    if division is not None:
        conditions.append("c.division = ?")
        params.append(division)

    if subdivision is not None:
        conditions.append("c.sub_division = ?")
        params.append(subdivision)

    if country is not None:
        conditions.append("c.country_id = ?")
        params.append(country)

    if region is not None:
        conditions.append("c.region_id = ?")
        params.append(region)
    
    if sector is not None:
        conditions.append("c.client_type = ?")
        params.append(sector)

    
    where_clause =  "AND " + " AND ".join(conditions) if conditions else "  "

    query = f"""
        SELECT
        c.country_id as country,
        c.country_id as country_id,
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
    {where_clause}
    GROUP BY c.country_id, country_name
    """


    
      
   
    df_client_country_status = con.execute(query, params).fetchdf()

    

    
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
            ANY_VALUE(c.temp_client_id) AS temp_client_id,
            ANY_VALUE(c.debtor_no) as reg_debtor_no

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
        {where_clause}
    GROUP BY c.debtor_no,c.temp_client_id"""
    df_client_status = con.execute(query,params).fetchdf()
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
    
  
    
    #if subdivision > 0:
        #df_client_enquiry = df_client_enquiry[df_client_enquiry['subdivision'] == subdivision]

    
    # Join
    df_client_enquiry_merged = pd.merge(
        df_client_enquiry,
        df_debtors_master[["debtor_no","name","client_type","client_status","country"]],
        how="left",
        on=["debtor_no"],
        suffixes=("_ce", "_dm")
    )

    df_client_enquiry_merged = pd.merge(
        df_client_enquiry_merged,
        df_country[["id", "name", "region_id","colour_code"]],
        left_on="country",
        right_on="id",
        how="left",
        suffixes=("", "_country")
    )

    #if country > 0:
       # df_client_enquiry_merged = df_client_enquiry_merged[
          #  df_client_enquiry_merged['country'] == country
        #]
    #if region > 0:
        #df_client_enquiry_merged = df_client_enquiry_merged[
          #  df_client_enquiry_merged['region_id'] == region
        #]
  
    filter_client_enquiry_prev_data = df_client_enquiry_merged[
        (df_client_enquiry_merged['enquiry_date']>=PREV_ENQUIRY_FROM_DATE) &
        (df_client_enquiry_merged['enquiry_date']<INACTIVE_TO_DATE) &
        (df_client_enquiry_merged['enq_status']!=3)
    ]
    
    if division is not None:
        division = int(division)
        filter_client_enquiry_prev_data = filter_client_enquiry_prev_data[
            pd.to_numeric(filter_client_enquiry_prev_data['division'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_client_enquiry_prev_data = filter_client_enquiry_prev_data[
            pd.to_numeric(filter_client_enquiry_prev_data['subdivision'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_client_enquiry_prev_data = filter_client_enquiry_prev_data[
            pd.to_numeric(filter_client_enquiry_prev_data['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_client_enquiry_prev_data = filter_client_enquiry_prev_data[
            pd.to_numeric(filter_client_enquiry_prev_data['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]

    if sector is not None:
        sector = int(sector)
        filter_client_enquiry_prev_data = filter_client_enquiry_prev_data[
            pd.to_numeric(filter_client_enquiry_prev_data['client_type_ce'], errors='coerce').fillna(-1).astype(int) == sector 

        ]
   
    
        
    # Sum of approx_amnt * rate
    total_prev_enquiry_amount = (filter_client_enquiry_prev_data["aprox_amount"] * 
                            filter_client_enquiry_prev_data["rate"]).sum()

    filter_client_enquiry_curr_data = df_client_enquiry_merged[
        (df_client_enquiry_merged['enquiry_date']>ACTIVE_FROM_DATE) &
        (df_client_enquiry_merged['enquiry_date']<ACTIVE_TO_DATE) &
        (df_client_enquiry_merged['enq_status']!=3)
    ]

    if division is not None:
        division = int(division)
        filter_client_enquiry_curr_data = filter_client_enquiry_curr_data[
            pd.to_numeric(filter_client_enquiry_curr_data['division'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_client_enquiry_curr_data = filter_client_enquiry_curr_data[
            pd.to_numeric(filter_client_enquiry_curr_data['subdivision'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_client_enquiry_curr_data = filter_client_enquiry_curr_data[
            pd.to_numeric(filter_client_enquiry_curr_data['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_client_enquiry_curr_data = filter_client_enquiry_curr_data[
            pd.to_numeric(filter_client_enquiry_curr_data['region_id'], errors='coerce').fillna(-1).astype(int) == region 

    ]
    
    if sector is not None:
        sector = int(sector)
        filter_client_enquiry_curr_data = filter_client_enquiry_curr_data[
            pd.to_numeric(filter_client_enquiry_curr_data['client_type_ce'], errors='coerce').fillna(-1).astype(int) == sector 

    ]
    
    # Sum of approx_amnt * rate
    total_curr_enquiry_amount = (filter_client_enquiry_curr_data["aprox_amount"] * 
                            filter_client_enquiry_curr_data["rate"]).sum()
    
    growth_value = total_curr_enquiry_amount-total_prev_enquiry_amount

    growth_per = safe_percent(total_curr_enquiry_amount-total_prev_enquiry_amount, total_prev_enquiry_amount, 1)
    #############################CLIENT ENQUIRY PERCENTAGE###################################


    filter_client_enquiry_one = filter_client_enquiry_curr_data[
        (filter_client_enquiry_curr_data['enquiry_date']>=ACTIVE_FROM_DATE) &
        (filter_client_enquiry_curr_data['enquiry_date']<=ACTIVE_TO_DATE) &
        (filter_client_enquiry_curr_data['client_type_ce']!=5) &
        (filter_client_enquiry_curr_data['division']==3)
    ]
    # Sum of approx_amnt * rate
    total_one_enquiry = (filter_client_enquiry_one["aprox_amount"] * 
                            filter_client_enquiry_one["rate"]).sum()

    one_enquiry_per = safe_percent(total_one_enquiry, total_curr_enquiry_amount, 2)

    #######################################IM DIVISIONENQUIRY ########################
    filter_client_enquiry_IM = filter_client_enquiry_curr_data[
        (filter_client_enquiry_curr_data['enquiry_date']>=ACTIVE_FROM_DATE) &
        (filter_client_enquiry_curr_data['enquiry_date']<=ACTIVE_TO_DATE) &
        (filter_client_enquiry_curr_data['client_type_ce']!=5) &
        (filter_client_enquiry_curr_data['division']==225)
    ]
    # Sum of approx_amnt * rate
    total_IM_enquiry = (filter_client_enquiry_IM["aprox_amount"] * 
                            filter_client_enquiry_IM["rate"]).sum()

    IM_enquiry_per = safe_percent(total_IM_enquiry, total_curr_enquiry_amount,2)
    ################################CLIENT ENQUIRY SECTOR ############################
    filter_client_enquiry_renewable = df_client_enquiry_merged[
        (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
        (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
        (df_client_enquiry_merged['client_type_ce']==12) 
    ]
    # Sum of approx_amnt * rate
    total_renewable_enquiry = (filter_client_enquiry_renewable["aprox_amount"] * 
                            filter_client_enquiry_renewable["rate"]).sum()

    renewable_enquiry_per = safe_percent(total_renewable_enquiry, total_curr_enquiry_amount,2)
    #--------------------------------OIL-------------------------------------
    
    filter_client_enquiry_oilgas = df_client_enquiry_merged[
        (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
        (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
        (df_client_enquiry_merged['client_type_ce']==3) 
    ]
    if division is not None:
        division = int(division)
        filter_client_enquiry_oilgas = filter_client_enquiry_oilgas[
            pd.to_numeric(filter_client_enquiry_oilgas['division'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_client_enquiry_oilgas = filter_client_enquiry_oilgas[
            pd.to_numeric(filter_client_enquiry_oilgas['subdivision'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_client_enquiry_oilgas = filter_client_enquiry_oilgas[
            pd.to_numeric(filter_client_enquiry_oilgas['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_client_enquiry_oilgas = filter_client_enquiry_oilgas[
            pd.to_numeric(filter_client_enquiry_oilgas['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
    if sector is not None:
        sector = int(sector)
        filter_client_enquiry_oilgas = filter_client_enquiry_oilgas[
            pd.to_numeric(filter_client_enquiry_oilgas['client_type_ce'], errors='coerce').fillna(-1).astype(int) == sector 

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
    if division is not None:
        division = int(division)
        filter_client_enquiry_industrial = filter_client_enquiry_industrial[
            pd.to_numeric(filter_client_enquiry_industrial['division'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_client_enquiry_industrial = filter_client_enquiry_industrial[
            pd.to_numeric(filter_client_enquiry_industrial['subdivision'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_client_enquiry_industrial = filter_client_enquiry_industrial[
            pd.to_numeric(filter_client_enquiry_industrial['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_client_enquiry_industrial = filter_client_enquiry_industrial[
            pd.to_numeric(filter_client_enquiry_industrial['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
    if sector is not None:
        sector = int(sector)
        filter_client_enquiry_industrial = filter_client_enquiry_industrial[
            pd.to_numeric(filter_client_enquiry_industrial['client_type_ce'], errors='coerce').fillna(-1).astype(int) == sector 

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
    if division is not None:
        division = int(division)
        filter_client_enquiry_petrochemical = filter_client_enquiry_petrochemical[
            pd.to_numeric(filter_client_enquiry_petrochemical['division'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_client_enquiry_petrochemical = filter_client_enquiry_petrochemical[
            pd.to_numeric(filter_client_enquiry_petrochemical['subdivision'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_client_enquiry_petrochemical = filter_client_enquiry_petrochemical[
            pd.to_numeric(filter_client_enquiry_petrochemical['country'], errors='coerce').fillna(-1).astype(int) == country 
        ]
    if region is not None:
        region = int(region)
        filter_client_enquiry_petrochemical = filter_client_enquiry_petrochemical[
            pd.to_numeric(filter_client_enquiry_petrochemical['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
    if sector is not None:
        sector = int(sector)
        filter_client_enquiry_petrochemical = filter_client_enquiry_petrochemical[
            pd.to_numeric(filter_client_enquiry_petrochemical['client_type_ce'], errors='coerce').fillna(-1).astype(int) == sector 

        ]
    
    # Sum of approx_amnt * rate
    total_petrochecmical_enquiry = (filter_client_enquiry_petrochemical["aprox_amount"] * 
                            filter_client_enquiry_petrochemical["rate"]).sum()
    #--------------------------------OFFSHORE-------------------------------------
    filter_client_enquiry_offshore = df_client_enquiry_merged[
        (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
        (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
        (df_client_enquiry_merged['client_type_ce'].astype(int)==6) 
    ]
    if division is not None:
        division = int(division)
        filter_client_enquiry_offshore = filter_client_enquiry_offshore[
            pd.to_numeric(filter_client_enquiry_offshore['division'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_client_enquiry_offshore = filter_client_enquiry_offshore[
            pd.to_numeric(filter_client_enquiry_offshore['subdivision'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_client_enquiry_offshore = filter_client_enquiry_offshore[
            pd.to_numeric(filter_client_enquiry_offshore['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_client_enquiry_offshore = filter_client_enquiry_offshore[
            pd.to_numeric(filter_client_enquiry_offshore['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
    if sector is not None:
        sector = int(sector)
        filter_client_enquiry_offshore = filter_client_enquiry_offshore[
            pd.to_numeric(filter_client_enquiry_offshore['client_type_ce'], errors='coerce').fillna(-1).astype(int) == sector 

        ]
   
     
    # Sum of approx_amnt * rate
    total_offshore_enquiry = (filter_client_enquiry_offshore["aprox_amount"] * 
                            filter_client_enquiry_offshore["rate"]).sum()
    #--------------------------------MARINE-------------------------------------
    filter_client_enquiry_marine = df_client_enquiry_merged[
        (df_client_enquiry_merged['enquiry_date']>=ACTIVE_FROM_DATE) &
        (df_client_enquiry_merged['enquiry_date']<=ACTIVE_TO_DATE) &
        (df_client_enquiry_merged['client_type_ce'].astype(int)==2) 
    ]

    if division is not None:
        division = int(division)
        filter_client_enquiry_marine = filter_client_enquiry_marine[
            pd.to_numeric(filter_client_enquiry_marine['division'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_client_enquiry_marine = filter_client_enquiry_marine[
            pd.to_numeric(filter_client_enquiry_marine['subdivision'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_client_enquiry_marine = filter_client_enquiry_marine[
            pd.to_numeric(filter_client_enquiry_marine  ['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_client_enquiry_oilgas = filter_client_enquiry_oilgas[
            pd.to_numeric(filter_client_enquiry_oilgas['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
    if sector is not None:
        sector = int(sector)
        filter_client_enquiry_oilgas = filter_client_enquiry_oilgas[
            pd.to_numeric(filter_client_enquiry_oilgas['client_type_ce'], errors='coerce').fillna(-1).astype(int) == sector 

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

    df_invoice_merged = pd.merge(
        df_invoice_merged,
        df_country[["id", "name", "region_id","colour_code"]],
        left_on="country",
        right_on="id",
        how="left",
        suffixes=("", "_country")
    )
    
    filter_invoice_prev_data = df_invoice_merged[
        (df_invoice_merged['tran_date']>=PREV_JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=PREV_JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)!=5)
    ]
    if division is not None:
        division = int(division)
        filter_invoice_prev_data = filter_invoice_prev_data[
            pd.to_numeric(filter_invoice_prev_data['dimension2_id'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_invoice_prev_data = filter_invoice_prev_data[
            pd.to_numeric(filter_invoice_prev_data['dimension3_id'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_invoice_prev_data = filter_invoice_prev_data[
            pd.to_numeric(filter_invoice_prev_data['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_invoice_prev_data = filter_invoice_prev_data[
            pd.to_numeric(filter_invoice_prev_data['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
   
        
    
   
    # Sum of approx_amnt * rate
    total_prev_invoice_amount = ((filter_invoice_prev_data["ov_amount"] * 
                            filter_invoice_prev_data["rate"])-filter_invoice_prev_data['total_expense_aed']).sum()

    # Sum of ov_amount * rate
    total_prev_gross_invoice_amount = ((filter_invoice_prev_data["ov_amount"]*filter_invoice_prev_data["rate"])).sum()

    if division is not None:
        division = int(division)
        df_invoice_merged = df_invoice_merged[
            pd.to_numeric(df_invoice_merged['dimension2_id'], errors='coerce').fillna(-1).astype(int) == division 
        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        df_invoice_merged = df_invoice_merged[
            pd.to_numeric(df_invoice_merged['dimension3_id'], errors='coerce').fillna(-1).astype(int) == subdivision 
        ]
    if country is not None:
        country = int(country)
        df_invoice_merged = df_invoice_merged[
            pd.to_numeric(df_invoice_merged['country'], errors='coerce').fillna(-1).astype(int) == country 
        ]
    if country is not None:
        country = int(country)
        df_invoice_merged = df_invoice_merged[
            pd.to_numeric(df_invoice_merged['country'], errors='coerce').fillna(-1).astype(int) == country 
        ]
    if region is not None:
        region = int(region)
        df_invoice_merged = df_invoice_merged[
            pd.to_numeric(df_invoice_merged['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
    if sector is not None:
        sector = int(sector)
        df_invoice_merged = df_invoice_merged[
            pd.to_numeric(df_invoice_merged['client_type'], errors='coerce').fillna(-1).astype(int) == sector 

        ]

       
    

    filter_invoice_curr_data = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)!=5)
    ]
       
  

 
    # Sum of approx_amnt * rate
    total_curr_invoice_amount = ((filter_invoice_curr_data["ov_amount"] * 
                            filter_invoice_curr_data["rate"])-filter_invoice_curr_data['total_expense_aed']).sum()

    total_curr_gross_invoice_amount = ((filter_invoice_curr_data["ov_amount"]*filter_invoice_curr_data["rate"])).sum()

    invoice_growth_value = total_curr_invoice_amount-total_prev_invoice_amount
    invoice_gross_growth_value = total_curr_gross_invoice_amount-total_prev_gross_invoice_amount
    if total_prev_gross_invoice_amount>0 :
        invoice_gross_growth_per=safe_percent(safe_divide(invoice_gross_growth_value,total_prev_gross_invoice_amount),2)
    else :
        invoice_gross_growth_per = 0
    if total_prev_invoice_amount >0 :
        invoice_growth_per = safe_percent(safe_divide(invoice_growth_value,total_prev_invoice_amount),2)
    else:
         invoice_growth_per =0
    
    #---------------------------------------------RENEWABLE ENERGY__________________
    df_invoice_merged['tran_date'] = pd.to_datetime(
    df_invoice_merged['tran_date'],
    errors='coerce'
)
    
    filter_invoice_renewable = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)==12)
    ] 
    
    if division is not None:
        division = int(division)
        filter_invoice_renewable = filter_invoice_renewable[
            pd.to_numeric(filter_invoice_renewable['dimension2_id'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_invoice_renewable = filter_invoice_renewable[
            pd.to_numeric(filter_invoice_renewable['dimension3_id'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_invoice_renewable = filter_invoice_renewable[
            pd.to_numeric(filter_invoice_renewable['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_invoice_renewable = filter_invoice_renewable[
            pd.to_numeric(filter_invoice_renewable['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
    
    
    # Sum of approx_amnt * rate
    total_renewable_invoice_amount = ((filter_invoice_renewable["ov_amount"] * 
                            filter_invoice_renewable["rate"])-filter_invoice_renewable['total_expense_aed']).sum()
    #---------------------------------------------OILGAS__________________
    filter_invoice_oilgas = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)==3)
    ]
    if division is not None:
        division = int(division)
        filter_invoice_oilgas = filter_invoice_oilgas[
            pd.to_numeric(filter_invoice_oilgas['dimension2_id'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_invoice_oilgas = filter_invoice_oilgas[
            pd.to_numeric(filter_invoice_oilgas['dimension3_id'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_invoice_oilgas = filter_invoice_oilgas[
            pd.to_numeric(filter_invoice_oilgas['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_invoice_oilgas = filter_invoice_oilgas[
            pd.to_numeric(filter_invoice_oilgas['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
   

    # Sum of approx_amnt * rate
    total_oilgas_invoice_amount = ((filter_invoice_oilgas["ov_amount"] * 
                            filter_invoice_oilgas["rate"])-filter_invoice_oilgas['total_expense_aed']).sum()
    #---------------------------------------------INDUSTRIAL__________________
    filter_invoice_industrial = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)==1)
    ]
    if division is not None:
        division = int(division)
        filter_invoice_industrial = filter_invoice_industrial[
            pd.to_numeric(filter_invoice_industrial['dimension2_id'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_invoice_industrial = filter_invoice_industrial[
            pd.to_numeric(filter_invoice_industrial['dimension3_id'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_invoice_industrial = filter_invoice_industrial[
            pd.to_numeric(filter_invoice_industrial['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_invoice_industrial = filter_invoice_industrial[
            pd.to_numeric(filter_invoice_industrial['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
   
    # Sum of approx_amnt * rate
    total_industrial_invoice_amount = ((filter_invoice_industrial["ov_amount"] * 
                            filter_invoice_industrial["rate"])-filter_invoice_industrial['total_expense_aed']).sum()
    #---------------------------------------------PETROCHECMICAL__________________
    filter_invoice_petrochemical = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)==10)
    ]
    if division is not None:
        division = int(division)
        filter_invoice_petrochemical = filter_invoice_petrochemical[
            pd.to_numeric(filter_invoice_petrochemical['dimension2_id'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_invoice_petrochemical = filter_invoice_petrochemical[
            pd.to_numeric(filter_invoice_petrochemical['dimension3_id'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_invoice_petrochemical = filter_invoice_petrochemical[
            pd.to_numeric(filter_invoice_petrochemical['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_invoice_petrochemical = filter_invoice_petrochemical[
            pd.to_numeric(filter_invoice_petrochemical['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
   
    # Sum of approx_amnt * rate
    total_petrochemical_invoice_amount = ((filter_invoice_petrochemical["ov_amount"] * 
                            filter_invoice_petrochemical["rate"])-filter_invoice_petrochemical['total_expense_aed']).sum()
    #---------------------------------------------OFFSHORE__________________
    filter_invoice_offshore = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)==6)
    ]
    if division is not None:
        division = int(division)
        filter_invoice_offshore = filter_invoice_offshore[
            pd.to_numeric(filter_invoice_offshore['dimension2_id'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_invoice_offshore = filter_invoice_offshore[
            pd.to_numeric(filter_invoice_offshore['dimension3_id'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_invoice_offshore = filter_invoice_offshore[
            pd.to_numeric(filter_invoice_offshore['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_invoice_offshore = filter_invoice_offshore[
            pd.to_numeric(filter_invoice_offshore['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
   
    # Sum of approx_amnt * rate
    total_offshore_invoice_amount = ((filter_invoice_offshore["ov_amount"] * 
                            filter_invoice_offshore["rate"])-filter_invoice_offshore['total_expense_aed']).sum()
    #---------------------------------------------MARINE__________________
    filter_invoice_marine = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)==2)
    ]
    if division is not None:
        division = int(division)
        filter_invoice_marine = filter_invoice_marine[
            pd.to_numeric(filter_invoice_marine['dimension2_id'], errors='coerce').fillna(-1).astype(int) == division 

        ]
    if subdivision is not None:
        subdivision = int(subdivision)
        filter_invoice_marine = filter_invoice_marine[
            pd.to_numeric(filter_invoice_marine['dimension3_id'], errors='coerce').fillna(-1).astype(int) == subdivision 

        ]
    if country is not None:
        country = int(country)
        filter_invoice_marine = filter_invoice_marine[
            pd.to_numeric(filter_invoice_marine['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_invoice_marine = filter_invoice_marine[
            pd.to_numeric(filter_invoice_marine['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
   
   
    # Sum of approx_amnt * rate
    total_marine_invoice_amount = ((filter_invoice_marine["ov_amount"] * 
                            filter_invoice_marine["rate"])-filter_invoice_marine['total_expense_aed']).sum()
    ###########################################ONE DIVISIOn ###############################################
    filter_invoice_one_data = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type']!=5) &
        (df_invoice_merged['dimension2_id'].astype(int)==3)
        ]
    
   
    
    if country is not None:
        country = int(country)
        filter_invoice_one_data = filter_invoice_one_data[
            pd.to_numeric(filter_invoice_one_data['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        filter_invoice_renewable = filter_invoice_one_data[
            pd.to_numeric(filter_invoice_one_data['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
    if sector is not None:
        sector = int(sector)
        filter_invoice_renewable = filter_invoice_one_data[
            pd.to_numeric(filter_invoice_one_data['client_type'], errors='coerce').fillna(-1).astype(int) == sector 

        ]
    total_one_invoice_amount = ((filter_invoice_one_data["ov_amount"] * 
                            filter_invoice_one_data["rate"])-filter_invoice_one_data['total_expense_aed']).sum()
    if total_curr_invoice_amount>0:
         one_per = safe_percent(safe_divide(total_one_invoice_amount,total_curr_invoice_amount),2)
    else :
        total_curr_invoice_amount=0
        one_per =0

   

    ########################################I&M DIVISION ######################################
   
    if country is not None:
        country = int(country)
        df_invoice_merged = df_invoice_merged[
            pd.to_numeric(df_invoice_merged['country'], errors='coerce').fillna(-1).astype(int) == country 

        ]
    if region is not None:
        region = int(region)
        df_invoice_merged = df_invoice_merged[
            pd.to_numeric(df_invoice_merged['region_id'], errors='coerce').fillna(-1).astype(int) == region 

        ]
    if sector is not None:
        sector = int(sector)
        df_invoice_merged = df_invoice_merged[
            pd.to_numeric(df_invoice_merged['client_type'], errors='coerce').fillna(-1).astype(int) == sector 

        ]

    filter_invoice_IM_data = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)!=5) &
        (df_invoice_merged['dimension2_id'].astype(int)==225)
        ]
    
    total_IM_invoice_amount = ((filter_invoice_IM_data["ov_amount"] * 
                            filter_invoice_IM_data["rate"])-filter_invoice_IM_data['total_expense_aed']).sum()
    if total_curr_invoice_amount>0:
         IM_per = safe_percent(safe_divide(total_IM_invoice_amount,total_curr_invoice_amount),2)
    else :
        IM_per =0
    ########################################NON MARINE DIVISION ######################################
    filter_invoice_non_marine_data = df_invoice_merged[
        (df_invoice_merged['tran_date']>=JOB_FROM_DATE) &
        (df_invoice_merged['tran_date']<=JOB_TO_DATE) &
        (df_invoice_merged['client_type'].astype(int)!=5) &
        (df_invoice_merged['dimension2_id'].astype(int).isin(NON_MARINE_DIVISION))
        ]
   
    total_nonmarine_invoice_amount = ((filter_invoice_non_marine_data["ov_amount"] * 
                            filter_invoice_non_marine_data["rate"])-filter_invoice_non_marine_data['total_expense_aed']).sum()
    nonmarine_per = safe_percent(safe_divide(total_nonmarine_invoice_amount,total_curr_invoice_amount)*100,2)
    #################################################################################################
    # Clean enquiry_date
   

    conditions = []
    params = []
    if division is not None:
        conditions.append("ja.division_id = ?")
        params.append(division)

    if subdivision is not None:
        conditions.append("ja.sub_division_id = ?")
        params.append(subdivision)

    if country is not None:
        conditions.append("c.country_id = ?")
        params.append(country)

    if region is not None:
        conditions.append("d.region_id = ?")
        params.append(region)
    
    if sector is not None:
        conditions.append("c.client_type = ?")
        params.append(sector)

    where_clause = " AND " + " AND ".join(conditions) if conditions else "  "

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
    WHERE ja.activity_code IS NOT NULL AND ja.activity_code!='' AND c.client_type!=5 AND ja.status=1
     {where_clause}
    GROUP BY ja.activity_code 
 """



    
    
   
    df_client_activity_code_status = con.execute(query, params).fetchdf()
  
    
    
   
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
    (df_client_activity_code_status["enquiry_date"] >= pd.to_datetime("2020-01-01"))  &
    (df_client_activity_code_status["status"]==1 )  
]

    total_enquiry_activities = df_client_activity_code_status[
        (df_client_activity_code_status["enquiry_date"] >pd.to_datetime("2020-01-01")) 
    ]["activity_code"].nunique()
    # Active-----------------------------------------------------------
    enquiry_active_activities = (
            df_client_activity_code_status
                .groupby("activity_code", as_index=False)["enquiry_date"]
                .max()
        )
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
    
    conditions = []
    params = []
    if division is not None:
        conditions.append("division = ?")
        params.append(division)

    if subdivision is not None:
        conditions.append("sub_division = ?")
        params.append(subdivision)

    if country is not None:
        conditions.append("country_id = ?")
        params.append(country)

    if region is not None:
        conditions.append("region_id = ?")
        params.append(region)
    
    if sector is not None:
        conditions.append("client_type = ?")
        params.append(sector)

    where_clause = " WHERE  AND " + " AND ".join(conditions) if conditions else " WHERE 1 "

    query = f"""
            SELECT
            c.sub_division AS sub_division,
            c.division,
            c.country_id,
            c.enquiry_date,
            c.job_date,
            c.region_id,
            c.debtor_no,
            c.client_type
        FROM '{DATA_DIR}/client_activity_status.parquet' c  """

    
   
   
    df_client_activity_status = con.execute(query).fetchdf()
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
    
    #idle_countries = df_merged[df_merged['client_category']==6]['country_id'].nunique() 
    # 
    idle_enquiry_countries = df_idle_list[
        (df_idle_list['enquiry_date']>= pd.to_datetime("2020-01-01")) &
        (df_idle_list['country_id']>0) & (df_idle_list['client_type']!=5)
    ]
    if country is not None:
           idle_enquiry_countries = idle_enquiry_countries [
                idle_enquiry_countries['country_id']== country
        ]
    if region is not None:
            idle_enquiry_countries =idle_enquiry_countries [
                idle_enquiry_countries['region_id']== region
        ]
    if sector is not None:
            idle_enquiry_countries = idle_enquiry_countries [
                idle_enquiry_countries['client_type']== sector
        ]
    #idle_enquiry_countries.to_csv("idle_enquiry_countries.csv",index=False)   
    exclude_enquiry_country = df_client_country_status.loc[
        df_client_country_status['enquiry_date']> pd.to_datetime("2020-01-01"), 'country_id'
    ]
    exclude_enquiry_clients = df_client_status.loc[
        df_client_status['enquiry_date']> pd.to_datetime("2020-01-01"), 'debtor_no'
    ]
    exclude_job_clients = df_client_status.loc[
        df_client_status['job_date']> pd.to_datetime("2020-01-01"), 'debtor_no'
    ]
  

    idle_enquiry_clients =  idle_job_clients = idle_enquiry_countries
    if exclude_enquiry_country is not None:
        idle_enquiry_countries = idle_enquiry_countries[
            (~idle_enquiry_countries["country_id"].isin(exclude_enquiry_country.drop_duplicates().tolist())) &
            (idle_enquiry_countries["enquiry_date"] > pd.to_datetime("2020-01-01"))
        ]
    
    total_idle_enquiry_countries = idle_enquiry_countries['country_id'].nunique()
    idle_job_countries = df_idle_list[
        (df_idle_list['job_date']> pd.to_datetime("2020-01-01")) &
         (df_idle_list['country_id'].astype(int)>0)
    ]

    if country is not None:
           idle_job_countries = idle_job_countries [
                idle_job_countries['country_id']== country
        ]
    if region is not None:
            idle_job_countries =idle_job_countries [
                idle_job_countries['region_id']== region
        ]
    if sector is not None:
            idle_job_countries = idle_job_countries [
                idle_job_countries['client_type']== sector
        ]
   
    
    exclude_job_countries = df_client_country_status.loc[
        df_client_country_status['job_date']> pd.to_datetime("2020-01-01"), 'country_id'
    ]
    if exclude_job_countries is not None:
        idle_job_countries = idle_job_countries[
            (~idle_job_countries["country_id"].isin(exclude_job_countries.drop_duplicates().tolist())) &
            (idle_job_countries["job_date"] > pd.to_datetime("2020-01-01"))
        ]
    total_idle_job_countries = idle_job_countries['country_id'].nunique()
        # Total enquiry countries
    total_enquiry_countries = df_client_country_status[
        (df_client_country_status["enquiry_date"] >pd.to_datetime("2020-01-01")) &
        (df_client_country_status["country_id"]>0)
    ]["country_id"].nunique()

    
    
        #total_enquiry_clients
    df_client_status = df_client_status.loc[df_client_status["enquiry_date"] > pd.to_datetime("2020-01-01")].copy()

    df_client_status['debtor_no'] = pd.to_numeric(df_client_status['debtor_no'], errors='coerce')
    df_client_status['temp_client_id'] = pd.to_numeric(df_client_status['temp_client_id'], errors='coerce')
    unique_debtors = df_client_status.loc[df_client_status['debtor_no'] > 0, 'debtor_no'].nunique()
    unique_temps = df_client_status.loc[df_client_status['temp_client_id'] > 0, 'temp_client_id'].nunique()

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
   
    enquiry_active_countries = df_client_country_status[
            (df_client_country_status["enquiry_date"] >= ACTIVE_FROM_DATE) &
            (df_client_country_status["enquiry_date"] <= ACTIVE_TO_DATE)
        ]["country_id"].nunique()
        
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
    
    enquiry_inactive_countries = df_client_country_status[
            (df_client_country_status["enquiry_date"] >= INACTIVE_FROM_DATE) &
            (df_client_country_status["enquiry_date"] <= INACTIVE_TO_DATE)& 
            (df_client_country_status["country_id"]>0)
        ]["country_id"].nunique()
        
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
        ]["country_id"].nunique()
        
        # Lost Enquiry Clients ------------------------------------------
   
    # Filter the dataframe for the date range first
    df_lost_enq = df_client_status[df_client_status["enquiry_date"] <= LOST_TO_DATE]

    debtor_count = df_lost_enq.loc[df_lost_enq['debtor_no'] > 0, 'debtor_no'].nunique()
    temp_count = df_lost_enq.loc[df_lost_enq['temp_client_id'] > 0, 'temp_client_id'].nunique()
    enquiry_lost_clients = debtor_count + temp_count

    if exclude_enquiry_clients is not None:   
        idle_enquiry_clients = idle_enquiry_clients[
            (~idle_enquiry_clients["debtor_no"].isin(exclude_enquiry_clients)) &
            (idle_enquiry_clients["enquiry_date"] > pd.to_datetime("2020-01-01"))
        ]

    total_idle_enquiry_clients = idle_enquiry_clients["debtor_no"].nunique()
    if exclude_job_clients is not None:   
        idle_job_clients = idle_job_clients[
            (~idle_job_clients["debtor_no"].isin(exclude_job_clients.drop_duplicates().tolist())) &
            (idle_job_clients["job_date"] > pd.to_datetime("2020-01-01"))
        ]
    
    
    total_idle_job_clients = idle_job_clients["debtor_no"].nunique()
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
    ]["country_id"].nunique()
        
        # total_job_clients 
    df_filtered = df_client_status.loc[df_client_status["job_date"] > pd.to_datetime("2020-01-01")].copy()
    df_filtered['debtor_no'] = pd.to_numeric(df_filtered['debtor_no'], errors='coerce')
    total_job_clients = df_filtered.loc[df_filtered['debtor_no'] > 0, 'debtor_no'].nunique()
        
        
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
        ]["country_id"].nunique()
        
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
        ]["country_id"].nunique()
        
        # INACTIVE JOB CLIENTS
        # Inactive
   
    job_inactive_clients = df_client_status[
            (df_client_status["job_date"] >= INACTIVE_FROM_DATE) &
            (df_client_status["job_date"] <= INACTIVE_TO_DATE)
        ]["debtor_no"].nunique()
        # Lost
    
    job_lost_countries = df_client_country_status[
            (df_client_country_status["job_date"] <= LOST_TO_DATE)
        ]["country_id"].nunique()
        
        # LOST JOB CLIENTS
   
    job_lost_clients = df_client_status[
            (df_client_status["job_date"] <= LOST_TO_DATE)
        ]["debtor_no"].nunique()
    

    return {
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
        "total_job_closed_clients":total_job_closed_clients,
        "total_idle_enquiry_countries":total_idle_enquiry_countries,
        "total_idle_job_countries":total_idle_job_countries,
        "total_idle_enquiry_clients":total_idle_enquiry_clients,
        "total_idle_job_clients":total_idle_job_clients
    }
#
@router_division.get("/client_lessthanayear")    
def enquiry_country_stats(
    division:  Optional[int] = Query(None),
    country: Optional[int] = Query(None),       # OPTIONAL 
    region: Optional[int] = Query(None),        # OPTIONAL
    subdivision: Optional[int] = Query(None), # OPTIONAL
    sector: Optional[int] = Query(None)      # OPTIONAL
):
    
    conditions = []
    params = []

    if division is not None:
        conditions.append("c.division = ?")
        params.append(division)

    if subdivision is not None:
        conditions.append("c.subdivision = ?")
        params.append(subdivision)

    if country is not None:
        conditions.append("""
        COALESCE(
            TRY_CAST(NULLIF(CAST(d.country AS VARCHAR), '') AS BIGINT),
            TRY_CAST(NULLIF(CAST(t.country AS VARCHAR), '') AS BIGINT)
        ) = ?
    """)
        params.append(country)

    if region is not None:
        conditions.append("COALESCE(CAST(c1.region_id AS BIGINT), CAST(c2.region_id AS BIGINT)) = ?")
        params.append(region)

    if sector is not None:
        conditions.append("""
        COALESCE(
            TRY_CAST(NULLIF(CAST(d.client_type AS VARCHAR), '') AS BIGINT),
            TRY_CAST(NULLIF(CAST(t.temp_client_type AS VARCHAR), '') AS BIGINT)
        ) = ?
    """)
        params.append(sector)

    where_clause = (
        " WHERE " + " AND ".join(conditions)
        if conditions
        else " WHERE 1=1 "
    )

    query = f"""
        SELECT
        COALESCE(
            CAST(c.debtor_no AS VARCHAR),
            'TEMP' || CAST(c.enquiry_temp_id AS VARCHAR)
        ) AS client_id,

        CAST(c.subdivision AS VARCHAR) AS subdivision,
        CAST(c.division AS VARCHAR) AS division,

        c.enquiry_date,

        COALESCE(
            CAST(d.name AS VARCHAR),
            CAST(t.client_name AS VARCHAR)
        ) AS client_name_final,

        COALESCE(
            CAST(d.country AS BIGINT),
            CAST(NULLIF(t.country, '') AS BIGINT)
        ) AS country_id,
        COALESCE(
            CAST(c1.region_id AS INT),
            CAST(c2.region_id AS INT)
        ) AS region_id
        ,c.aprox_amount,
        c.rate,
        c.enquiry_temp_id AS temp_client_id,
        COALESCE(
            CAST(d.client_type AS BIGINT),
            CAST(NULLIF(t.temp_client_type, '') AS BIGINT)
        ) AS client_type
            FROM read_parquet('{DATA_DIR}/client_enquiry.parquet') c
            LEFT JOIN read_parquet('{DATA_DIR}/debtors_master.parquet') d
                ON c.debtor_no = d.debtor_no
            LEFT JOIN '{DATA_DIR}/country.parquet' c1
                ON c1.id = d.country
            LEFT JOIN read_parquet('{DATA_DIR}/temp_clients.parquet') t
                ON c.enquiry_temp_id = t.temp_clients_id
            LEFT JOIN '{DATA_DIR}/country.parquet' c2
                ON c2.id = TRY_CAST(NULLIF(t.country, '') AS BIGINT)
            {where_clause}
        """
    
    df_top_clients_merged = con.execute(query, params).fetchdf()
    
   


    # Filter by active period (last 365 days)
    df_top_clients_filtered = df_top_clients_merged[
        (df_top_clients_merged["enquiry_date"] >= ACTIVE_FROM_DATE) &
        (df_top_clients_merged["enquiry_date"] <= ACTIVE_TO_DATE)
    ]

    

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
    

   
    df_top_enquiry_clients_filtered_gcc_by_region = df_top_clients_filtered[
        df_top_clients_filtered["country_id"].isin([1,5,16,2,3,4])
    ]
    df_gcc_countries = df_country[
        df_country['id'].isin([1,5,16,2,3,4])
    ]
    # Group by client and sum enquiry amounts, keeping other columns
    top_10_clients = (
        df_top_clients_filtered
        .groupby(["client_id"], as_index=False)
        .agg({
            "enquiry_amount": "sum",
            "client_name_final": "first",
            "country_name": "first",
            "region_name": "first",
            "temp_client_id":"first"
        })
        .sort_values("enquiry_amount", ascending=False)
        .head(10)
    )

    df_region1 = df_country.merge(
        df_region,
        how="left",
        left_on="region_id",
        right_on="id"
    ).rename(columns={'name_y':'region_name',"id_y":"id","id_x":"countryid"})
    
    df_region1 = (
        df_region1
        .groupby(["id"], as_index=False)
        .agg({
            "countryid": "sum",
            "region_name": "first",
            "colour_code": "first"
        })
    )
  
   
    top_10_enquiry_clients_by_region = df_region1.merge(
        df_top_clients_filtered,
        how="left",
        left_on="id",
        right_on="region_id"
    )
    
    #.rename(columns={"colour_code_x":"colour_code","region_name_x":"region_name"})

    # Group by client and sum enquiry amounts, keeping other columns
    top_10_enquiry_clients_by_region = (
        top_10_enquiry_clients_by_region
        .groupby(["id_x"], as_index=False)
        .agg({
            "enquiry_amount": "sum",
            "region_name_x": "first",
            "colour_code_x": "first"
        })
        .sort_values("enquiry_amount", ascending=False)
        .head(10)
    ).rename(columns={"region_name_x":"region_name","colour_code_x":"colour_code"})
   
   
    #return{"hi":"hello"}

    # Gcc countries status in less than a year
    df_top_enquiry_clients_filtered_gcc_by_region = df_gcc_countries.merge(
        df_top_enquiry_clients_filtered_gcc_by_region,
        how="left",
        left_on="id",
        right_on="country_id"
    ).rename(columns={"id_x":"id","colour_code_x":"colour_code","name":"country_name","country_name":"country_name_x"})
    df_top_enquiry_clients_filtered_gcc_by_region = ( 
        df_top_enquiry_clients_filtered_gcc_by_region
        .groupby(["id"], as_index=False)    
        .agg({
            "enquiry_amount": "sum",
            "country_name": "first",
            "colour_code": "first"
        })  
        .sort_values("enquiry_amount", ascending=False)
    )

    ##############################################################################################
    #TOP 10 Clients on the basis of invoice amount less than a year
    # Sequential merge: invoice -> debtors_master
    conditions = []
    params = []

    if division is not None:
        conditions.append("c.dimension2_id = ?")
        params.append(division)

    if subdivision is not None:
        conditions.append("c.dimension3_id = ?")
        params.append(subdivision)

    if country is not None:
        conditions.append("d.country = ?")
        params.append(country)

    if region is not None:
        conditions.append("c2.region_id = ?")
        params.append(region)

    if sector is not None:
        conditions.append("d.client_type = ?")
        params.append(sector)

    where_clause = (
        " WHERE " + " AND ".join(conditions)
        if conditions
        else " WHERE 1=1 "
    )

    query = f"""
        SELECT
        c.debtor_no AS debtor_no,

        c.dimension3_id AS dimension3_id,
        c.dimension2_id AS dimension2_id,

        c.ov_amount,

        d.name AS client_name,

        d.country AS country,
        c.total_expense_aed,
        c2.region_id,
        c.rate, c.tran_date, d.client_type
            FROM read_parquet('{DATA_DIR}/debtor_trans.parquet') c
            LEFT JOIN read_parquet('{DATA_DIR}/debtors_master.parquet') d
                ON c.debtor_no = d.debtor_no
            LEFT JOIN '{DATA_DIR}/country.parquet' c2
            ON c2.id = d.country
            {where_clause}
        """

    df_top_job_clients_merged = con.execute(query, params).fetchdf()
    
    df_top_job_clients_merged['client_type'] = df_top_job_clients_merged['client_type'].astype(int)
    # Filter by active period (last 365 days)
    df_top_job_clients_filtered = df_top_job_clients_merged[
        (df_top_job_clients_merged["tran_date"] >= JOB_FROM_DATE) &
        (df_top_job_clients_merged["tran_date"] <= JOB_TO_DATE)&
        (df_top_job_clients_merged["client_type"]!=5)
    ]
    df_top_job_clients_filtered["country"] = pd.to_numeric(
    df_top_job_clients_filtered["country"], errors="coerce"
    ).fillna(0).astype(int)
    # Merge with country table to get country name and region_id
    df_top_job_clients_filtered = pd.merge(
        df_top_job_clients_filtered,
        df_country[["id", "name", "region_id","colour_code"]],
        left_on="country",
        right_on="id",
        how="left",
        suffixes=("", "_country")
    ).rename(columns={"name": "country_name", "colour_code": "colour_code"}).drop(columns=["id"])
    
    # Store country_id for later filtering
    df_top_job_clients_filtered["country_id"] = df_top_job_clients_filtered["country"]

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
    #top_job_clients.to_csv("top_job_clients_ONE.csv", index=False)
    import numpy as np

    df_top_job_clients_filtered = df_top_job_clients_filtered.fillna(0).replace([np.inf, -np.inf], 0)
     
    df_top_job_clients_filtered_gcc = df_top_job_clients_filtered[
        df_top_job_clients_filtered["country_id"].isin([1,5,16,2,3,4])   
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
    top_10_job_clients_by_region = df_region1.merge(
        df_top_job_clients_filtered,
        how="left",
        on=["id"]
    ).rename(columns={"colour_code_x":"colour_code","region_name_x":"region_name"})
    #top_10_job_clients_by_region.to_csv('region.csv',index=False)
    top_10_job_clients_by_region = (
        top_10_job_clients_by_region
        .groupby(["id"], as_index=False)
        .agg({
            "invoice_amount": "sum",
            "region_name": "first",
            "colour_code": "first"
        })
        .sort_values("invoice_amount", ascending=False)
    )
    top_10_job_clients_by_region = top_10_job_clients_by_region[
        top_10_job_clients_by_region['id']>0
    ]
    df_top_job_clients_filtered_gcc = df_gcc_countries.merge(
        df_top_job_clients_filtered_gcc,
        how="left",
        left_on="id",
        right_on="country_id"
    ).rename(columns={"id_x":"id","colour_code_x":"colour_code","name":"country_name","country_name":"country_name_x"})
    # Gcc countries status in less than a year
    df_top_job_clients_filtered_gcc_by_region = (
        df_top_job_clients_filtered_gcc
        .groupby(["id"], as_index=False)
        .agg({
            "invoice_amount": "sum",
            "country_name": "first"
        })
        .sort_values("invoice_amount", ascending=False)
        .head(10)
    )
    
    ############################################################################################
    def make_json_safe(df: pd.DataFrame) -> pd.DataFrame:
        return (
        df.replace([np.inf, -np.inf], np.nan)
          .fillna(0)
    )
    top_10_clients = make_json_safe(top_10_clients)
    top_10_job_clients = make_json_safe(top_10_job_clients)
    top_10_job_clients_by_region = make_json_safe(top_10_job_clients_by_region)
    top_10_enquiry_clients_by_region = make_json_safe(top_10_enquiry_clients_by_region)
    df_top_enquiry_clients_filtered_gcc_by_region = make_json_safe(df_top_enquiry_clients_filtered_gcc_by_region)
    df_top_job_clients_filtered_gcc_by_region = make_json_safe(df_top_job_clients_filtered_gcc_by_region)

    ####################################################################
    # ---- API Endpoint ----
    """Returns top 10 clients sorted by enquiry amount (aprox_amount * rate) in last 365 days"""
    return {
        "top_10_clients_enquiry": top_10_clients.to_dict(orient="records"),
        "top_10_clients_invoice": top_10_job_clients.to_dict(orient="records"),
        "top_10_clients_invoice_by_region": top_10_job_clients_by_region.to_dict(orient="records"),
        "top_10_clients_enquiry_by_region": top_10_enquiry_clients_by_region.to_dict(orient="records"),
        "top_10_gcc_clients_enquiry_by_country": df_top_enquiry_clients_filtered_gcc_by_region.to_dict(orient="records"),
        "top_10_gcc_clients_invoice_by_country": df_top_job_clients_filtered_gcc_by_region.to_dict(orient="records"),
    }