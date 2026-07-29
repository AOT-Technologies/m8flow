import logging

from m8flow_telemetry.logging_bridge import M8FLOW_TENANT_ID_ATTR, StdlibTenantFilter, TenantAttributeLogProcessor


def test_tenant_attribute_log_processor_adds_tenant_id():
    processor = TenantAttributeLogProcessor(lambda: "tenant-abc")

    class _LogRecord:
        attributes = None

    rw = type("RW", (), {"log_record": _LogRecord()})()
    processor.on_emit(rw)  # type: ignore[arg-type]
    assert rw.log_record.attributes[M8FLOW_TENANT_ID_ATTR] == "tenant-abc"


def test_stdlib_filter_sets_record_attribute():
    filt = StdlibTenantFilter(lambda: "tenant-xyz")
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "msg", (), None)
    assert filt.filter(record) is True
    assert record.m8flow_tenant_id == "tenant-xyz"
