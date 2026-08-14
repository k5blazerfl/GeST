"""CI-safe tests for the gestd Services adapter — the model->property-bag
converters (pure) and the contract shape. The variant packing + live rc-* reads
are exercised by the round-trip on an OpenRC host."""

from gest.core.services.model import Service, ServiceDetail
from gest.coreservice import services_adapter as adapter
from gest.ipc import core_contract


def test_service_to_dict_shape_and_enabled_running():
    s = Service(name="sshd", status="started", runlevels=["default"])
    d = adapter.service_to_dict(s)
    assert d["name"] == "sshd" and d["status"] == "started"
    assert d["runlevels"] == ["default"]
    assert d["enabled"] is True and d["running"] is True
    assert set(d) == {"name", "status", "runlevels", "enabled", "running"}


def test_service_to_dict_stopped_and_not_enabled():
    d = adapter.service_to_dict(Service(name="foo"))       # stopped, no runlevels
    assert d["status"] == "stopped"
    assert d["enabled"] is False and d["running"] is False and d["runlevels"] == []


def test_detail_to_dict_scalars_and_dep_lists():
    det = ServiceDetail(name="sshd", description="OpenSSH server",
                        needs=["net"], uses=["logger"], wants=["dns"],
                        needed_by=["x"], status="started", runlevels=["default"])
    d = adapter.detail_to_dict(det)
    assert d["description"] == "OpenSSH server"
    assert d["needs"] == ["net"] and d["uses"] == ["logger"]
    assert d["wants"] == ["dns"] and d["needed_by"] == ["x"]
    assert d["status"] == "started" and d["running"] is True and d["runlevels"] == ["default"]


def test_services_contract_shape():
    assert core_contract.SERVICES_CORE_IFACE == "org.gentoo.gest.core1.Services"
    assert core_contract.SERVICES_CORE_PATH == "/org/gentoo/gest/core/Services"
