from intelligence import analyze_document, detect_pii, parse_dates, mask_value

def test_parse_dates_formats_and_invalid_dates():
    assert "2026-10-12" in parse_dates("Due date: 2026-10-12")
    assert "2026-10-12" in parse_dates("Issued 12/10/2026")
    assert "2026-02-30" not in parse_dates("bad 2026-02-30")

def test_pii_masking():
    found=detect_pii("Contact neha@example.com or call +92 300 1234567")
    assert any(x["type"]=="Email" for x in found)
    assert all(len(x["masked"])<=len(x["value"]) for x in found)
    assert mask_value("123456789")=="•••••6789"

def test_analyze_document_category_dates_amount():
    info=analyze_document("Electricity bill\nDue date: 2026-10-12\nTotal Rs. 18,450.00\nEmail: a@b.com","bill.pdf")
    assert info["category"]=="Finance"
    assert info["due_date"]=="2026-10-12"
    assert info["amount"]==18450.0
    assert info["pii"]

def test_empty_text_is_safe():
    info=analyze_document("","scan.png")
    assert info["category"]=="Other"
    assert info["amount"] is None
