from typing import Tuple, List, Dict, Any
from app.query.spec import QuerySpec


def build_sql(spec: QuerySpec) -> Tuple[str, List[Any], Dict[str, Any]]:
    where: List[str] = []
    params: List[Any] = []

    # Date range filter (inclusive)
    where.append("CAST(sale_date AS DATE) BETWEEN ? AND ?")
    params.extend([spec.date_range.start.isoformat(), spec.date_range.end.isoformat()])

    # Borough filter (values are lowercase in the dataset)
    if spec.borough:
        ph = ",".join(["?"] * len(spec.borough))
        where.append(f"borough IN ({ph})")
        params.extend([b.lower() for b in spec.borough])

    # Neighborhood filter (case-sensitive in source; normalize to lower)
    if spec.neighborhood:
        ph = ",".join(["?"] * len(spec.neighborhood))
        where.append(f"lower(neighborhood) IN ({ph})")
        params.extend([n.lower() for n in spec.neighborhood])

    # Building class category filter (exact match)
    if spec.building_class_category:
        ph = ",".join(["?"] * len(spec.building_class_category))
        where.append(f"building_class_category IN ({ph})")
        params.extend(spec.building_class_category)

    where_sql = " AND ".join(where) if where else "TRUE"

    # Grouping
    group_cols: List[str] = []
    select_keys: List[str] = []

    if spec.groupby == "month":
        group_cols.append("date_trunc('month', CAST(sale_date AS DATE)) AS month")
        select_keys.append("month")
        order_by = "ORDER BY month"
    elif spec.groupby == "neighborhood":
        group_cols.append("neighborhood")
        select_keys.append("neighborhood")
        order_by = "ORDER BY neighborhood"
    elif spec.groupby == "class":
        group_cols.append("building_class_category")
        select_keys.append("building_class_category")
        order_by = "ORDER BY building_class_category"
    else:
        order_by = ""

    group_expr = ""
    group_by_clause = ""
    if group_cols:
        group_expr = ", " + ", ".join(select_keys)
        group_by_clause = "GROUP BY " + ", ".join(select_keys)

    metrics = """
        COUNT(*) AS txns,
        SUM(sale_price) AS total_sale_price,
        MEDIAN(sale_price) AS median_sale_price,
        MEDIAN(price_per_sqft) AS median_price_per_sqft
    """

    sql = f"""
    WITH src AS (
        SELECT
            borough,
            neighborhood,
            building_class_category,
            sale_price,
            price_per_sqft,
            sale_date
        FROM nyc
        WHERE {where_sql}
    )
    SELECT
        {metrics.strip()}{group_expr}
    FROM src
    {group_by_clause}
    {order_by}
    """.strip()

    filters_echo: Dict[str, Any] = {
        "date_range": {"start": spec.date_range.start.isoformat(), "end": spec.date_range.end.isoformat()},
        "borough": [b.lower() for b in spec.borough] if spec.borough else None,
        "neighborhood": [n for n in spec.neighborhood] if spec.neighborhood else None,
        "building_class_category": [c for c in spec.building_class_category] if spec.building_class_category else None,
        "groupby": spec.groupby,
    }

    return sql, params, filters_echo
