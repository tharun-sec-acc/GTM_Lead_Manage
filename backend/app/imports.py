import io
import re
import zipfile
from xml.etree.ElementTree import ParseError

from email_validator import EmailNotValidError, validate_email
from openpyxl import load_workbook
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Batch, ImportRow, Lead, Product, ProductLead, now

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 100
MAX_SHEETS = 50
FIELDS = ("company_name", "domain", "email", "revenue", "phone", "remarks", "key_person_info",
          "designation", "industry", "location")


def _read_sheet(sheet):
    if sheet.max_column and sheet.max_column > MAX_COLUMNS:
        raise ValueError(f"Worksheet '{sheet.title}' exceeds {MAX_COLUMNS} columns.")
    if sheet.max_row and sheet.max_row > MAX_ROWS + 1:
        raise ValueError(f"Worksheet '{sheet.title}' exceeds {MAX_ROWS} data rows.")
    iterator = sheet.iter_rows(values_only=True)
    first = next(iterator, None)
    if first is None:
        return [], []
    headers = []
    used = set()
    for index, cell in enumerate(first):
        base = str(cell).strip() if cell is not None and str(cell).strip() else f"Column {index + 1}"
        name = base
        suffix = 2
        while name in used:
            name = f"{base} [{suffix}]"
            suffix += 1
        headers.append(name)
        used.add(name)
    if not headers:
        return [], []
    rows = []
    for row_number, row in enumerate(iterator, start=2):
        if row_number > MAX_ROWS + 1:
            raise ValueError(f"Worksheet '{sheet.title}' exceeds {MAX_ROWS} data rows.")
        values = [str(value).strip() if value is not None else "" for value in row[:len(headers)]]
        values.extend([""] * (len(headers) - len(values)))
        if any(values):
            rows.append((row_number, dict(zip(headers, values))))
    return headers, rows


def workbook_sheets(content: bytes):
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("File exceeds the 10 MB limit.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("The uncompressed spreadsheet exceeds 100 MB.")
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
        try:
            if len(workbook.worksheets) > MAX_SHEETS:
                raise ValueError(f"Workbook exceeds {MAX_SHEETS} worksheets.")
            sheets = {}
            total_rows = 0
            for sheet in workbook.worksheets:
                headers, rows = _read_sheet(sheet)
                total_rows += len(rows)
                if total_rows > MAX_ROWS:
                    raise ValueError(f"Workbook exceeds {MAX_ROWS} non-empty data rows.")
                sheets[sheet.title] = {"headers": headers, "rows": rows}
            if not sheets:
                raise ValueError("Workbook has no worksheets.")
            if not any(item["headers"] for item in sheets.values()):
                raise ValueError("Workbook contains no worksheet with a header row.")
            return sheets
        finally:
            workbook.close()
    except (zipfile.BadZipFile, KeyError, OSError, EOFError, ParseError) as exc:
        raise ValueError("Invalid or damaged .xlsx file.") from exc


def workbook_rows(content: bytes):
    """Compatibility adapter for older callers and batches using the original single-sheet API."""
    sheets = workbook_sheets(content)
    if len(sheets) == 1:
        active_sheet = next(iter(sheets))
    else:
        try:
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
            try:
                active_sheet = workbook.active.title
            finally:
                workbook.close()
        except (KeyError, OSError, EOFError) as exc:
            raise ValueError("Invalid or damaged .xlsx file.") from exc
    if active_sheet is None:
        raise ValueError("Workbook contains no worksheet with a header row.")
    return sheets[active_sheet]["headers"], sheets[active_sheet]["rows"]


def workbook_active_sheet_name(content: bytes):
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True, keep_links=False)
    try:
        return workbook.active.title if workbook.active else None
    finally:
        workbook.close()


def validate_mapping(mapping: dict, headers: list[str]):
    if any(field not in FIELDS for field in mapping):
        raise ValueError("Unknown field in column mapping.")
    if not mapping.get("company_name"):
        raise ValueError("Map the company name column.")
    columns = [column for column in mapping.values() if column]
    if any(column not in headers for column in columns):
        raise ValueError("A mapped column is not present in the spreadsheet.")
    if len(set(columns)) != len(columns):
        raise ValueError("Each spreadsheet column may be mapped only once.")


def process_batch(session: Session, batch_id: str):
    # Serialize imports so concurrent batches cannot race on duplicate checks.
    if session.bind and session.bind.dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(776281945)"))
    batch = session.scalar(select(Batch).where(Batch.id == batch_id).with_for_update())
    if batch is None or batch.status != "pending":
        return
    product = None
    if batch.product_id:
        product = session.get(Product, batch.product_id)
        if product is None:
            raise ValueError("The product selected for this import no longer exists.")
        if product.status != "active":
            raise ValueError("The product selected for this import is archived.")
    sheets = workbook_sheets(batch.content)
    mapping = batch.mapping or {}
    legacy_mapping = bool(mapping) and all(key in FIELDS for key in mapping)
    if legacy_mapping:
        active_name = workbook_active_sheet_name(batch.content)
        if active_name not in sheets or not sheets[active_name]["headers"]:
            raise ValueError("The original active worksheet has no header row.")
        sheet_mappings = {active_name: mapping}
    elif isinstance(mapping, dict) and mapping:
        sheet_mappings = mapping
    else:
        raise ValueError("No worksheet mappings were selected.")
    if any(name not in sheets for name in sheet_mappings):
        raise ValueError("A selected worksheet no longer exists in the uploaded workbook.")
    batch.sheet_headers = {name: sheet["headers"] for name, sheet in sheets.items()}

    for sheet_name, sheet_mapping in sheet_mappings.items():
        headers = sheets[sheet_name]["headers"]
        rows = sheets[sheet_name]["rows"]
        if not headers:
            if rows:
                raise ValueError(f"Worksheet '{sheet_name}' has data but no header row.")
            continue
        validate_mapping(sheet_mapping, headers)
        for row_number, original in rows:
            values = {field: original.get(sheet_mapping.get(field, ""), "").strip() for field in FIELDS}
            company = values["company_name"]
            email = values["email"]
            error = None
            if not company:
                error = "Company name is required."
            elif len(company) > 500:
                error = "Company name exceeds 500 characters."
            if email and not error:
                try:
                    email = validate_email(email, check_deliverability=False).normalized
                except EmailNotValidError:
                    error = "Invalid email address."
            domain = values["domain"].strip().lower().rstrip(".")
            if domain and not error and (len(domain) > 253 or not re.fullmatch(
                r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", domain
            )):
                error = "Company domain must be a hostname such as example.com."
            company_key = re.sub(r"\s+", " ", company.casefold()).strip()
            duplicate = None
            if not error:
                if email:
                    duplicate = session.scalar(select(Lead).where(func.lower(Lead.email) == email.lower()))
                if duplicate is None:
                    duplicate = session.scalar(select(Lead).where(Lead.company_key == company_key))
            if error:
                session.add(ImportRow(batch_id=batch.id, sheet_name=sheet_name, row_number=row_number,
                                      original=original, status="invalid", message=error))
            elif duplicate:
                associated = False
                if product is not None and session.scalar(select(ProductLead).where(
                    ProductLead.product_id == product.id, ProductLead.lead_id == duplicate.id
                )) is None:
                    session.add(ProductLead(
                        product_id=product.id, lead_id=duplicate.id, stage="prospect",
                        priority="medium", status="active",
                        associated_at=now(), updated_at=now(),
                    ))
                    associated = True
                session.add(ImportRow(
                    batch_id=batch.id, sheet_name=sheet_name, row_number=row_number,
                    original=original, status="imported" if associated else "duplicate",
                    message=("Existing company associated with this product." if associated
                             else "Possible duplicate; review the original row."),
                    lead_id=duplicate.id,
                ))
            else:
                used = {value for value in sheet_mapping.values() if value}
                lead = Lead(
                    company_name=company, company_key=company_key, email=email or None,
                    domain=domain or None,
                    designation=values["designation"] or None,
                    industry=values["industry"] or None,
                    location=values["location"] or None,
                    revenue=values["revenue"] or None, phone=values["phone"] or None,
                    remarks=values["remarks"] or None, key_person_info=values["key_person_info"] or None,
                    extra={key: value for key, value in original.items() if key not in used},
                )
                session.add(lead)
                session.flush()
                if product is not None:
                    session.add(ProductLead(
                        product_id=product.id, lead_id=lead.id, stage="prospect",
                        priority="medium", status="active",
                        associated_at=now(), updated_at=now(),
                    ))
                session.add(ImportRow(batch_id=batch.id, sheet_name=sheet_name, row_number=row_number,
                                      original=original, status="imported", lead_id=lead.id))
    batch.status = "completed"
    batch.error = None
