from typing import Tuple, List, Dict, Any
from app.query.spec import QuerySpec


def build_sql(spec: QuerySpec) -> Tuple[str, List[Any], Dict[str, Any]]:
    where: List[str] = []
    params: List[Any] = []

    where.append("CAST(sale_date AS DATE) BETWEEN ? AND ?")
    params.extend([spec.date_range.start.isoformat(), spec.date_range.end.isoformat()])

    if spec.borough:
        ph = ",".join(["?"] * len(spec.borough))
        where.append(f"borough IN ({ph})")
        params.extend([b.lower() for b in spec.borough])

    if spec.neighborhood:
        ph = ",".join(["?"] * len(spec.neighborhood))
        where.append(f"lower(neighborhood) IN ({ph})")
        params.extend([n.lower() for n in spec.neighborhood])

    if spec.building_class_category:
        ph = ",".join(["?"] * len(spec.building_class_category))
        where.append(f"building_class_category IN ({ph})")
        params.extend(spec.building_class_category)

    where_sql = " AND ".join(where) if where else "TRUE"

    src_select_cols = [
        "borough",
        "neighborhood",
        "building_class_category",
        "sale_price",
        "price_per_sqft",
        "sale_date",
    ]
    select_keys: List[str] = []
    order_by = ""

    if spec.groupby == "month":
        src_select_cols.append("date_trunc('month', CAST(sale_date AS DATE)) AS month")
        select_keys.append("month")
        order_by = "ORDER BY month"
    elif spec.groupby == "neighborhood":
        select_keys.append("neighborhood")
        order_by = "ORDER BY neighborhood"
    elif spec.groupby == "class":
        select_keys.append("building_class_category")
        order_by = "ORDER BY building_class_category"

    group_by_clause = f"GROUP BY {', '.join(select_keys)}" if select_keys else ""

    metrics = """
        COUNT(*) AS txns,
        SUM(sale_price) AS total_sale_price,
        MEDIAN(sale_price) AS median_sale_price,
        MEDIAN(price_per_sqft) AS median_price_per_sqft
    """

    key_select = (", " + ", ".join(select_keys)) if select_keys else ""

    sql = f"""
    WITH src AS (
        SELECT {", ".join(src_select_cols)}
        FROM nyc
        WHERE {where_sql}
    )
    SELECT
        {metrics.strip()}{key_select}
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
