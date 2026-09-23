from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
import re
import zipfile

import pandas as pd


MONTHS = {
    "янв": 1,
    "фев": 2,
    "март": 3,
    "мар": 3,
    "апр": 4,
    "май": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сент": 9,
    "сен": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}


@dataclass(frozen=True)
class SupplierSpec:
    folder: str
    label: str
    lead_time_days: int
    transit_tokens: tuple[str, ...]


@dataclass
class ProductData:
    code: str
    sku: str
    product_name: str
    supplier: str
    category: str
    unit: str
    sales_by_month: dict[tuple[int, int], float]
    stock_qty: float
    in_transit_qty: float
    moq: float
    unit_price_kzt: float | None
    lead_time_days: int


def load_products(zip_path, iek_lead_time_days: int, systeme_lead_time_days: int) -> list[ProductData]:
    specs = [
        SupplierSpec("IEK", "ИЭК", iek_lead_time_days, ("Путь",)),
        SupplierSpec("Systeme electric", "SystemElectric", systeme_lead_time_days, ("Товар в пути",)),
    ]
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".xlsx")]
        products: list[ProductData] = []
        for spec in specs:
            supplier_names = [name for name in names if name.startswith(f"{spec.folder}/")]
            if not supplier_names:
                continue
            products.extend(_load_supplier(archive, supplier_names, spec))
        return products


def _load_supplier(archive: zipfile.ZipFile, names: list[str], spec: SupplierSpec) -> list[ProductData]:
    moq = _load_moq(archive, _find_file(names, ("MOQ",)))
    monthly_sales = _load_monthly_table(archive, _find_file(names, ("Ежемесячные", "продажи")))
    monthly_stock = _load_monthly_table(archive, _find_file(names, ("Ежемесячные", "остатки")))
    transit = _load_transit(archive, _find_file(names, spec.transit_tokens), spec.label)

    codes = set(monthly_sales) | set(monthly_stock) | set(transit) | set(moq)
    products: list[ProductData] = []
    for code in sorted(codes):
        sales_row = monthly_sales.get(code, {})
        stock_row = monthly_stock.get(code, {})
        transit_row = transit.get(code, {})
        moq_row = moq.get(code, {})

        name = _first_text(
            sales_row.get("product_name"),
            stock_row.get("product_name"),
            transit_row.get("product_name"),
            moq_row.get("product_name"),
            f"Товар {code}",
        )
        sku = _first_text(transit_row.get("sku"), moq_row.get("sku"), code)
        unit = _first_text(sales_row.get("unit"), stock_row.get("unit"), "шт.")
        category = _first_text(transit_row.get("category"), _guess_category(name))
        moq_value = _positive_number(moq_row.get("moq"), default=1)
        if moq_value <= 0:
            moq_value = 1

        products.append(
            ProductData(
                code=code,
                sku=sku,
                product_name=name,
                supplier=spec.label,
                category=category,
                unit=unit,
                sales_by_month=sales_row.get("months", {}),
                stock_qty=max(_number(stock_row.get("latest_value")), 0),
                in_transit_qty=max(_number(transit_row.get("in_transit_qty")), 0),
                moq=moq_value,
                unit_price_kzt=_optional_number(transit_row.get("unit_price_kzt")),
                lead_time_days=spec.lead_time_days,
            )
        )
    return products


def _find_file(names: list[str], tokens: tuple[str, ...]) -> str:
    lowered = [(name, name.casefold()) for name in names]
    for name, lowered_name in lowered:
        if all(token.casefold() in lowered_name for token in tokens):
            return name
    raise FileNotFoundError(f"Не найден Excel-файл с токенами: {tokens}")


def _read_excel(archive: zipfile.ZipFile, name: str, **kwargs) -> pd.DataFrame:
    with archive.open(name) as source:
        return pd.read_excel(BytesIO(source.read()), **kwargs)


def _load_moq(archive: zipfile.ZipFile, name: str) -> dict[str, dict]:
    df = _read_excel(archive, name)
    code_col = _column(df, ("Код 1с", "Номенклатура.Код", "Код"))
    name_col = _column(df, ("Наименование", "Номенклатура"))
    sku_col = _column(df, ("Артикул поставщика", "Артикул"), required=False)
    moq_col = _column(df, ("Мин. разр. к отгр.", "Кратность", "MOQ"), required=False)
    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        code = _clean_code(row.get(code_col))
        if not code:
            continue
        result[code] = {
            "product_name": _clean_text(row.get(name_col)),
            "sku": _clean_text(row.get(sku_col)) if sku_col else "",
            "moq": _number(row.get(moq_col)) if moq_col else 1,
        }
    return result


def _load_monthly_table(archive: zipfile.ZipFile, name: str) -> dict[str, dict]:
    df = _read_excel(archive, name)
    code_col = _column(df, ("Номенклатура.Код", "Код 1с", "Код"))
    name_col = _column(df, ("Номенклатура", "Наименование"))
    unit_col = _column(df, ("Ед.изм", "Ед."), required=False)
    month_cols = _month_columns(df)
    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        code = _clean_code(row.get(code_col))
        if not code:
            continue
        months = {
            key: max(_number(row.get(column)), 0)
            for key, column in month_cols
            if not math.isnan(_number(row.get(column)))
        }
        latest_value = None
        if month_cols:
            latest_value = _number(row.get(month_cols[-1][1]))
        result[code] = {
            "product_name": _clean_text(row.get(name_col)),
            "unit": _clean_text(row.get(unit_col)) if unit_col else "шт.",
            "months": months,
            "latest_value": latest_value,
        }
    return result


def _load_transit(archive: zipfile.ZipFile, name: str, supplier: str) -> dict[str, dict]:
    raw = _read_excel(archive, name, header=None)
    header_index = _header_row_index(raw)
    if header_index is None:
        df = _read_excel(archive, name)
    else:
        columns = [_clean_text(value) or f"col_{index}" for index, value in enumerate(raw.iloc[header_index])]
        df = raw.iloc[header_index + 1 :].copy()
        df.columns = columns

    code_col = _column(df, ("Код 1с", "Номенклатура.Код", "Код"))
    name_col = _column(df, ("Наименование", "Номенклатура"))
    sku_col = _column(df, ("Артикул поставщика", "Артикул"), required=False)
    category_col = _column(df, ("Категория",), required=False)
    price_col = _column(df, ("СС реал", "Цена", "Прайс"), required=False)

    transit_columns = _transit_columns(df, supplier)
    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        code = _clean_code(row.get(code_col))
        if not code:
            continue
        in_transit = sum(max(_number(row.get(column)), 0) for column in transit_columns)
        result[code] = {
            "product_name": _clean_text(row.get(name_col)),
            "sku": _clean_text(row.get(sku_col)) if sku_col else "",
            "category": _category_label(row.get(category_col)) if category_col else "",
            "in_transit_qty": in_transit,
            "unit_price_kzt": _optional_number(row.get(price_col)) if price_col else None,
        }
    return result


def _header_row_index(raw: pd.DataFrame) -> int | None:
    for index, row in raw.head(8).iterrows():
        values = " ".join(_clean_text(value) for value in row.tolist())
        if "Код 1с" in values and "Наименование" in values:
            return int(index)
    return None


def _transit_columns(df: pd.DataFrame, supplier: str) -> list[str]:
    if supplier == "SystemElectric":
        columns = [
            column
            for column in df.columns
            if "в пути" in str(column).casefold() and _numeric_series(df[column]).sum() > 0
        ]
        return columns
    metadata_tokens = ("код", "артикул", "наименование", "категория", "цена", "вес")
    columns = []
    for column in df.columns:
        lowered = str(column).casefold()
        if any(token in lowered for token in metadata_tokens):
            continue
        if _numeric_series(df[column]).sum() > 0:
            columns.append(column)
    return columns


def _month_columns(df: pd.DataFrame) -> list[tuple[tuple[int, int], str]]:
    result = []
    for column in df.columns:
        key = _month_key(str(column))
        if key:
            result.append((key, column))
    return sorted(result)


def _month_key(label: str) -> tuple[int, int] | None:
    normalized = label.replace("\xa0", " ").casefold()
    year_match = re.search(r"(20\d{2})", normalized)
    if not year_match:
        return None
    for token, month in MONTHS.items():
        if token in normalized:
            return (int(year_match.group(1)), month)
    return None


def _column(df: pd.DataFrame, options: tuple[str, ...], required: bool = True) -> str | None:
    for option in options:
        for column in df.columns:
            if option.casefold() in str(column).casefold():
                return column
    if required:
        raise KeyError(f"Не найдена колонка: {options}")
    return None


def _numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", ".", regex=False), errors="coerce").fillna(0)


def _number(value) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    parsed = pd.to_numeric(str(value).replace("\xa0", "").replace(" ", "").replace(",", "."), errors="coerce")
    if pd.isna(parsed):
        return 0.0
    return float(parsed)


def _optional_number(value) -> float | None:
    parsed = _number(value)
    return parsed if parsed > 0 else None


def _positive_number(value, default: float) -> float:
    parsed = _number(value)
    return parsed if parsed > 0 else default


def _clean_code(value) -> str:
    text = _clean_text(value)
    if not text or text.casefold() == "nan":
        return ""
    return text.replace(" ", "")


def _clean_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", text)


def _first_text(*values: str) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _category_label(value) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return f"Категория {text}"


def _guess_category(product_name: str) -> str:
    lowered = product_name.casefold()
    if any(token in lowered for token in ("розет", "выключ", "переключ", "рамк")):
        return "Розетки и выключатели"
    if any(token in lowered for token in ("кабель", "провод", "utp", "ftp")):
        return "Кабель и провод"
    if any(token in lowered for token in ("светиль", "ламп", "led")):
        return "Освещение"
    if any(token in lowered for token in ("автомат", "узо", "реле", "контактор")):
        return "Автоматика"
    return "Электрика"
