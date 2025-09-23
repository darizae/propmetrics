from typing import Tuple, List, Dict, Any
from app.query.spec import QuerySpec


def build_sql(spec: QuerySpec) -> Tuple[str, List[Any], Dict[str, Any]]:
    where: List[str] = []
    params: List[Any] = []

    # Date range over stichtag
    where.append("CAST(stichtag AS DATE) BETWEEN ? AND ?")
    params.extend([spec.date_range.start.isoformat(), spec.date_range.end.isoformat()])

    # Municipality filter (normalized)
    if spec.municipality:
        ph = ",".join(["?"] * len(spec.municipality))
        where.append(f"lower(trim(municipality)) IN ({ph})")
        params.extend([m.strip().lower() for m in spec.municipality])

    # Land use (exact codes like WA, WR, MI, GE, etc.)
    if spec.land_use:
        ph = ",".join(["?"] * len(spec.land_use))
        where.append(f"trim(land_use) IN ({ph})")
        params.extend([u.strip() for u in spec.land_use])

    # Postal code
    if spec.plz:
        ph = ",".join(["?"] * len(spec.plz))
        where.append(f"trim(plz) IN ({ph})")
        params.extend([p.strip() for p in spec.plz])

    where_sql = " AND ".join(where) if where else "TRUE"

    select_key_aliases: List[str] = []
    group_by_exprs: List[str] = []
    if spec.groupby == "month":
        month_expr = "date_trunc('month', CAST(stichtag AS DATE))"
        select_key_aliases.append(f"{month_expr} AS month")
        group_by_exprs.append(month_expr)
        order_by = "ORDER BY month"
    elif spec.groupby == "municipality":
        select_key_aliases.append("municipality")
        group_by_exprs.append("municipality")
        order_by = "ORDER BY municipality"
    elif spec.groupby == "land_use":
        select_key_aliases.append("land_use")
        group_by_exprs.append("land_use")
        order_by = "ORDER BY land_use"
    else:
        order_by = ""

    group_expr = ""
    group_by_clause = ""
    if select_key_aliases:
        group_expr = ", " + ", ".join(select_key_aliases)
        group_by_clause = "GROUP BY " + ", ".join(group_by_exprs)

    metrics = """
        COUNT(*) AS zones,
        MEDIAN(eur_per_m2) AS median_eur_per_m2
    """

    sql = f"""
    WITH src AS (
        SELECT
            municipality,
            land_use,
            plz,
            eur_per_m2,
            stichtag
        FROM brw
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
        "municipality": [m.strip().lower() for m in spec.municipality] if spec.municipality else None,
        "land_use": [u.strip() for u in spec.land_use] if spec.land_use else None,
        "plz": [p.strip() for p in spec.plz] if spec.plz else None,
        "groupby": spec.groupby,
    }
    return sql, params, filters_echo
