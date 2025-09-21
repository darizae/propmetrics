from typing import Tuple, List, Dict, Any
from app.query.spec import QuerySpec


def build_sql(spec: QuerySpec) -> Tuple[str, List[Any], Dict[str, Any]]:
    where: List[str] = []
    params: List[Any] = []

    # Date range
    where.append("CAST(sale_date AS DATE) BETWEEN ? AND ?")
    params.extend([spec.date_range.start.isoformat(), spec.date_range.end.isoformat()])

    # Borough filter (normalized)
    if spec.borough:
        ph = ",".join(["?"] * len(spec.borough))
        where.append(f"lower(trim(borough)) IN ({ph})")
        params.extend([b.strip().lower() for b in spec.borough])

    # Neighborhood filter (normalized)
    if spec.neighborhood:
        ph = ",".join(["?"] * len(spec.neighborhood))
        where.append(f"lower(trim(neighborhood)) IN ({ph})")
        params.extend([n.strip().lower() for n in spec.neighborhood])

    # Building class category filter (trim only)
    if spec.building_class_category:
        ph = ",".join(["?"] * len(spec.building_class_category))
        where.append(f"trim(building_class_category) IN ({ph})")
        params.extend([c.strip() for c in spec.building_class_category])

    where_sql = " AND ".join(where) if where else "TRUE"

    # Grouping
    select_key_aliases: List[str] = []
    group_by_exprs: List[str] = []
    if spec.groupby == "month":
        month_expr = "date_trunc('month', CAST(sale_date AS DATE))"
        select_key_aliases.append(f"{month_expr} AS month")
        group_by_exprs.append(month_expr)
        order_by = "ORDER BY month"
    elif spec.groupby == "neighborhood":
        select_key_aliases.append("neighborhood")
        group_by_exprs.append("neighborhood")
        order_by = "ORDER BY neighborhood"
    elif spec.groupby == "class":
        select_key_aliases.append("building_class_category")
        group_by_exprs.append("building_class_category")
        order_by = "ORDER BY building_class_category"
    else:
        order_by = ""

    group_expr = ""
    group_by_clause = ""
    if select_key_aliases:
        group_expr = ", " + ", ".join(select_key_aliases)
        group_by_clause = "GROUP BY " + ", ".join(group_by_exprs)

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
        "borough": [b.strip().lower() for b in spec.borough] if spec.borough else None,
        "neighborhood": [n.strip().lower() for n in spec.neighborhood] if spec.neighborhood else None,
        "building_class_category": [c.strip() for c in
                                    spec.building_class_category] if spec.building_class_category else None,
        "groupby": spec.groupby,
    }
    return sql, params, filters_echo
