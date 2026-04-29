from datetime import date
from fastapi import APIRouter, Query, params
from typing import Optional
import numpy as np
import pandas as pd
from app.config import DATA_DIR
import math
from app.constants import (
    ACTIVE_FROM_DATE, ACTIVE_TO_DATE,
    INACTIVE_FROM_DATE, INACTIVE_TO_DATE,
    LOST_TO_DATE,PREV_JOB_TO_DATE,PREV_JOB_FROM_DATE,PREV_ENQUIRY_FROM_DATE,JOB_FROM_DATE,
    JOB_TO_DATE, NON_MARINE_DIVISION
)
import duckdb
import numpy as np

con = duckdb.connect()

router_listing = APIRouter(prefix="/listing", tags=["Listing API"])


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
    
def normalize_key(df, col):
    df[col] = (
        df[col]
        .astype(str)
        .str.strip()
        .replace({"nan": None})
    )
    return df
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
df_idle_list = df_client_activity_status = pd.read_parquet(
    DATA_DIR / "client_activity_status.parquet"
)
           
con.execute(f"""
CREATE OR REPLACE VIEW v_enquiry AS
SELECT
    c.client_enquiry_id,
    COALESCE(CAST(d.country AS INTEGER), TRY_CAST(t.country AS INTEGER)) AS country_id,
    co.name AS country_name,
    r.id AS region_id,
    r.name AS region_name,
    c.enq_status,
    c.enquiry_date,
    c.aprox_amount * c.rate AS amount_value,
    COALESCE(d.client_type, t.temp_client_type) AS client_type,
    c.division AS division,
    c.subdivision AS sub_division,
    CASE
        WHEN d.debtor_no IS NOT NULL THEN d.debtor_no
        ELSE t.temp_clients_id
    END AS debtor_no,
    COALESCE(CAST(d.client_type AS INTEGER), TRY_CAST(t.temp_client_type AS INTEGER)) AS client_type
FROM read_parquet('{DATA_DIR}/client_enquiry.parquet') c
LEFT JOIN read_parquet('{DATA_DIR}/debtors_master.parquet') d
    ON c.debtor_no = d.debtor_no
LEFT JOIN read_parquet('{DATA_DIR}/temp_clients.parquet') t
    ON c.enquiry_temp_id = t.temp_clients_id
LEFT JOIN read_parquet('{DATA_DIR}/country.parquet') co
    ON COALESCE(CAST(d.country AS INTEGER), TRY_CAST(t.country AS INTEGER)) = co.id
LEFT JOIN read_parquet('{DATA_DIR}/region.parquet') r
    ON co.region_id = r.id
WHERE COALESCE(CAST(d.client_type AS INTEGER), TRY_CAST(t.temp_client_type AS INTEGER)) != 5
""")

con.execute(f"""
            CREATE OR REPLACE VIEW v_invoice AS
SELECT
    CAST(d.country AS INTEGER) AS country_id, dt.dimension2_id division, dt.dimension3_id sub_division, r.id as region_id, 

    (dt.ov_amount * dt.rate) - COALESCE(dt.total_expense_aed, 0) AS invoice_amount,
    dt.trans_no AS invoice_no, dt.debtor_no, dt.tran_date,d.client_type

FROM read_parquet('{DATA_DIR}/debtor_trans.parquet') dt
LEFT JOIN read_parquet('{DATA_DIR}/debtors_master.parquet') d
    ON d.debtor_no = dt.debtor_no
LEFT JOIN read_parquet('{DATA_DIR}/country.parquet') co
    ON CAST(d.country AS INTEGER) = co.id
LEFT JOIN read_parquet('{DATA_DIR}/region.parquet') r
    ON co.region_id = r.id

WHERE CAST(d.client_type AS INTEGER) != 5
  AND CAST(d.country AS INTEGER) IS NOT NULL""")

@router_listing.get("/country-listings-enquiry")
def top_countries(
        division:  Optional[int] = Query(None),
        country: Optional[int] = Query(None),       # OPTIONAL 
        region: Optional[int] = Query(None),        # OPTIONAL
        subdivision: Optional[int] = Query(None),
        type: Optional[str] = Query(None),   # OPTIONAL: "invoice" (default) or "enquiry",
        sector: Optional[int] = Query(None),       # OPTIONAL
        startDate:Optional[date] = Query(None),
        endDate:Optional[date] = Query(None),
        order: Optional[str] = Query("DESC"),    # Default to DESC
        orderby: Optional[str] = Query(None)
):
    
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
    total_countries = df_client_country_status["country_id"].nunique()
    df_client_country_status = df_client_country_status[df_client_country_status["country_id"] > 0]
    if type == "active_enq":
        df_client_country_status = df_client_country_status[
            (df_client_country_status['enquiry_date'] >= ACTIVE_FROM_DATE) &
            (df_client_country_status['enquiry_date'] <= ACTIVE_TO_DATE) 
        ]
    elif type is not None and type == "inactive_enq":
        df_client_country_status = df_client_country_status[
            (df_client_country_status['enquiry_date']>=INACTIVE_FROM_DATE) &
            (df_client_country_status['enquiry_date']<=INACTIVE_TO_DATE) 
        ]
    elif type is not None and type == "lost_enq":
        df_client_country_status = df_client_country_status[
            (df_client_country_status['enquiry_date']<=LOST_TO_DATE) 
        ]
    elif type is not None and type == "total_job":
        df_client_country_status = df_client_country_status[
            (df_client_country_status["job_date"] >pd.to_datetime("2020-01-01")) &
            (df_client_country_status['job_date']<=ACTIVE_TO_DATE) 
        ]
    elif type is not None and type == "job_active":
        df_client_country_status = df_client_country_status[
             (df_client_country_status['job_date']>=ACTIVE_FROM_DATE) &
            (df_client_country_status['job_date']<=ACTIVE_TO_DATE) 
        ]
    elif type is not None and type == "job_inactive":
        df_client_country_status = df_client_country_status[
            (df_client_country_status['job_date']>=INACTIVE_FROM_DATE) &
            (df_client_country_status['job_date']<=INACTIVE_TO_DATE) 
        ]
    elif type is not None and type == "job_lost":
        df_client_country_status = df_client_country_status[
            (df_client_country_status['job_date']<=LOST_TO_DATE) 
        ]
    else:
        # Default behavior: Filter by enquiry_date using URL startDate
        df_client_country_status = df_client_country_status[
            (df_client_country_status["enquiry_date"] >= pd.to_datetime("2020-01-01"))
    ]    

    
    
    
    query_invoice = """
        SELECT
            country_id as country_id,
            COUNT(*) AS total_invoice_count,
            SUM(invoice_amount) AS total_invoice_amount

        FROM  v_invoice
        WHERE country_id IS NOT NULL
        """
    params = []
    if division is not None:
        query_invoice += " AND division = ?"
        params.append(division)

    if subdivision is not None:
        query_invoice += " AND sub_division = ?"
        params.append(subdivision)

    if country is not None:
        query_invoice += " AND country_id = ?"
        params.append(country)

    if region is not None:
        query_invoice += " AND region_id = ?"
        params.append(region)

    if startDate is not None:
        query_invoice += " AND tran_date >= ?"
        params.append(startDate)
    
    if endDate is not None:
        query_invoice += " AND tran_date <= ?"
        params.append(endDate)
    
    query_invoice += """
        GROUP BY country_id
        """
    df_invoice_status = con.execute(query_invoice, params).fetchdf()    
    query = """
        SELECT
            v_enquiry.country_id,
            v_enquiry.country_name,
            v_enquiry.region_name,

            COUNT(*) AS total_enquiry_count,
            SUM(amount_value) AS total_enquiry_amount,

            SUM(CASE WHEN enq_status = 1 THEN 1 ELSE 0 END) AS cancel_enquiry_count,
            SUM(CASE WHEN enq_status = 1 THEN amount_value ELSE 0 END) AS cancel_enquiry_amount,

            SUM(CASE WHEN enq_status = 2 THEN 1 ELSE 0 END) AS lost_enquiry_count,
            SUM(CASE WHEN enq_status = 2 THEN amount_value ELSE 0 END) AS lost_enquiry_amount

        FROM v_enquiry
        WHERE v_enquiry.country_id IS NOT NULL
        """
   
    params = []

    if division is not None:
        query += " AND division = ?"
        params.append(division)

    if subdivision is not None:
        query += " AND sub_division = ?"
        params.append(subdivision)

    if country is not None:
        query += " AND country_id = ?"
        params.append(country)

    if region is not None:
        query += " AND region_id = ?"
        params.append(region)

    if startDate:
        query += " AND enquiry_date >= ?"
        params.append(startDate)
    
    if endDate:
        query += " AND enquiry_date <= ?"
        params.append(endDate)
    query += """
        GROUP BY v_enquiry.country_id, v_enquiry.country_name, v_enquiry.region_name
        """

    df_enquiry_status = con.execute(query, params).fetchdf()
        # --------------------------------------------------
        # 9. Conditional aggregation (CANCELLED / LOST)
        # --------------------------------------------------
    df_client_country_status = (
        df_client_country_status
        .merge(
            df_enquiry_status,
            how="left",
            on="country_id",
            validate="one_to_one",
            suffixes=("", "_enquiry")
        )
        .merge(
            df_invoice_status,
            how="left",
            on="country_id",
            validate="one_to_one",
            suffixes=("", "_invoice")
        )
    )
    sort_mapping = {
        "enquiry_no": "total_enquiry_count",
        "enquiry_amount": "total_enquiry_amount",
        "jobs": "total_invoice_count",           # 'jobs' in PHP maps to invoice count
        "actual_invoice": "total_invoice_amount", # 'actual_invoice' in PHP maps to invoice amount
        "lost_enquiry": "lost_enquiry_count",
        "lost_amount": "lost_enquiry_amount",
        "cancel_enquiry": "cancel_enquiry_count",
        "cancel_amount": "cancel_enquiry_amount"
    }

    target_column = sort_mapping.get(orderby)

    if not target_column:
        if type == "total_job" or (type and "job" in type):
            target_column = "total_invoice_amount"
        else:
            target_column = "total_enquiry_amount"

    if target_column not in df_client_country_status.columns:
        # Fallback to amount if the mapping failed
        target_column = "total_enquiry_amount" 

    # is_asc will be True if "ASC", False if "DESC"
    is_asc = (str(order).upper() == "ASC")
    
    df_client_country_status = df_client_country_status.sort_values(
        by=[target_column, "country_id"], 
        ascending=[is_asc, True] # Tie-breaker is always ascending for stability
    ).reset_index(drop=True)
    #df_client_country_status.to_csv("client_country_status.csv", index=False)
    return {
    "count": int(df_enquiry_status["country_id"].nunique()),
    "top_countries": (
        df_client_country_status[
            [
                "country_id",
                "country_name",
                "region_name",
                "total_enquiry_count",
                "total_enquiry_amount",
                "cancel_enquiry_count",
                "cancel_enquiry_amount",
                "lost_enquiry_count",
                "lost_enquiry_amount",
                "total_invoice_count",
                "total_invoice_amount",
            ]
        ]
        .fillna(0)
        .to_dict(orient="records")
    ),
    }
##################################################################################################################################################################################################
@router_listing.get("/country-listings-idle")
def top_countries_idle(
        division:  Optional[int] = Query(None),
        country: Optional[int] = Query(None),       # OPTIONAL 
        region: Optional[int] = Query(None),        # OPTIONAL
        subdivision: Optional[int] = Query(None),
        type: Optional[str] = Query(None),   # OPTIONAL: "invoice" (default) or "enquiry",
        sector: Optional[int] = Query(None),       # OPTIONAL
        startDate:Optional[date] = Query(None),
        endDate:Optional[date] = Query(None),
        order: Optional[str] = Query("DESC"),    # Default to DESC
        orderby: Optional[str] = Query(None)       # OPTIONAL
):
    
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
       ANY_VALUE(c.division) division,
       ANY_VALUE(c.sub_division) sub_division
        
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

    if type=='idle_enq':
         df_client_country_status = df_client_country_status[
            (df_client_country_status["enquiry_date"] >pd.to_datetime("2020-01-01")) 
        ]
    if type=='idle_job':
         df_client_country_status = df_client_country_status[
            (df_client_country_status["job_date"] >pd.to_datetime("2020-01-01")) &
           (df_client_country_status['job_date']<=ACTIVE_TO_DATE)  
        ]
    idle_enquiry_countries = df_idle_list[
        (df_idle_list['enquiry_date']>= pd.to_datetime("2020-01-01")) &
        (df_idle_list['country_id']>0)
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

    
    
    conditions = []
    params = []
   




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
       ANY_VALUE(c.division) division,
       ANY_VALUE(c.sub_division) sub_division
        
    FROM '{DATA_DIR}/client_activity_status.parquet' c
    LEFT JOIN '{DATA_DIR}/country.parquet' d
        ON c.country_id = d.id
    LEFT JOIN '{DATA_DIR}/region.parquet' r
        ON c.region_id = r.id
    WHERE c.country_id IS NOT NULL AND c.country_id > 0 AND c.client_type!=5 
    {where_clause}
    GROUP BY c.country_id, country_name
    """
   
    df_client_country_status = con.execute(query).fetchdf()
       
    if type=='idle_enq':
         df_client_country_status = df_client_country_status[
            (df_client_country_status["enquiry_date"] >pd.to_datetime("2020-01-01")) 
        ]
    if type=='idle_job':
         df_client_country_status = df_client_country_status[
            (df_client_country_status["job_date"] >pd.to_datetime("2020-01-01")) &
           (df_client_country_status['job_date']<=ACTIVE_TO_DATE)  
        ]          

    total_countries = df_client_country_status["country_id"].nunique()
   
    if type=='idle_enq':
        if exclude_enquiry_country is not None:
            idle_enquiry_countries = idle_enquiry_countries[
            (~idle_enquiry_countries["country_id"].isin(exclude_enquiry_country.drop_duplicates().tolist())) &
            (idle_enquiry_countries["enquiry_date"] > pd.to_datetime("2020-01-01"))
        ].drop_duplicates(subset=["country_id"])
        df_client_country_status = idle_enquiry_countries.merge(
            df_client_country_status[["country_id", "country_name", "region_name"]],        
            on="country_id", how="left"
        )
  
    total_countries_idle = df_client_country_status["country_id"].nunique()
   
    
    if type=='idle_job':
        
        if exclude_job_countries is not None:
            idle_job_countries = idle_job_countries[
                (~idle_job_countries["country_id"].isin(exclude_job_countries.drop_duplicates().tolist())) &
                (idle_job_countries["job_date"] > pd.to_datetime("2020-01-01"))
            ].drop_duplicates(subset=["country_id"])
        df_client_country_status = idle_job_countries.merge(
            df_client_country_status[["country_id", "country_name", "region_name"]],
            on="country_id", how="left"
        )
    
    query_invoice = """
        SELECT
            country_id as country_id,
            COUNT(*) AS total_invoice_count,
            SUM(invoice_amount) AS total_invoice_amount

        FROM  v_invoice
        WHERE country_id IS NOT NULL
        """
    params = []
    if division is not None:
        query_invoice += " AND division != ?"
        params.append(division)

    if subdivision is not None:
        query_invoice += " AND sub_division != ?"
        params.append(subdivision)

    if country is not None:
        query_invoice += " AND country_id = ?"
        params.append(country)

    if region is not None:
        query_invoice += " AND region_id = ?"
        params.append(region)
    
    if startDate is not None:
        query_invoice += " AND tran_date >= ?"
        params.append(startDate)
    
    if endDate is not None:
        query_invoice += " AND tran_date <= ?"
        params.append(endDate)
    
    query_invoice += """
        GROUP BY country_id
        """
    df_invoice_status = con.execute(query_invoice, params).fetchdf()    
    query = """
        SELECT
            v_enquiry.country_id,
            v_enquiry.country_name,
            v_enquiry.region_name,

            COUNT(*) AS total_enquiry_count,
            SUM(amount_value) AS total_enquiry_amount,

            SUM(CASE WHEN enq_status = 1 THEN 1 ELSE 0 END) AS cancel_enquiry_count,
            SUM(CASE WHEN enq_status = 1 THEN amount_value ELSE 0 END) AS cancel_enquiry_amount,

            SUM(CASE WHEN enq_status = 2 THEN 1 ELSE 0 END) AS lost_enquiry_count,
            SUM(CASE WHEN enq_status = 2 THEN amount_value ELSE 0 END) AS lost_enquiry_amount

        FROM v_enquiry
        WHERE v_enquiry.country_id IS NOT NULL
        """
   
    params = []

    if division is not None:
        query += " AND division != ?"
        params.append(division)

    if subdivision is not None:
        query += " AND sub_division != ?"
        params.append(subdivision)

    if country is not None:
        query += " AND country_id = ?"
        params.append(country)

    if region is not None:
        query += " AND region_id = ?"
        params.append(region)
    if sector is not None:
        query += " AND region_id = ?"
        params.append(sector)
    if startDate is not None:
        query += " AND enquiry_date >= ?"
        params.append(startDate)
    
    if endDate is not None:
        query += " AND enquiry_date <= ?"
        params.append(endDate)

    query += """
        GROUP BY v_enquiry.country_id, v_enquiry.country_name, v_enquiry.region_name
        """

    df_enquiry_status = con.execute(query, params).fetchdf()
    
        # --------------------------------------------------
        # 9. Conditional aggregation (CANCELLED / LOST)
        # --------------------------------------------------
    df_client_country_status = (
    df_client_country_status
    .merge(
        df_enquiry_status,
        how="left",
        on="country_id",
        validate="one_to_one",
        suffixes=("", "_enquiry")
    )
    .merge(
        df_invoice_status,
        how="left",
        on="country_id",
        validate="one_to_one",
        suffixes=("", "_invoice")
    )
)
    sort_mapping = {
        "enquiry_no": "total_enquiry_count",
        "enquiry_amount": "total_enquiry_amount",
        "jobs": "total_invoice_count",           # 'jobs' in PHP maps to invoice count
        "actual_invoice": "total_invoice_amount", # 'actual_invoice' in PHP maps to invoice amount
        "lost_enquiry": "lost_enquiry_count",
        "lost_amount": "lost_amount",             # Check if your column is lost_enquiry_amount
        "cancel_enquiry": "cancel_enquiry_count",
        "cancel_amount": "cancel_enquiry_amount"
    }

    # 1. Determine the primary sort column
    # If the user clicked a button, use the mapping. Otherwise, default to amount.
    target_column = sort_mapping.get(orderby)

    # 2. Logic for "type" overrides (If you want 'type' to change what a button does)
    if not target_column:
        if type == "total_job" or (type and "job" in type):
            target_column = "total_invoice_amount"
        else:
            target_column = "total_enquiry_amount"

    # 3. Final Safety Check: If the column still doesn't exist in DF, fallback to a safe one
    if target_column not in df_client_country_status.columns:
        # Fallback to amount if the mapping failed
        target_column = "total_enquiry_amount" 

    # 4. Perform the Sort
    # is_asc will be True if "ASC", False if "DESC"
    is_asc = (str(order).upper() == "ASC")
    
    df_client_country_status = df_client_country_status.sort_values(
        by=[target_column, "country_id"], 
        ascending=[is_asc, True] # Tie-breaker is always ascending for stability
    ).reset_index(drop=True)
   
    #df_client_country_status.to_csv("client_country_status.csv", index=False)
    
    return {
    "count": int(df_client_country_status["country_id"].nunique()),
    "top_countries": (
        df_client_country_status[
            [
                "country_id",
                "country_name",
                "region_name",
                "total_enquiry_count",
                "total_enquiry_amount",
                "cancel_enquiry_count",
                "cancel_enquiry_amount",
                "lost_enquiry_count",
                "lost_enquiry_amount",
                "total_invoice_count",
                "total_invoice_amount",
            ]
        ]
        .fillna(0)
        .to_dict(orient="records")
    ),
    }
  
         
#####################################################################################################

@router_listing.get("/client-listings")
def top_clients(
        division:  Optional[int] = Query(None),
        country: Optional[int] = Query(None),       # OPTIONAL 
        region: Optional[int] = Query(None),        # OPTIONAL
        subdivision: Optional[int] = Query(None),
        type: Optional[str] = Query(None),
        sector: Optional[str] = Query(None),
        startDate:Optional[date]=Query(None),
        endDate:Optional[date]=Query(None)  # OPTIONAL: "invoice" (default) or "enquiry"
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
        {where_clause}
    GROUP BY c.debtor_no,c.temp_client_id"""
 ###########################################################################   
    df_client_status = con.execute(query, params).fetchdf() 
    if type is not None and type == "active_enq":
        df_client_status = df_client_status[
            (df_client_status['enquiry_date']>=ACTIVE_FROM_DATE) &
            (df_client_status['enquiry_date']<=ACTIVE_TO_DATE) 
        ]
    if type is not None and type == "inactive_enq":
            df_client_status = df_client_status[
            (df_client_status['enquiry_date']>=INACTIVE_FROM_DATE) &
            (df_client_status['enquiry_date']<=INACTIVE_TO_DATE) 
        ]
    if type is not None and type == "lost_enq":
            df_client_status = df_client_status[
            (df_client_status["enquiry_date"] >pd.to_datetime("2020-01-01")) &
            (df_client_status['enquiry_date']<=LOST_TO_DATE) 
        ]
    if type is not None and type == "total_job":
            df_client_status = df_client_status[
            (df_client_status["job_date"] >pd.to_datetime("2020-01-01")) &
            (df_client_status['job_date']<=ACTIVE_TO_DATE) 
        ]
    if type is not None and type == "job_active":
            df_client_status = df_client_status[
             (df_client_status['job_date']>=ACTIVE_FROM_DATE) &
            (df_client_status['job_date']<=ACTIVE_TO_DATE) 
        ]
    if type is not None and type == "job_inactive":
            df_client_status = df_client_status[
            (df_client_status['job_date']>=INACTIVE_FROM_DATE) &
            (df_client_status['job_date']<=INACTIVE_TO_DATE) 
        ]
    if type is not None and type == "job_lost":
            df_client_status = df_client_status[
            (df_client_status['job_date']<=LOST_TO_DATE) 
        ]
    if type is not None and type == "job_blacklisted":
            df_client_status = df_client_status[
            (df_client_status['client_category'].isin([6]))&
            (df_client_status["job_date"] >pd.to_datetime("2020-01-01"))  
        ]
    if type is not None and type == "job_nonexisting":
            df_client_status = df_client_status[
            (df_client_status['client_category'].isin([2,4,11,12])) &
            (df_client_status["job_date"] >pd.to_datetime("2020-01-01")) 
        ]
    if type is not None and type == "blacklisted_enq":
            df_client_status = df_client_status[
            (df_client_status['client_category'].isin([6]))&
            (df_client_status["enquiry_date"] >pd.to_datetime("2020-01-01"))  
        ]
    if type is not None and type == "nonexisting_enq":
            df_client_status = df_client_status[
            (df_client_status['client_category'].isin([2,4,11,12])) &
            (df_client_status["enquiry_date"] >pd.to_datetime("2020-01-01")) 
        ]
    if type is not None and type == "idle_enq":
            df_client_status = df_client_status[
            (df_client_status['client_category'].isin([2,4,11,12])) &
            (df_client_status["enquiry_date"] >pd.to_datetime("2020-01-01")) 
        ]
     
    query_invoice = """
        SELECT
            debtor_no as debtor_no,
            COUNT(*) AS total_invoice_count,
            SUM(invoice_amount) AS total_invoice_amount

        FROM  v_invoice
        WHERE debtor_no IS NOT NULL
        """
    params = []
    if division is not None:
        query_invoice += " AND division = ?"
        params.append(division)

    if subdivision is not None:
        query_invoice += " AND sub_division = ?"
        params.append(subdivision)

    if country is not None:
        query_invoice += " AND country_id = ?"
        params.append(country)

    if region is not None:
        query_invoice += " AND region_id = ?"
        params.append(region)

    if sector is not None:
        query_invoice += " AND client_type = ?"
        params.append(sector)
    
    if startDate is not None:
        query_invoice += " AND tran_date >= ?"
        params.append(startDate)
    
    if endDate is not None:
        query_invoice += " AND tran_date <= ?"
        params.append(endDate)

    query_invoice += """
        GROUP BY debtor_no
        """
    df_invoice_status = con.execute(query_invoice, params).fetchdf()   
    
   
    query = """
        SELECT
            v_enquiry.debtor_no,
            v_enquiry.country_name,
            v_enquiry.region_name,

            COUNT(*) AS total_enquiry_count,
            SUM(amount_value) AS total_enquiry_amount,

            SUM(CASE WHEN enq_status = 1 THEN 1 ELSE 0 END) AS cancel_enquiry_count,
            SUM(CASE WHEN enq_status = 1 THEN amount_value ELSE 0 END) AS cancel_enquiry_amount,

            SUM(CASE WHEN enq_status = 2 THEN 1 ELSE 0 END) AS lost_enquiry_count,
            SUM(CASE WHEN enq_status = 2 THEN amount_value ELSE 0 END) AS lost_enquiry_amount

        FROM v_enquiry
        WHERE v_enquiry.debtor_no IS NOT NULL
        """
     
    params = []

    if division is not None:
        query += " AND division = ?"
        params.append(division)

    if subdivision is not None:
        query += " AND sub_division = ?"
        params.append(subdivision)

    if country is not None:
        query += " AND country_id = ?"
        params.append(country)

    if region is not None:
        query += " AND region_id = ?"
        params.append(region)
    
    if sector is not None:
        query += " AND client_type = ?"
        params.append(sector)

    if startDate is not None:
        query += " AND enquiry_date >= ?"
        params.append(startDate)
    
    if endDate is not None:
        query+= " AND enquiry_date <= ?"
        params.append(endDate)

    query += """
        GROUP BY v_enquiry.debtor_no,
        v_enquiry.country_name,
        v_enquiry.region_name
        """
    
    df_enquiry_status = con.execute(query, params).fetchdf()
    
        # --------------------------------------------------
        # 9. Conditional aggregation (CANCELLED / LOST)
        # --------------------------------------------------
    normalize_key(df_client_status, "debtor_no")
    normalize_key(df_invoice_status, "debtor_no")
    normalize_key(df_enquiry_status, "debtor_no")
    # --- Merge client + invoice data ---
    df_client_invoice = pd.merge(
        df_client_status,
        df_invoice_status,
        on='debtor_no',
        how='left'
    )

    # --- Merge the above with enquiry data ---
    df_client_full = pd.merge(
        df_client_invoice,
        df_enquiry_status,
        on='debtor_no',
        how='left'
    )
    
    df_client_full = df_client_full.sort_values(
        by='total_enquiry_amount',
        ascending=False
    )
    df_client_full['debtor_no'] = pd.to_numeric(df_client_full['debtor_no'], errors='coerce')
    df_client_full['temp_client_id'] = pd.to_numeric(df_client_full['temp_client_id'], errors='coerce')
    df_client_full.drop_duplicates(subset=['debtor_no', 'temp_client_id'], inplace=True)
    unique_debtor = df_client_full.loc[df_client_full['debtor_no'] > 0, 'debtor_no'].nunique()
    unique_temp = df_client_full.loc[df_client_full['temp_client_id'] > 0, 'temp_client_id'].nunique()
    # df_client_full.to_csv("client_full.csv", index=False)
    total_count = unique_debtor + unique_temp
    
    return {
    "count": int(total_count),
    "top_clients": (
    df_client_full[
            [
                "debtor_no",
                "client_id",
                "client_name",
                "client_type",
                "client_status",
                "temp_client_id",
                "total_enquiry_count",
                "total_enquiry_amount",
                "cancel_enquiry_count",
                "cancel_enquiry_amount",
                "lost_enquiry_count",
                "lost_enquiry_amount",
                "total_invoice_count",
                "total_invoice_amount",
            ]
        ]
        .fillna(0)
        .to_dict(orient="records")
    ),
    }

##############################################################################

@router_listing.get("/client-listings-idle")
def top_clients(
        division:  Optional[int] = Query(None),
        country: Optional[int] = Query(None),       # OPTIONAL 
        region: Optional[int] = Query(None),        # OPTIONAL
        subdivision: Optional[int] = Query(None),
        sector: Optional[int] = Query(None),
        type: Optional[str] = Query(None)   # OPTIONAL: "invoice" (default) or "enquiry"
):  
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
        conditions.append("c.client_type = ?")
        params.append(sector)

    where_clause =  "AND " + " AND ".join(conditions) if conditions else "  "
    
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
        AND c.temp_client_id = 0
        {where_clause}
    GROUP BY c.debtor_no,c.temp_client_id"""
 ###########################################################################  
    df_client_status = con.execute(query, params).fetchdf() 
    
    
    
    # df_client_status.to_csv("client_division_status.csv", index=False)
    if type=='idle_enq':
         exclude_enquiry_clients = df_client_status.loc[
        (df_client_status['enquiry_date']> pd.to_datetime("2020-01-01")) &
        (df_client_status['temp_client_id'] == 0), 'debtor_no'
    ]
    
    if type=='idle_job':
        exclude_job_clients = df_client_status.loc[
        (df_client_status['job_date']> pd.to_datetime("2020-01-01")) &
        (df_client_status['temp_client_id'] == 0), 'debtor_no'
    ]
    
    
    
    

########################## TOTAL CLIENTS ######################################
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
        AND c.temp_client_id = 0
    GROUP BY c.debtor_no,c.temp_client_id"""
 ###########################################################################   
    df_client_status = con.execute(query).fetchdf() 

    # df_client_status.to_csv("client_total_status.csv", index=False)
    if type=='idle_enq':
         
        if exclude_enquiry_clients is not None:
            df_client_status = df_client_status[
                (~df_client_status["debtor_no"].isin(exclude_enquiry_clients.tolist())) 
            ].drop_duplicates(subset=["debtor_no"])
    if type=='idle_job':
        df_client_status = df_client_status[
             (df_client_status['job_date']> pd.to_datetime("2020-01-01")) &
             (df_client_status['debtor_no']>0)
        ]
        if exclude_job_clients is not None:
            df_client_status = df_client_status[
                (~df_client_status["debtor_no"].isin(exclude_job_clients.tolist())) 
            ].drop_duplicates(subset=["debtor_no"]) 
    # df_client_status.to_csv("client_idle_status.csv", index=False)
##########################################################################
    
   
     
    query_invoice = """
        SELECT
            debtor_no as debtor_no,
            COUNT(*) AS total_invoice_count,
            SUM(invoice_amount) AS total_invoice_amount

        FROM  v_invoice
        WHERE debtor_no IS NOT NULL
        """
    params = []
    if division is not None:
        query_invoice += " AND division != ?"
        params.append(division)

    if subdivision is not None:
        query_invoice += " AND sub_division != ?"
        params.append(subdivision)

    if country is not None:
        query_invoice += " AND country_id = ?"
        params.append(country)

    if region is not None:
        query_invoice += " AND region_id = ?"
        params.append(region)
    
    if sector is not None:
        query_invoice += " AND client_type = ?"
        params.append(sector)
    query_invoice += """
        GROUP BY debtor_no
        """
    df_invoice_status = con.execute(query_invoice, params).fetchdf()   
    
   
    query = """
        SELECT
            v_enquiry.debtor_no,
            v_enquiry.country_name,
            v_enquiry.region_name,

            COUNT(*) AS total_enquiry_count,
            SUM(amount_value) AS total_enquiry_amount,

            SUM(CASE WHEN enq_status = 1 THEN 1 ELSE 0 END) AS cancel_enquiry_count,
            SUM(CASE WHEN enq_status = 1 THEN amount_value ELSE 0 END) AS cancel_enquiry_amount,

            SUM(CASE WHEN enq_status = 2 THEN 1 ELSE 0 END) AS lost_enquiry_count,
            SUM(CASE WHEN enq_status = 2 THEN amount_value ELSE 0 END) AS lost_enquiry_amount

        FROM v_enquiry
        WHERE v_enquiry.debtor_no IS NOT NULL
        """
     
    params = []

    if division is not None:
        query += " AND division != ?"
        params.append(division)

    if subdivision is not None:
        query += " AND sub_division != ?"
        params.append(subdivision)

    if country is not None:
        query += " AND country_id = ?"
        params.append(country)

    if region is not None:
        query += " AND region_id = ?"
        params.append(region)

    if sector is not None:
        query += " AND client_type = ?"
        params.append(sector)
    
    query += """
        GROUP BY v_enquiry.debtor_no,
        v_enquiry.country_name,
        v_enquiry.region_name
        """
    
    df_enquiry_status = con.execute(query, params).fetchdf()
        # --------------------------------------------------
        # 9. Conditional aggregation (CANCELLED / LOST)
        # --------------------------------------------------
    normalize_key(df_client_status, "debtor_no")
    normalize_key(df_invoice_status, "debtor_no")
    normalize_key(df_enquiry_status, "debtor_no")

    # --- Merge client + invoice data ---
    df_client_invoice = pd.merge(
        df_client_status,
        df_invoice_status,
        on='debtor_no',
        how='left'
    )

    df_enquiry_status = df_enquiry_status.drop_duplicates(subset=['debtor_no'])
    # --- Merge the above with enquiry data ---
    df_client_full = pd.merge(
        df_client_invoice,
        df_enquiry_status,
        on='debtor_no',
        how='left'
    )
    
    df_client_full = df_client_full.sort_values(
        by='total_enquiry_amount',
        ascending=False
    )
    
    # df_client_full.to_csv("client_idle_full.csv", index=False)
    
    return {
    "count": int(df_client_full["debtor_no"].nunique()),
    "top_clients": (
    df_client_full[
            [
                "debtor_no",
                "client_id",
                "client_name",
                "client_type",
                "client_status",
                "temp_client_id",
                "total_enquiry_count",
                "total_enquiry_amount",
                "cancel_enquiry_count",
                "cancel_enquiry_amount",
                "lost_enquiry_count",
                "lost_enquiry_amount",
                "total_invoice_count",
                "total_invoice_amount",
            ]
        ]
        .fillna(0)
        .to_dict(orient="records")
    ),
    }