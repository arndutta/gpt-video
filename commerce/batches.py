"""Transactional batch application, receipt lookup, and idempotent replay."""

from decimal import Decimal
import hashlib
import json

from fastapi import HTTPException

from commerce.models import PriceBatch
from commerce.rules import invalid_ladder_families, validate_item
from commerce.storage import connect, product_rows, utc_now


def receipt(db_path, batch_key: str) -> dict:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT result_json FROM batches WHERE batch_key = ?", (batch_key,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Batch receipt not found.")
    return json.loads(row[0])


def apply_batch(db_path, batch: PriceBatch) -> dict:
    canonical = json.dumps(batch.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            "SELECT payload_digest, result_json FROM batches WHERE batch_key = ?",
            (batch.batch_key,),
        ).fetchone()
        if existing:
            if existing["payload_digest"] != digest:
                raise HTTPException(409, "Batch key already belongs to a different payload.")
            return json.loads(existing["result_json"])
        products = product_rows(connection)
        by_sku = {row["sku"]: row for row in products}
        errors = {item.sku: validate_item(item, by_sku.get(item.sku)) for item in batch.items}
        proposed = {item.sku: item.price for item in batch.items if errors[item.sku] is None}
        invalid_families = invalid_ladder_families(products, proposed)
        for item in batch.items:
            product = by_sku.get(item.sku)
            if errors[item.sku] is None and product["family_id"] in invalid_families:
                errors[item.sku] = (
                    "price_ladder", "Family changes were rejected together to preserve the size-price ladder."
                )
        timestamp, results = utc_now(), []
        for item in batch.items:
            product, error = by_sku.get(item.sku), errors[item.sku]
            prior = product["current_price"] if product else None
            version = product["price_version"] if product else None
            result = {"sku": item.sku, "status": "rejected" if error else "applied",
                      "prior_price": prior, "new_price": format(item.price, ".2f"),
                      "prior_version": version, "new_version": version,
                      "applied_at": None, "rejection_code": error[0] if error else None,
                      "rejection_reason": error[1] if error else None}
            if error is None:
                # A no-change request is a successful, idempotent no-op with no new history.
                if item.price != Decimal(prior):
                    result["new_version"] = version + 1
                    connection.execute(
                        "UPDATE prices SET current_price = ?, price_version = ?, updated_at = ? WHERE sku = ?",
                        (result["new_price"], result["new_version"], timestamp, item.sku),
                    )
                    connection.execute(
                        "INSERT INTO price_history (sku,batch_key,prior_price,new_price,prior_version,"
                        "new_version,actor,approval_kind,applied_at) VALUES (?,?,?,?,?,?,?,?,?)",
                        (item.sku, batch.batch_key, prior, result["new_price"], version,
                         result["new_version"], batch.actor, batch.approval_kind, timestamp),
                    )
                result["applied_at"] = timestamp
            results.append(result)
        applied = sum(row["status"] == "applied" for row in results)
        status = "applied" if applied == len(results) else "partial" if applied else "rejected"
        response = {"batch_key": batch.batch_key, "status": status, "items": results}
        connection.execute(
            "INSERT INTO batches VALUES (?, ?, ?, ?)",
            (batch.batch_key, digest, json.dumps(response, sort_keys=True), timestamp),
        )
        connection.commit()
        return response
